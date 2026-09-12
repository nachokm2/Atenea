"""Presupuesto global, cuotas por usuario, registro del gasto y degradación."""

from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.core.errors import QuotaExceeded
from app.core.time import utcnow
from app.models.enums import EventType, JobStatus, JobType
from app.models.gamification import DomainEvent
from app.models.ingestion import GenerationJob
from app.modules.ai import costos
from app.modules.ai.proveedor import UsoIA, calcular_coste


def _job(db, usuario, *, coste: str, tipo: JobType = JobType.PATH_DESIGN) -> GenerationJob:
    """Crea un trabajo ya cerrado con el coste indicado."""
    fila = GenerationJob(
        user_id=usuario.id,
        job_type=tipo,
        status=JobStatus.SUCCEEDED,
        cost_usd=Decimal(coste),
        queued_at=utcnow(),
    )
    db.add(fila)
    db.flush()
    return fila


# ---------------------------------------------------------------------------
# Registro del gasto
# ---------------------------------------------------------------------------


def test_registrar_uso_suma_en_el_trabajo(db, cfg, usuario) -> None:
    """Cada llamada acumula tokens y coste en su `generation_jobs`."""
    job = costos.crear_job(db, job_type=JobType.LESSON_GENERATION, usuario_id=usuario.id)
    assert job.input_tokens == 0

    primera = UsoIA(
        model_id="claude-sonnet-5",
        provider="anthropic",
        input_tokens=1_000,
        cached_input_tokens=500,
        output_tokens=300,
        cost_usd=calcular_coste(
            "claude-sonnet-5", input_tokens=1_000, cached_input_tokens=500, output_tokens=300
        ),
    )
    costos.registrar_uso(db, job, primera)
    costos.registrar_uso(db, job, primera)

    db.refresh(job)
    assert job.input_tokens == 2_000
    assert job.cached_input_tokens == 1_000
    assert job.output_tokens == 600
    assert job.cost_usd == primera.cost_usd * 2
    assert job.model_id == "claude-sonnet-5"
    assert job.provider == "anthropic"


def test_el_contador_de_uso_suma(proveedor) -> None:
    """El acumulador del proveedor suma llamadas, tokens y coste."""
    uno = UsoIA(model_id="m", provider="p", input_tokens=10, output_tokens=4, cost_usd=Decimal("0.5"))
    dos = UsoIA(model_id="m", provider="p", input_tokens=6, output_tokens=2, cost_usd=Decimal("0.25"))
    proveedor.contador.registrar(uno, "lesson")
    proveedor.contador.registrar(dos, "questions")
    contador = proveedor.uso_acumulado
    assert contador.llamadas == 2
    assert contador.input_tokens == 16
    assert contador.output_tokens == 6
    assert contador.cost_usd == Decimal("0.75")
    assert contador.como_dict()["by_task"] == {"lesson": 1, "questions": 1}
    assert (uno + dos).cost_usd == Decimal("0.75")


def test_cerrar_job_marca_progreso_y_resultado(db, usuario) -> None:
    """Un trabajo terminado queda al 100 % con su resultado persistido."""
    job = costos.crear_job(db, job_type=JobType.MODULE_GENERATION, usuario_id=usuario.id)
    costos.cerrar_job(db, job, estado=JobStatus.SUCCEEDED, resultado={"lessons": 3})
    db.refresh(job)
    assert job.status is JobStatus.SUCCEEDED
    assert job.progress_pct == 100
    assert job.result == {"lessons": 3}
    assert job.finished_at is not None


# ---------------------------------------------------------------------------
# Presupuesto global
# ---------------------------------------------------------------------------


def test_gasto_global_suma_el_dia(db, cfg, usuario) -> None:
    """El gasto del día es la suma de `cost_usd` de los trabajos del día."""
    _job(db, usuario, coste="1.500000")
    _job(db, usuario, coste="2.250000")
    estado = costos.estado_presupuesto(db, cfg)
    assert estado.gastado >= Decimal("3.750000")
    assert estado.presupuesto == Decimal("30")
    assert estado.agotado is False
    assert estado.restante <= Decimal("26.25")


def test_emite_el_umbral_del_80_una_sola_vez(db, cfg, usuario) -> None:
    """`ai.budget_thresholds`: se avisa al cruzar el umbral, y solo una vez por día."""
    _job(db, usuario, coste="25.000000")
    estado = costos.estado_presupuesto(db, cfg)
    assert costos.emitir_umbrales(db, cfg, estado) == [80]
    assert costos.emitir_umbrales(db, cfg, estado) == []

    eventos = list(
        db.execute(
            sa.select(DomainEvent).where(DomainEvent.event_type == EventType.AI_BUDGET_THRESHOLD)
        ).scalars()
    )
    assert len(eventos) == 1
    assert eventos[0].payload["threshold_pct"] == 80
    assert eventos[0].payload["budget_usd"] == 30.0
    assert eventos[0].source_module == "ai"


def test_freno_global_al_agotar_el_presupuesto(db, cfg, usuario) -> None:
    """Agotado el presupuesto, cualquier llamada nueva se detiene con 503."""
    _job(db, usuario, coste="30.000000")
    assert costos.modo_degradado(db, cfg) is True
    with pytest.raises(costos.PresupuestoAgotado) as error:
        costos.verificar_presupuesto(db, cfg)
    assert error.value.code == "AI_BUDGET_EXCEEDED"
    assert error.value.status_code == 503
    assert error.value.headers["Retry-After"] == "3600"


def test_sin_gasto_no_hay_degradacion(db, cfg) -> None:
    """Con el presupuesto intacto no se degrada nada."""
    assert costos.modo_degradado(db, cfg) is False


# ---------------------------------------------------------------------------
# Cuotas por usuario
# ---------------------------------------------------------------------------


def test_cuota_diaria_por_usuario(db, cfg, usuario) -> None:
    """`ai.quotas_per_day.path_designs = 2`: el tercer diseño del día se rechaza."""
    assert costos.limite_de_cuota(cfg, costos.CUOTA_DISENOS_RUTA) == 2

    estado = costos.estado_cuota(db, cfg, usuario.id, costos.CUOTA_DISENOS_RUTA)
    assert estado.usado == 0 and estado.restante == 2

    _job(db, usuario, coste="0.1", tipo=JobType.PATH_DESIGN)
    costos.verificar_cuota(db, cfg, usuario.id, costos.CUOTA_DISENOS_RUTA)
    _job(db, usuario, coste="0.1", tipo=JobType.PATH_DESIGN)

    with pytest.raises(QuotaExceeded) as error:
        costos.verificar_cuota(db, cfg, usuario.id, costos.CUOTA_DISENOS_RUTA)
    assert error.value.code == "QUOTA_EXCEEDED"
    assert error.value.status_code == 429
    assert error.value.details["quota"] == "path_designs"
    assert error.value.details["limit"] == 2
    assert error.value.details["resets_at"].endswith("Z")


def test_la_cuota_de_un_usuario_no_afecta_a_otro(db, cfg, usuario) -> None:
    """Las cuotas son por usuario; el gasto de uno no penaliza a otro."""
    from app.models.identity import User

    otro = User(email="otro-cuota@atenea.test", password_hash="x" * 20, timezone="UTC")
    db.add(otro)
    db.flush()
    _job(db, usuario, coste="0.1", tipo=JobType.PATH_DESIGN)
    _job(db, usuario, coste="0.1", tipo=JobType.PATH_DESIGN)

    assert costos.estado_cuota(db, cfg, otro.id, costos.CUOTA_DISENOS_RUTA).usado == 0
    costos.verificar_cuota(db, cfg, otro.id, costos.CUOTA_DISENOS_RUTA)


def test_sin_usuario_no_hay_cuota(db, cfg) -> None:
    """Los trabajos de sistema no consumen cuota de nadie."""
    assert costos.verificar_cuota(db, cfg, None, costos.CUOTA_DISENOS_RUTA) is None
