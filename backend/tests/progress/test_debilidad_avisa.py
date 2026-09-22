"""Cuando un tema se marca débil, alguien tiene que enterarse.

`WEAKNESS_DETECTED` estaba en el catálogo de eventos (§4.2) y en el contrato, con
`REVIEW_RECOMMENDED` colgando de él, pero no se emitía en ninguna parte: el
recálculo de dominio escribía `is_weak` en la tabla y ahí se quedaba. La
consecuencia práctica era que el repaso espaciado solo tenía una puerta —la
pantalla de resultado de una evaluación—, y quien no pasaba por ahí no volvía a
ver ese tema nunca.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.content import KnowledgeArea
from app.models.enums import EventType, KnowledgeAreaStatus, KnowledgeCategory, NotificationType
from app.models.gamification import DomainEvent, Notification
from app.models.identity import User
from app.models.progress import UserAreaProgress, UserTopicProgress
from app.modules.progress.dominio import ServicioDominio

from .conftest import registrar_respuesta


def _fallar_muchas_veces(db: Session, usuario: User, contenido, veces: int = 6) -> None:
    """Evidencias suficientes y todas malas: la regla R2 se cumple sin discusión."""
    for _ in range(veces):
        registrar_respuesta(db, usuario, contenido, correcta=False)


def _eventos(db: Session, tipo: EventType) -> list[DomainEvent]:
    return list(
        db.execute(sa.select(DomainEvent).where(DomainEvent.event_type == tipo)).scalars().all()
    )


def _avisos(db: Session) -> list[Notification]:
    return list(
        db.execute(
            sa.select(Notification).where(
                Notification.notification_type == NotificationType.REVIEW_RECOMMENDED
            )
        )
        .scalars()
        .all()
    )


def test_marcar_un_tema_debil_emite_el_evento(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    _fallar_muchas_veces(db, usuario, contenido)

    resultado = ServicioDominio(db).recalcular_cascada(usuario.id, topic_id=contenido.tema.id)

    assert resultado.weakness_detected is True
    assert EventType.WEAKNESS_DETECTED in resultado.eventos
    evento = _eventos(db, EventType.WEAKNESS_DETECTED)
    assert len(evento) == 1
    assert evento[0].payload["topic_id"] == str(contenido.tema.id)


def test_marcar_un_tema_debil_propone_un_repaso(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    """El enlace lleva directo al repaso de ese tema: el cliente ya sabe abrirlo."""
    _fallar_muchas_veces(db, usuario, contenido)

    ServicioDominio(db).recalcular_cascada(usuario.id, topic_id=contenido.tema.id)

    creados = _avisos(db)
    assert len(creados) == 1
    assert creados[0].deep_link == f"review/{contenido.tema.id}"
    assert contenido.tema.title in creados[0].title
    assert creados[0].payload["topic_id"] == str(contenido.tema.id)


def test_seguir_fallando_no_repite_el_aviso(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    """Es la transición la que avisa, no el estado: si no, avisaría por respuesta."""
    _fallar_muchas_veces(db, usuario, contenido)
    servicio = ServicioDominio(db)
    # Los dos recálculos van en segundos distintos: la clave de `MASTERY_UPDATED`
    # lleva la marca de tiempo en segundos y dos seguidos chocarían entre sí por
    # un motivo que no tiene nada que ver con lo que se prueba aquí.
    primero = utcnow()
    servicio.recalcular_cascada(usuario.id, topic_id=contenido.tema.id, ahora=primero)

    registrar_respuesta(db, usuario, contenido, correcta=False)
    segundo = servicio.recalcular_cascada(
        usuario.id, topic_id=contenido.tema.id, ahora=primero + timedelta(seconds=5)
    )

    assert segundo.weakness_detected is False
    assert len(_avisos(db)) == 1


def test_un_tema_sano_no_avisa_de_nada(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    for _ in range(6):
        registrar_respuesta(db, usuario, contenido, correcta=True)

    resultado = ServicioDominio(db).recalcular_cascada(usuario.id, topic_id=contenido.tema.id)

    assert resultado.weakness_detected is False
    assert _eventos(db, EventType.WEAKNESS_DETECTED) == []
    assert _avisos(db) == []
    fila = db.execute(
        sa.select(UserTopicProgress).where(UserTopicProgress.topic_id == contenido.tema.id)
    ).scalar_one()
    assert fila.is_weak is False


# ---------------------------------------------------------------------------
# El territorio del mapa
# ---------------------------------------------------------------------------
#
# `TERRITORY_UNLOCKED` estaba en el catálogo de eventos y hay un logro
# contándolo, pero no lo emitía nadie: ese logro no podía desbloquearse jamás.
# Sale de la niebla con la misma condición que usa el mapa para pasar de FOGGED
# a DISCOVERED: el primer dominio del aprendiz en ese conocimiento.


def test_el_primer_dominio_saca_el_territorio_de_la_niebla(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    for _ in range(4):
        registrar_respuesta(db, usuario, contenido, correcta=True)

    resultado = ServicioDominio(db).recalcular_cascada(usuario.id, topic_id=contenido.tema.id)

    assert resultado.area_after > 0
    assert EventType.TERRITORY_UNLOCKED in resultado.eventos
    eventos = _eventos(db, EventType.TERRITORY_UNLOCKED)
    assert len(eventos) == 1
    assert eventos[0].payload["knowledge_area_id"] == str(contenido.area.id)


def test_el_territorio_no_se_redescubre(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    """Un dominio que sube, baja y vuelve a subir no vale dos veces."""
    servicio = ServicioDominio(db)
    primero = utcnow()
    for _ in range(4):
        registrar_respuesta(db, usuario, contenido, correcta=True)
    servicio.recalcular_cascada(usuario.id, topic_id=contenido.tema.id, ahora=primero)

    registrar_respuesta(db, usuario, contenido, correcta=True)
    servicio.recalcular_cascada(
        usuario.id, topic_id=contenido.tema.id, ahora=primero + timedelta(seconds=5)
    )

    assert len(_eventos(db, EventType.TERRITORY_UNLOCKED)) == 1


def test_intentarlo_y_fallar_tambien_descubre_el_territorio(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    """La cobertura cuenta aunque las respuestas no acierten, y está bien.

    El mapa da el territorio por descubierto en cuanto el aprendiz pone un pie,
    acierte o no. No hay aquí una prueba del caso contrario —territorio con
    niebla— porque no se puede montar: el dominio de un conocimiento no baja de
    cero ni sin evidencias, y el recálculo solo se dispara cuando el aprendiz ha
    hecho algo en ese conocimiento. La niebla es, literalmente, no haber pasado.
    """
    for _ in range(4):
        registrar_respuesta(db, usuario, contenido, correcta=False)

    resultado = ServicioDominio(db).recalcular_cascada(usuario.id, topic_id=contenido.tema.id)

    assert resultado.area_after > 0
    assert EventType.TERRITORY_UNLOCKED in resultado.eventos


# ---------------------------------------------------------------------------
# Áreas dominadas, de toda la cuenta
# ---------------------------------------------------------------------------
#
# `ACH_REALM_MASTER` compara `areas_mastered` del payload de `MASTERY_UPDATED`
# contra sus tres niveles (1/3/5), pero `ResultadoRecalculo` no tenía ese campo:
# el logro no podía cumplirse nunca, sin importar cuántas áreas dominara nadie.


def _area_dominada(db: Session, usuario: User, *, sufijo: str) -> UserAreaProgress:
    """Otra área, ya dominada, para probar que el conteo es de toda la cuenta."""
    area = KnowledgeArea(
        slug=f"otra-{sufijo}",
        name=f"Área {sufijo}",
        short_name=sufijo,
        category=KnowledgeCategory.DATA,
    )
    db.add(area)
    db.flush()
    fila = UserAreaProgress(
        user_id=usuario.id,
        knowledge_area_id=area.id,
        mastery=Decimal("90.00"),
        status=KnowledgeAreaStatus.MASTERED,
    )
    db.add(fila)
    db.flush()
    return fila


def test_areas_mastered_cuenta_toda_la_cuenta_no_solo_la_que_se_recalculo(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    """El área que se acaba de recalcular no está dominada; otras dos sí lo
    estaban de antes. El conteo tiene que ver las tres, no solo la tocada."""
    _area_dominada(db, usuario, sufijo="a")
    _area_dominada(db, usuario, sufijo="b")

    resultado = ServicioDominio(db).recalcular_cascada(usuario.id, topic_id=contenido.tema.id)

    assert resultado.area_status != KnowledgeAreaStatus.MASTERED
    assert resultado.areas_mastered == 2


def test_areas_mastered_viaja_en_el_payload_de_mastery_updated(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    """`ACH_REALM_MASTER` lee este campo del evento, no del `ResultadoRecalculo`
    en memoria: sin esto en el payload, la condición nunca se evalúa."""
    _area_dominada(db, usuario, sufijo="c")

    ServicioDominio(db).recalcular_cascada(usuario.id, topic_id=contenido.tema.id)

    eventos = _eventos(db, EventType.MASTERY_UPDATED)
    assert len(eventos) == 1
    assert eventos[0].payload["areas_mastered"] == 1
