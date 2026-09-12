"""Cola de trabajos sobre PostgreSQL: `generation_jobs` como única pieza de datos (§3.3).

No hay Redis ni broker: la cola **es** la tabla `generation_jobs`, tal como fija §1.2
(«Única pieza de datos: OLTP + vectores + FTS + eventos de dominio»). La toma de trabajo
usa el patrón canónico de PostgreSQL

```sql
UPDATE generation_jobs SET status = 'RUNNING', …
 WHERE id = (SELECT id FROM generation_jobs
              WHERE status = 'PENDING' AND queue = ANY(…) AND <listo para reintento>
              ORDER BY priority, created_at
              FOR UPDATE SKIP LOCKED
              LIMIT 1)
RETURNING id;
```

`FOR UPDATE SKIP LOCKED` es lo que hace **seguro correr varias instancias del worker**:
dos consumidores simultáneos nunca reciben la misma fila, y un worker lento no bloquea
a los demás. Todo en una sola sentencia atómica, sin ventana de carrera entre el
`SELECT` y el `UPDATE`.

Otras piezas del contrato que viven aquí:

* **Reintentos con retroceso exponencial** — `attempt_count` / `max_attempts` (por
  defecto 3). Un fallo reintentable devuelve el trabajo a `PENDING` y marca `finished_at`;
  la consulta de toma no lo vuelve a ofrecer hasta que pase `base · 2^intentos`. Sin
  columna nueva: el retroceso se calcula en SQL sobre `finished_at`.
* **Pasos persistidos** (`steps`) — un reintento **reanuda** en vez de repetir; es lo que
  hace la ingesta y la generación idempotentes frente a una caída a mitad.
* **Progreso** (`progress_pct`, `progress_label`) — alimenta `GET /paths/{id}/generation`.
* **Cancelación** — `JobStatus.CANCELLED`; un trabajo cancelado nunca se vuelve a tomar.
* **Idempotencia** (`idempotency_key`, único) — encolar dos veces lo mismo devuelve el
  trabajo existente en lugar de duplicarlo.

Los segundos de retroceso y el tiempo de trabajo atascado son parámetros de
**infraestructura**, no de juego: no existen en §5 y por eso viven aquí como constantes.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.enums import JobMode, JobStatus, JobType
from app.models.ingestion import GenerationJob

logger = get_logger("atenea.worker.cola")

#: Colas lógicas de `generation_jobs.queue` (§3.3).
COLA_INGESTA = "ingest"
COLA_GENERACION = "generate"
COLA_MANTENIMIENTO = "housekeeping"
COLAS: tuple[str, ...] = (COLA_INGESTA, COLA_GENERACION, COLA_MANTENIMIENTO)

#: Base del retroceso exponencial entre reintentos, en segundos (infraestructura).
RETROCESO_BASE_SEGUNDOS = 15

#: Tope del retroceso, en segundos: 10 minutos.
RETROCESO_MAXIMO_SEGUNDOS = 600

#: Un trabajo `RUNNING` más tiempo del que dura la ingesta se considera huérfano.
MINUTOS_TRABAJO_ATASCADO = 15

#: Estados terminales: ni se toman ni se reintentan.
ESTADOS_TERMINALES: frozenset[JobStatus] = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.CANCELLED, JobStatus.FAILED}
)


class TrabajoNoEncontrado(NotFound):
    """404 · El trabajo no existe o no pertenece a quien pregunta (§8.7)."""


# ---------------------------------------------------------------------------
# Encolado
# ---------------------------------------------------------------------------


def encolar(
    db: Session,
    *,
    job_type: JobType,
    queue: str = COLA_GENERACION,
    usuario_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    learning_path_id: uuid.UUID | None = None,
    document_version_id: uuid.UUID | None = None,
    prompt_template_id: uuid.UUID | None = None,
    priority: int = 100,
    max_attempts: int = 3,
    mode: JobMode = JobMode.SYNC,
    provider: str = "anthropic",
    idempotency_key: str | None = None,
    progress_label: str | None = None,
    momento: dt.datetime | None = None,
) -> GenerationJob:
    """Inserta un trabajo `PENDING`. Con `idempotency_key` repetida devuelve el existente.

    La clave es única global en `generation_jobs`, así que la carrera entre dos peticiones
    simultáneas se resuelve en la base: el perdedor recupera la fila del ganador.
    """
    ahora = momento or utcnow()
    if idempotency_key:
        existente = por_clave(db, idempotency_key)
        if existente is not None:
            return existente

    trabajo = GenerationJob(
        user_id=usuario_id,
        job_type=job_type,
        status=JobStatus.PENDING,
        mode=mode,
        queue=queue,
        priority=priority,
        target_type=target_type,
        target_id=target_id,
        learning_path_id=learning_path_id,
        document_version_id=document_version_id,
        prompt_template_id=prompt_template_id,
        provider=provider,
        max_attempts=max(1, int(max_attempts)),
        payload=dict(payload or {}),
        result={},
        steps=[],
        progress_label=progress_label,
        idempotency_key=idempotency_key,
        queued_at=ahora,
    )
    punto = db.begin_nested()
    try:
        db.add(trabajo)
        db.flush()
    except IntegrityError:
        punto.rollback()
        if idempotency_key:
            existente = por_clave(db, idempotency_key)
            if existente is not None:
                return existente
        raise
    punto.commit()
    logger.info(
        "trabajo_encolado",
        job_id=str(trabajo.id),
        job_type=str(job_type),
        queue=queue,
        priority=priority,
    )
    return trabajo


def por_clave(db: Session, idempotency_key: str) -> GenerationJob | None:
    """Devuelve el trabajo ya encolado con esa clave de idempotencia, si existe."""
    return db.execute(
        sa.select(GenerationJob).where(GenerationJob.idempotency_key == idempotency_key)
    ).scalar_one_or_none()


def obtener(
    db: Session, job_id: uuid.UUID, *, usuario_id: uuid.UUID | None = None
) -> GenerationJob:
    """Carga un trabajo comprobando la propiedad; si no es del usuario, 404 (no 403)."""
    trabajo = db.get(GenerationJob, job_id)
    if trabajo is None:
        raise TrabajoNoEncontrado("No encontramos ese trabajo.")
    if usuario_id is not None and trabajo.user_id is not None and trabajo.user_id != usuario_id:
        raise TrabajoNoEncontrado("No encontramos ese trabajo.")
    return trabajo


# ---------------------------------------------------------------------------
# Toma de trabajo
# ---------------------------------------------------------------------------


def _listo_para_reintento(ahora: dt.datetime) -> Any:
    """Cláusula del retroceso exponencial, calculada en SQL sobre `finished_at`.

    Un trabajo que nunca falló (`attempt_count = 0` o sin `finished_at`) está listo. Uno
    que falló espera `min(base · 2^intentos, tope)` segundos desde su último fallo.
    """
    espera = sa.func.least(
        sa.cast(RETROCESO_MAXIMO_SEGUNDOS, sa.Float),
        sa.cast(RETROCESO_BASE_SEGUNDOS, sa.Float)
        * sa.func.power(sa.cast(2.0, sa.Float), sa.cast(GenerationJob.attempt_count, sa.Float)),
    )
    # Se compara en segundos transcurridos en vez de construir un `interval`: el
    # resultado es el mismo y la expresión es portable y directa en SQL.
    transcurrido = sa.func.extract(
        "epoch", sa.literal(ahora, sa.DateTime(timezone=True)) - GenerationJob.finished_at
    )
    return sa.or_(
        GenerationJob.finished_at.is_(None),
        GenerationJob.attempt_count == 0,
        transcurrido >= espera,
    )


def tomar_siguiente(
    db: Session,
    *,
    colas: list[str] | tuple[str, ...] | None = None,
    momento: dt.datetime | None = None,
) -> GenerationJob | None:
    """Toma un trabajo `PENDING` y lo deja `RUNNING`, con `FOR UPDATE SKIP LOCKED`.

    Es la primitiva que permite correr varios workers a la vez: dos consumidores
    concurrentes **nunca** obtienen la misma fila. Devuelve `None` si no hay trabajo
    disponible en las colas pedidas.
    """
    ahora = momento or utcnow()
    colas_efectivas = list(colas) if colas else list(COLAS)

    candidato = (
        sa.select(GenerationJob.id)
        .where(
            GenerationJob.status == JobStatus.PENDING,
            GenerationJob.queue.in_(colas_efectivas),
            GenerationJob.attempt_count < GenerationJob.max_attempts,
            _listo_para_reintento(ahora),
        )
        .order_by(GenerationJob.priority.asc(), GenerationJob.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )

    sentencia = (
        sa.update(GenerationJob)
        .where(GenerationJob.id == candidato)
        .values(
            status=JobStatus.RUNNING,
            started_at=ahora,
            finished_at=None,
            attempt_count=GenerationJob.attempt_count + 1,
            error_message=None,
        )
        .returning(GenerationJob.id)
        .execution_options(synchronize_session=False)
    )
    identificador = db.execute(sentencia).scalar_one_or_none()
    if identificador is None:
        return None

    trabajo = db.get(GenerationJob, identificador)
    if trabajo is not None:
        db.refresh(trabajo)
    return trabajo


def reclamar_atascados(
    db: Session, *, minutos: int = MINUTOS_TRABAJO_ATASCADO, momento: dt.datetime | None = None
) -> int:
    """Devuelve a `PENDING` los trabajos `RUNNING` cuyo worker murió; devuelve cuántos."""
    ahora = momento or utcnow()
    limite = ahora - dt.timedelta(minutes=minutos)
    sentencia = (
        sa.update(GenerationJob)
        .where(
            GenerationJob.status == JobStatus.RUNNING,
            GenerationJob.started_at.is_not(None),
            GenerationJob.started_at <= limite,
        )
        .values(status=JobStatus.PENDING, finished_at=ahora, error_message="Worker interrumpido.")
        .execution_options(synchronize_session=False)
    )
    resultado = db.execute(sentencia)
    return int(resultado.rowcount or 0)


# ---------------------------------------------------------------------------
# Pasos persistidos (reanudación)
# ---------------------------------------------------------------------------


def paso_hecho(trabajo: GenerationJob, nombre: str) -> bool:
    """Indica si un paso ya se completó en un intento anterior."""
    return any(
        isinstance(paso, dict) and paso.get("step") == nombre for paso in (trabajo.steps or [])
    )


def registrar_paso(
    db: Session,
    trabajo: GenerationJob,
    nombre: str,
    datos: dict[str, Any] | None = None,
    *,
    momento: dt.datetime | None = None,
) -> None:
    """Anota un paso completado en `steps` para que el reintento lo salte."""
    pasos = list(trabajo.steps or [])
    pasos = [paso for paso in pasos if not (isinstance(paso, dict) and paso.get("step") == nombre)]
    pasos.append(
        {
            "step": nombre,
            "at": (momento or utcnow()).isoformat().replace("+00:00", "Z"),
            "data": dict(datos or {}),
        }
    )
    trabajo.steps = pasos
    db.flush()


# ---------------------------------------------------------------------------
# Progreso y cierre
# ---------------------------------------------------------------------------


def marcar_progreso(
    db: Session,
    trabajo: GenerationJob,
    *,
    pct: float | int,
    label: str | None = None,
) -> None:
    """Actualiza el progreso visible de la pantalla de generación (0–100)."""
    from decimal import Decimal  # noqa: PLC0415 - solo aquí hace falta

    valor = max(0.0, min(100.0, float(pct)))
    trabajo.progress_pct = Decimal(f"{valor:.2f}")
    if label is not None:
        trabajo.progress_label = label[:120]
    db.flush()


def completar(
    db: Session,
    trabajo: GenerationJob,
    *,
    result: dict[str, Any] | None = None,
    label: str | None = None,
    momento: dt.datetime | None = None,
) -> GenerationJob:
    """Cierra el trabajo como `SUCCEEDED` al 100 % de progreso."""
    from decimal import Decimal  # noqa: PLC0415

    ahora = momento or utcnow()
    trabajo.status = JobStatus.SUCCEEDED
    trabajo.result = dict(result or {})
    trabajo.progress_pct = Decimal("100.00")
    if label is not None:
        trabajo.progress_label = label[:120]
    trabajo.error_message = None
    trabajo.finished_at = ahora
    db.flush()
    logger.info("trabajo_completado", job_id=str(trabajo.id), job_type=str(trabajo.job_type))
    return trabajo


def fallar(
    db: Session,
    trabajo: GenerationJob,
    mensaje: str,
    *,
    reintentable: bool = True,
    detalles: dict[str, Any] | None = None,
    momento: dt.datetime | None = None,
) -> GenerationJob:
    """Registra un fallo: vuelve a `PENDING` si quedan intentos, si no queda `FAILED`.

    Un fallo **no reintentable** (material ilegible, formato no admitido, esquema roto)
    cierra el trabajo de inmediato: reintentarlo daría exactamente el mismo resultado.
    """
    ahora = momento or utcnow()
    trabajo.error_message = str(mensaje)[:2000]
    trabajo.finished_at = ahora
    if detalles:
        resultado = dict(trabajo.result or {})
        resultado["error"] = dict(detalles)
        trabajo.result = resultado

    agotado = trabajo.attempt_count >= trabajo.max_attempts
    if reintentable and not agotado:
        trabajo.status = JobStatus.PENDING
    else:
        trabajo.status = JobStatus.FAILED
    db.flush()
    logger.warning(
        "trabajo_fallido",
        job_id=str(trabajo.id),
        job_type=str(trabajo.job_type),
        status=str(trabajo.status),
        intento=trabajo.attempt_count,
        max_intentos=trabajo.max_attempts,
        error=trabajo.error_message,
    )
    return trabajo


def necesita_atencion(
    db: Session, trabajo: GenerationJob, mensaje: str, *, momento: dt.datetime | None = None
) -> GenerationJob:
    """Marca `NEEDS_ATTENTION`: el trabajo no se pierde, pero nadie lo reintenta solo."""
    trabajo.status = JobStatus.NEEDS_ATTENTION
    trabajo.error_message = str(mensaje)[:2000]
    trabajo.finished_at = momento or utcnow()
    db.flush()
    logger.error("trabajo_necesita_atencion", job_id=str(trabajo.id), error=trabajo.error_message)
    return trabajo


def cancelar(
    db: Session,
    job_id: uuid.UUID,
    *,
    usuario_id: uuid.UUID | None = None,
    motivo: str | None = None,
    momento: dt.datetime | None = None,
) -> GenerationJob:
    """Cancela un trabajo pendiente o en curso; los terminados se devuelven intactos."""
    trabajo = obtener(db, job_id, usuario_id=usuario_id)
    if trabajo.status in ESTADOS_TERMINALES:
        return trabajo
    trabajo.status = JobStatus.CANCELLED
    trabajo.finished_at = momento or utcnow()
    if motivo:
        trabajo.error_message = motivo[:2000]
    db.flush()
    return trabajo


def cancelar_pendientes(
    db: Session,
    *,
    usuario_id: uuid.UUID | None = None,
    document_version_id: uuid.UUID | None = None,
    learning_path_id: uuid.UUID | None = None,
    motivo: str = "Cancelado por el usuario.",
    momento: dt.datetime | None = None,
) -> int:
    """Cancela en bloque los trabajos aún vivos de un documento o de una ruta."""
    filtros: list[Any] = [GenerationJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING])]
    if usuario_id is not None:
        filtros.append(GenerationJob.user_id == usuario_id)
    if document_version_id is not None:
        filtros.append(GenerationJob.document_version_id == document_version_id)
    if learning_path_id is not None:
        filtros.append(GenerationJob.learning_path_id == learning_path_id)
    if len(filtros) == 1:  # nunca se cancela "todo" por accidente
        return 0
    sentencia = (
        sa.update(GenerationJob)
        .where(*filtros)
        .values(
            status=JobStatus.CANCELLED,
            finished_at=momento or utcnow(),
            error_message=motivo[:2000],
        )
        .execution_options(synchronize_session=False)
    )
    return int(db.execute(sentencia).rowcount or 0)


# ---------------------------------------------------------------------------
# Consultas de apoyo
# ---------------------------------------------------------------------------


def trabajos_de_ruta(db: Session, learning_path_id: uuid.UUID) -> list[GenerationJob]:
    """Trabajos de una ruta, del más antiguo al más nuevo (pantalla de generación)."""
    return list(
        db.execute(
            sa.select(GenerationJob)
            .where(GenerationJob.learning_path_id == learning_path_id)
            .order_by(GenerationJob.created_at.asc())
        )
        .scalars()
        .all()
    )


def trabajos_de_version(db: Session, document_version_id: uuid.UUID) -> list[GenerationJob]:
    """Trabajos asociados a una versión de documento, del más reciente al más antiguo."""
    return list(
        db.execute(
            sa.select(GenerationJob)
            .where(GenerationJob.document_version_id == document_version_id)
            .order_by(GenerationJob.created_at.desc())
        )
        .scalars()
        .all()
    )


def pendientes(db: Session, *, colas: list[str] | None = None) -> int:
    """Número de trabajos a la espera (métrica del worker y de las pruebas)."""
    consulta = sa.select(sa.func.count(GenerationJob.id)).where(
        GenerationJob.status == JobStatus.PENDING
    )
    if colas:
        consulta = consulta.where(GenerationJob.queue.in_(colas))
    return int(db.execute(consulta).scalar() or 0)


__all__ = [
    "COLAS",
    "COLA_GENERACION",
    "COLA_INGESTA",
    "COLA_MANTENIMIENTO",
    "ESTADOS_TERMINALES",
    "MINUTOS_TRABAJO_ATASCADO",
    "RETROCESO_BASE_SEGUNDOS",
    "RETROCESO_MAXIMO_SEGUNDOS",
    "TrabajoNoEncontrado",
    "cancelar",
    "cancelar_pendientes",
    "completar",
    "encolar",
    "fallar",
    "marcar_progreso",
    "necesita_atencion",
    "obtener",
    "paso_hecho",
    "pendientes",
    "por_clave",
    "reclamar_atascados",
    "registrar_paso",
    "tomar_siguiente",
    "trabajos_de_ruta",
    "trabajos_de_version",
]
