"""Presupuesto de IA, cuotas por usuario, registro del gasto y degradación elegante.

Tres frenos, en este orden:

1. **Cuota diaria por usuario** (`ai.quotas_per_day`, §5.8): diseños de ruta,
   re-explicaciones, respuestas juzgadas, regeneraciones de módulo. Se agota → `429
   QUOTA_EXCEEDED` con `details.quota` y `details.resets_at`.
2. **Presupuesto global del día** (`ai.global_budget_usd_per_day` = 30 USD): al cruzar
   los umbrales de `ai.budget_thresholds` (`[0.8, 1.0]`) se emite el evento
   `AI_BUDGET_THRESHOLD`; al agotarse se lanza `PresupuestoAgotado`
   (`503 AI_BUDGET_EXCEEDED`).
3. **Degradación elegante**: cuando el presupuesto está agotado, todo lo que **no**
   necesita IA sigue funcionando (corrección determinista, sandbox de SQL, contenido ya
   generado). Solo se detiene lo que exige una llamada nueva.

El gasto vive en `generation_jobs` (`input_tokens`, `cached_input_tokens`,
`output_tokens`, `cost_usd`): es la única fuente de verdad del coste (§3.3).
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import AteneaError, QuotaExceeded
from app.core.time import day_start_utc, user_local_date, utcnow
from app.models.enums import EventType, JobStatus, JobType
from app.models.ingestion import GenerationJob
from app.modules.ai.proveedor import UsoIA
from app.modules.gamification import eventos as bus
from app.modules.gamification.servicio_config import ServicioConfig

# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------


class PresupuestoAgotado(AteneaError):
    """503 · Freno global de presupuesto de IA; la evaluación determinista sigue viva."""

    code = "AI_BUDGET_EXCEEDED"
    status_code = 503


# ---------------------------------------------------------------------------
# Cuotas: clave de `ai.quotas_per_day` -> trabajos que la consumen
# ---------------------------------------------------------------------------

CUOTA_DISENOS_RUTA: Final[str] = "path_designs"
CUOTA_REEXPLICACIONES: Final[str] = "re_explanations"
CUOTA_RESPUESTAS_JUZGADAS: Final[str] = "judged_answers"
CUOTA_REGENERACIONES: Final[str] = "module_regenerations"

#: Tipos de `generation_jobs` que consumen cada cuota diaria.
TIPOS_POR_CUOTA: Final[dict[str, tuple[JobType, ...]]] = {
    CUOTA_DISENOS_RUTA: (JobType.PATH_DESIGN,),
    CUOTA_REEXPLICACIONES: (JobType.RE_EXPLANATION,),
    CUOTA_RESPUESTAS_JUZGADAS: (JobType.ANSWER_JUDGEMENT,),
    CUOTA_REGENERACIONES: (JobType.MODULE_GENERATION,),
}

#: Estados que cuentan como consumo (un trabajo cancelado no gasta cuota).
_ESTADOS_QUE_CONSUMEN: Final[tuple[JobStatus, ...]] = (
    JobStatus.PENDING,
    JobStatus.RUNNING,
    JobStatus.SUCCEEDED,
    JobStatus.NEEDS_ATTENTION,
)


# ---------------------------------------------------------------------------
# Zona horaria y ventana del día
# ---------------------------------------------------------------------------


def fecha_local(
    db: Session, usuario_id: uuid.UUID | None, momento: dt.datetime | None = None
) -> dt.date:
    """Fecha local del usuario (§8.6: la calcula siempre el servidor)."""
    zona = bus.zona_horaria_de_usuario(db, usuario_id)
    return user_local_date(momento or utcnow(), zona)


def ventana_del_dia(
    db: Session, usuario_id: uuid.UUID | None, dia: dt.date | None = None
) -> tuple[dt.datetime, dt.datetime, dt.date, str]:
    """Límites UTC del día local del usuario, más el día y su zona."""
    zona = bus.zona_horaria_de_usuario(db, usuario_id)
    fecha = dia or user_local_date(utcnow(), zona)
    inicio = day_start_utc(fecha, zona)
    fin = day_start_utc(fecha + dt.timedelta(days=1), zona)
    return inicio, fin, fecha, zona


# ---------------------------------------------------------------------------
# Gasto
# ---------------------------------------------------------------------------


def gasto_global(db: Session, *, desde: dt.datetime, hasta: dt.datetime) -> Decimal:
    """Suma de `generation_jobs.cost_usd` en la ventana indicada."""
    total = db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(GenerationJob.cost_usd), 0)).where(
            GenerationJob.created_at >= desde,
            GenerationJob.created_at < hasta,
        )
    ).scalar_one()
    return Decimal(total or 0)


def gasto_de_usuario(
    db: Session, usuario_id: uuid.UUID, *, desde: dt.datetime, hasta: dt.datetime
) -> Decimal:
    """Gasto de IA imputable a un usuario en la ventana indicada."""
    total = db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(GenerationJob.cost_usd), 0)).where(
            GenerationJob.user_id == usuario_id,
            GenerationJob.created_at >= desde,
            GenerationJob.created_at < hasta,
        )
    ).scalar_one()
    return Decimal(total or 0)


def presupuesto_diario(cfg: ServicioConfig) -> Decimal:
    """`ai.global_budget_usd_per_day` (§5.8)."""
    return Decimal(str(cfg.obtener("ai.global_budget_usd_per_day", 0)))


@dataclass(frozen=True, slots=True)
class EstadoPresupuesto:
    """Foto del presupuesto global del día."""

    gastado: Decimal
    presupuesto: Decimal
    fecha: dt.date

    @property
    def restante(self) -> Decimal:
        """Cuánto queda antes del freno (nunca negativo)."""
        return max(Decimal("0"), self.presupuesto - self.gastado)

    @property
    def fraccion(self) -> Decimal:
        """Proporción consumida del presupuesto (0 si no hay presupuesto definido)."""
        if self.presupuesto <= 0:
            return Decimal("0")
        return self.gastado / self.presupuesto

    @property
    def agotado(self) -> bool:
        """`True` cuando ya no se puede hacer ninguna llamada nueva."""
        return self.presupuesto > 0 and self.gastado >= self.presupuesto


def estado_presupuesto(db: Session, cfg: ServicioConfig, *, momento: dt.datetime | None = None) -> EstadoPresupuesto:
    """Calcula el estado del presupuesto global para el día UTC en curso."""
    instante = momento or utcnow()
    hoy = instante.date()
    desde = dt.datetime.combine(hoy, dt.time.min, tzinfo=dt.UTC)
    hasta = desde + dt.timedelta(days=1)
    return EstadoPresupuesto(
        gastado=gasto_global(db, desde=desde, hasta=hasta),
        presupuesto=presupuesto_diario(cfg),
        fecha=hoy,
    )


def emitir_umbrales(
    db: Session, cfg: ServicioConfig, estado: EstadoPresupuesto
) -> list[int]:
    """Emite `AI_BUDGET_THRESHOLD` por cada umbral cruzado (idempotente por día)."""
    umbrales = [Decimal(str(u)) for u in (cfg.obtener_lista("ai.budget_thresholds", []) or [])]
    emitidos: list[int] = []
    for umbral in sorted(umbrales):
        if umbral <= 0 or estado.fraccion < umbral:
            continue
        porcentaje = int(umbral * 100)
        evento = bus.crear_evento_dominio(
            db,
            usuario_id=None,
            tipo=EventType.AI_BUDGET_THRESHOLD,
            payload={
                "threshold_pct": porcentaje,
                "spent_usd": float(estado.gastado),
                "budget_usd": float(estado.presupuesto),
            },
            idempotency_key=f"ai-budget:{estado.fecha.isoformat()}:{porcentaje}",
            source_module="ai",
        )
        if evento is not None:
            emitidos.append(porcentaje)
    return emitidos


def verificar_presupuesto(
    db: Session, cfg: ServicioConfig, *, momento: dt.datetime | None = None
) -> EstadoPresupuesto:
    """Comprueba el freno global antes de una llamada; emite los umbrales cruzados."""
    estado = estado_presupuesto(db, cfg, momento=momento)
    emitir_umbrales(db, cfg, estado)
    if estado.agotado:
        raise PresupuestoAgotado(
            "El servicio de generación está saturado. Inténtalo más tarde.",
            details={
                "spent_usd": float(estado.gastado),
                "budget_usd": float(estado.presupuesto),
            },
            headers={"Retry-After": "3600"},
        )
    return estado


def modo_degradado(db: Session, cfg: ServicioConfig, *, momento: dt.datetime | None = None) -> bool:
    """`True` si hay que degradar: no se puede llamar a la IA, pero el resto sigue.

    Los módulos la consultan para elegir el camino determinista (corrección sin juez,
    contenido ya generado, sandbox de SQL) en lugar de fallar de cara al usuario.
    """
    return estado_presupuesto(db, cfg, momento=momento).agotado


# ---------------------------------------------------------------------------
# Cuotas por usuario
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EstadoCuota:
    """Consumo de una cuota diaria del usuario."""

    clave: str
    usado: int
    limite: int
    resets_at: dt.datetime

    @property
    def restante(self) -> int:
        """Usos que quedan hoy."""
        return max(0, self.limite - self.usado)

    @property
    def agotada(self) -> bool:
        """`True` si ya no quedan usos."""
        return self.limite > 0 and self.usado >= self.limite


def limite_de_cuota(cfg: ServicioConfig, clave: str) -> int:
    """Valor de `ai.quotas_per_day[clave]` (§5.8)."""
    cuotas = cfg.obtener_json("ai.quotas_per_day", {}) or {}
    return int(cuotas.get(clave, 0) or 0)


def consumo_de_cuota(
    db: Session,
    usuario_id: uuid.UUID,
    clave: str,
    *,
    desde: dt.datetime,
    hasta: dt.datetime,
) -> int:
    """Cuenta los trabajos del usuario que consumen esa cuota en el día local."""
    tipos = TIPOS_POR_CUOTA.get(clave, ())
    if not tipos:
        return 0
    return int(
        db.execute(
            sa.select(sa.func.count(GenerationJob.id)).where(
                GenerationJob.user_id == usuario_id,
                GenerationJob.job_type.in_(tipos),
                GenerationJob.status.in_(_ESTADOS_QUE_CONSUMEN),
                GenerationJob.created_at >= desde,
                GenerationJob.created_at < hasta,
            )
        ).scalar_one()
        or 0
    )


def estado_cuota(
    db: Session, cfg: ServicioConfig, usuario_id: uuid.UUID, clave: str
) -> EstadoCuota:
    """Estado de una cuota diaria para el día **local** del usuario."""
    desde, hasta, _, _ = ventana_del_dia(db, usuario_id)
    return EstadoCuota(
        clave=clave,
        usado=consumo_de_cuota(db, usuario_id, clave, desde=desde, hasta=hasta),
        limite=limite_de_cuota(cfg, clave),
        resets_at=hasta,
    )


def verificar_cuota(
    db: Session, cfg: ServicioConfig, usuario_id: uuid.UUID | None, clave: str
) -> EstadoCuota | None:
    """Lanza `QuotaExceeded` (429) si la cuota diaria del usuario está agotada."""
    if usuario_id is None:
        return None
    estado = estado_cuota(db, cfg, usuario_id, clave)
    if estado.agotada:
        raise QuotaExceeded(
            "Agotaste tu cuota diaria. Vuelve a intentarlo mañana.",
            details={
                "quota": clave,
                "limit": estado.limite,
                "used": estado.usado,
                "resets_at": estado.resets_at.isoformat().replace("+00:00", "Z"),
            },
        )
    return estado


# ---------------------------------------------------------------------------
# Registro del gasto en el trabajo
# ---------------------------------------------------------------------------


def registrar_uso(db: Session, job: GenerationJob | None, uso: UsoIA) -> GenerationJob | None:
    """Acumula tokens y coste de una llamada en su `generation_jobs`."""
    if job is None:
        return None
    job.provider = uso.provider or job.provider
    job.model_id = uso.model_id or job.model_id
    job.input_tokens = int(job.input_tokens or 0) + uso.input_tokens
    job.cached_input_tokens = int(job.cached_input_tokens or 0) + uso.cached_input_tokens
    job.output_tokens = int(job.output_tokens or 0) + uso.output_tokens
    job.cost_usd = Decimal(job.cost_usd or 0) + uso.cost_usd
    db.flush()
    return job


def crear_job(
    db: Session,
    *,
    job_type: JobType,
    usuario_id: uuid.UUID | None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    learning_path_id: uuid.UUID | None = None,
    document_version_id: uuid.UUID | None = None,
    prompt_template_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    queue: str = "generate",
    progress_label: str | None = None,
) -> GenerationJob:
    """Crea el `generation_jobs` que contabiliza y traza una generación."""
    job = GenerationJob(
        user_id=usuario_id,
        job_type=job_type,
        status=JobStatus.RUNNING,
        queue=queue,
        target_type=target_type,
        target_id=target_id,
        learning_path_id=learning_path_id,
        document_version_id=document_version_id,
        prompt_template_id=prompt_template_id,
        payload=payload or {},
        idempotency_key=idempotency_key,
        progress_label=progress_label,
        queued_at=utcnow(),
        started_at=utcnow(),
        attempt_count=1,
    )
    db.add(job)
    db.flush()
    return job


def cerrar_job(
    db: Session,
    job: GenerationJob | None,
    *,
    estado: JobStatus = JobStatus.SUCCEEDED,
    resultado: dict[str, Any] | None = None,
    error: str | None = None,
) -> GenerationJob | None:
    """Cierra el trabajo con su estado final, resultado y progreso al 100 %."""
    if job is None:
        return None
    job.status = estado
    job.finished_at = utcnow()
    if resultado is not None:
        job.result = resultado
    if error is not None:
        job.error_message = error[:2000]
    if estado is JobStatus.SUCCEEDED:
        job.progress_pct = Decimal("100.00")
    db.flush()
    return job


__all__ = [
    "CUOTA_DISENOS_RUTA",
    "CUOTA_REEXPLICACIONES",
    "CUOTA_REGENERACIONES",
    "CUOTA_RESPUESTAS_JUZGADAS",
    "TIPOS_POR_CUOTA",
    "EstadoCuota",
    "EstadoPresupuesto",
    "PresupuestoAgotado",
    "cerrar_job",
    "consumo_de_cuota",
    "crear_job",
    "emitir_umbrales",
    "estado_cuota",
    "estado_presupuesto",
    "gasto_de_usuario",
    "gasto_global",
    "limite_de_cuota",
    "fecha_local",
    "modo_degradado",
    "presupuesto_diario",
    "registrar_uso",
    "ventana_del_dia",
    "verificar_cuota",
    "verificar_presupuesto",
]
