"""Que Rodrigo se entere de que el gasto de IA se le está yendo.

El freno funcionaba: `verificar_presupuesto` corta antes de gastar. Lo que no
había era nadie al otro lado. `AI_BUDGET_THRESHOLD` se escribía en
`domain_events` al cruzar el 80 % y el 100 %, y ahí se quedaba: ninguna tarea lo
barría, ningún endpoint lo exponía, y el módulo que lo escribe ni siquiera tiene
registro. El aviso existía y no salía de la máquina.

Nada de esto envía correo de verdad: en pruebas `email_provider` vale `consola`,
que escribe el mensaje en el registro y no abre ni un socket.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core import correo
from app.core.config import settings
from app.core.errors import AteneaError
from app.models.enums import EventStatus, EventType, JobStatus, JobType
from app.models.gamification import DomainEvent
from app.models.identity import User
from app.models.ingestion import GenerationJob
from app.modules.ai import costos
from app.modules.gamification.servicio_config import ServicioConfig
from app.worker import principal


@pytest.fixture
def espia_de_correo(monkeypatch):
    """Sustituye el envío por un buzón en memoria."""
    enviados: list[dict] = []

    def _enviar(*, destinatario: str, asunto: str, cuerpo: str) -> None:
        enviados.append({"destinatario": destinatario, "asunto": asunto, "cuerpo": cuerpo})

    monkeypatch.setattr(correo, "enviar", _enviar)
    monkeypatch.setattr(settings, "alert_email", "rodrigo@ejemplo.test")
    return enviados


def _gastar(db: Session, usuario: User, usd: str) -> GenerationJob:
    """Deja un trabajo terminado con su coste, que es como se mide el gasto."""
    job = GenerationJob(
        user_id=usuario.id,
        job_type=JobType.PATH_DESIGN,
        status=JobStatus.SUCCEEDED,
        queue="generate",
        cost_usd=Decimal(usd),
    )
    db.add(job)
    db.flush()
    return job


def _umbrales(db: Session) -> list[DomainEvent]:
    return list(
        db.execute(
            sa.select(DomainEvent)
            .where(DomainEvent.event_type == EventType.AI_BUDGET_THRESHOLD)
            .order_by(DomainEvent.occurred_at)
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# El aviso sale
# ---------------------------------------------------------------------------


def test_cruzar_el_umbral_manda_un_correo(
    db: Session, cfg: ServicioConfig, usuario: User, espia_de_correo
) -> None:
    _gastar(db, usuario, "25.00")  # el presupuesto sembrado son 30
    costos.verificar_presupuesto(db, cfg)
    assert _umbrales(db), "sin evento no hay nada que drenar"

    resumen = principal.mantenimiento(db)

    assert resumen.get("avisos_presupuesto") == 1
    assert len(espia_de_correo) == 1
    aviso = espia_de_correo[0]
    assert aviso["destinatario"] == "rodrigo@ejemplo.test"
    assert "80" in aviso["asunto"]
    assert "25.00" in aviso["asunto"]
    # El cuerpo tiene que decir qué hacer, no solo que algo pasó.
    assert "ai.global_budget_usd_per_day" in aviso["cuerpo"]


def test_el_evento_queda_marcado_y_no_se_reenvia(
    db: Session, cfg: ServicioConfig, usuario: User, espia_de_correo
) -> None:
    """La fila es su propia marca de «ya avisado»."""
    _gastar(db, usuario, "25.00")
    costos.verificar_presupuesto(db, cfg)

    principal.mantenimiento(db)
    principal.mantenimiento(db)

    assert len(espia_de_correo) == 1
    evento = _umbrales(db)[0]
    assert evento.processing_status == EventStatus.PROCESSED
    assert evento.processed_at is not None


def test_el_aviso_del_cien_por_ciento_dice_que_se_corto(
    db: Session, cfg: ServicioConfig, usuario: User, espia_de_correo
) -> None:
    from app.modules.ai.costos import PresupuestoAgotado

    _gastar(db, usuario, "31.00")
    with pytest.raises(PresupuestoAgotado):
        costos.verificar_presupuesto(db, cfg)

    principal.mantenimiento(db)

    asuntos = " ".join(a["asunto"] for a in espia_de_correo)
    cuerpos = " ".join(a["cuerpo"] for a in espia_de_correo)
    assert "agot" in asuntos
    assert "503" in cuerpos


def test_sin_umbrales_cruzados_no_se_manda_nada(
    db: Session, cfg: ServicioConfig, usuario: User, espia_de_correo
) -> None:
    _gastar(db, usuario, "1.00")
    costos.verificar_presupuesto(db, cfg)

    resumen = principal.mantenimiento(db)

    assert espia_de_correo == []
    assert "avisos_presupuesto" not in resumen


# ---------------------------------------------------------------------------
# Cuando algo va mal con el propio aviso
# ---------------------------------------------------------------------------


def test_sin_direccion_de_operador_queda_dicho_en_la_fila(
    db: Session, cfg: ServicioConfig, usuario: User, monkeypatch
) -> None:
    """Había algo que avisar y no había a quién. No es lo mismo que haber avisado."""
    monkeypatch.setattr(settings, "alert_email", None)
    _gastar(db, usuario, "25.00")
    costos.verificar_presupuesto(db, cfg)

    principal.mantenimiento(db)

    assert _umbrales(db)[0].processing_status == EventStatus.SKIPPED


def test_un_correo_caido_no_para_el_worker(
    db: Session, cfg: ServicioConfig, usuario: User, monkeypatch
) -> None:
    """El resto del mantenimiento tiene que seguir funcionando."""

    def _explota(**_: object) -> None:
        raise AteneaError("El servidor de correo no responde.", code="GENERATION_FAILED")

    monkeypatch.setattr(correo, "enviar", _explota)
    monkeypatch.setattr(settings, "alert_email", "rodrigo@ejemplo.test")
    _gastar(db, usuario, "25.00")
    costos.verificar_presupuesto(db, cfg)

    resumen = principal.mantenimiento(db)

    assert _umbrales(db)[0].processing_status == EventStatus.FAILED
    # Y las demás tareas del mantenimiento siguieron su curso.
    assert "reclamados" in resumen


def test_el_mismo_umbral_no_se_escribe_dos_veces(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """La antifatiga no es código: es la unicidad de la clave en PostgreSQL."""
    _gastar(db, usuario, "25.00")

    costos.verificar_presupuesto(db, cfg)
    costos.verificar_presupuesto(db, cfg)
    costos.verificar_presupuesto(db, cfg)

    assert len(_umbrales(db)) == 1


# ---------------------------------------------------------------------------
# Que la cifra del aviso no mienta
# ---------------------------------------------------------------------------


def test_los_intentos_que_no_validan_tambien_se_cobran(db: Session, usuario: User) -> None:
    """El proveedor cobra el intento aunque su respuesta no cumpla el esquema.

    Antes ese consumo se descartaba al levantar `SalidaInvalida`, así que una
    racha de generaciones rotas quemaba la tarjeta mientras el presupuesto del
    día seguía en cero y el freno no saltaba nunca.
    """
    from app.modules.ai.esquemas_salida import SalidaInvalida
    from app.modules.ai.proveedor import UsoIA

    job = _gastar(db, usuario, "0")
    fallo = SalidaInvalida("No cuadró.", details={})
    fallo.uso = UsoIA(
        provider="claude",
        model_id="claude-opus-5",
        input_tokens=1000,
        cached_input_tokens=0,
        output_tokens=2000,
        cost_usd=Decimal("0.42"),
    )

    costos.registrar_uso(db, job, fallo.uso)

    db.refresh(job)
    assert float(job.cost_usd) == pytest.approx(0.42)
    assert job.output_tokens == 2000
