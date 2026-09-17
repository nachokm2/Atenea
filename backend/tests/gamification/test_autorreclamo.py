"""Autorreclamar una misión tiene que pagarla.

`missions.claim.auto_on_expiry` está sembrado en `True` y promete que «al
expirar el periodo se reclaman solas las misiones completadas». Y se reclamaban:
`expirar_vencidas` movía la fila a `CLAIMED` y ahí se acababa. Pero la
recompensa no la otorga el estado de la fila sino el evento `MISSION_CLAIMED`,
que solo emitía el endpoint de reclamo manual.

O sea que el aprendiz cumplía su misión del día, se le pasaba reclamarla antes
de medianoche, y la perdía entera. Y si lo intentaba al día siguiente recibía un
409, porque `claimed_at` ya no era nulo. Silencioso por los dos lados.

Dos detalles decían que era un olvido y no una decisión: el payload del reclamo
manual declara un campo `auto` que nadie ponía nunca a `True`, y **no había una
sola prueba sobre `expirar_vencidas`** en todo el proyecto. Esta es la primera.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.enums import EventType, MissionStatus
from app.models.gamification import DomainEvent, UserMission
from app.models.identity import User
from app.modules.gamification import misiones
from app.modules.gamification.router import _pagar_autorreclamadas
from app.modules.gamification.servicio_config import ServicioConfig


@pytest.fixture
def mision_cumplida_y_vencida(db: Session, usuario: User, crear_plantilla_mision):
    """Una diaria cumplida que expiró anoche sin que nadie la reclamara.

    Es el caso exacto del aprendiz que hace su lección por la tarde, cierra la
    aplicación sin pasar por el tablón, y vuelve al día siguiente.
    """
    plantilla = crear_plantilla_mision(f"D-AUTO-{uuid.uuid4().hex[:6]}")
    fila = UserMission(
        user_id=usuario.id,
        template_id=plantilla.id,
        template_code=plantilla.code,
        template_version=1,
        scope=plantilla.scope,
        title="Completa 2 lecciones",
        target=2,
        progress=2,
        status=MissionStatus.COMPLETED,
        reward_xp=40,
        reward_gold=15,
        expires_at=utcnow() - timedelta(hours=1),
    )
    db.add(fila)
    db.flush()
    return fila


def _eventos_de_reclamo(db: Session, mision: UserMission) -> list[DomainEvent]:
    """Los eventos de pago que existen para esta misión."""
    return list(
        db.execute(
            sa.select(DomainEvent).where(DomainEvent.event_type == EventType.MISSION_CLAIMED)
        )
        .scalars()
        .all()
    )


def test_expirar_deja_la_mision_reclamada(
    db: Session, cfg: ServicioConfig, usuario: User, mision_cumplida_y_vencida: UserMission
) -> None:
    """Lo que ya hacía, y que por sí solo era el problema."""
    afectadas = misiones.expirar_vencidas(db, cfg, usuario.id)

    assert mision_cumplida_y_vencida.status == MissionStatus.CLAIMED
    assert mision_cumplida_y_vencida.claimed_at is not None
    # El contrato entre el módulo y quien lo llama: las autorreclamadas son las
    # que vuelven con `CLAIMED`, y son las que hay que pagar.
    assert [m.id for m in afectadas if m.status == MissionStatus.CLAIMED] == [
        mision_cumplida_y_vencida.id
    ]


def test_el_autorreclamo_paga(
    db: Session, cfg: ServicioConfig, usuario: User, mision_cumplida_y_vencida: UserMission
) -> None:
    """La prueba que faltaba: reclamar sola tiene que emitir el evento del pago."""
    assert _eventos_de_reclamo(db, mision_cumplida_y_vencida) == []

    _pagar_autorreclamadas(db, cfg, usuario.id)

    emitidos = _eventos_de_reclamo(db, mision_cumplida_y_vencida)
    assert len(emitidos) == 1, "sin este evento la recompensa no se otorga nunca"

    payload = emitidos[0].payload or {}
    assert payload["auto"] is True, "el campo que estaba declarado y nadie ponía"
    assert payload["user_mission_id"] == str(mision_cumplida_y_vencida.id)
    assert payload["reward"] == {"xp": 40, "gold": 15}


def test_abrir_el_tablon_dos_veces_no_paga_dos_veces(
    db: Session, cfg: ServicioConfig, usuario: User, mision_cumplida_y_vencida: UserMission
) -> None:
    """La clave de idempotencia cuelga de la misión, no del momento.

    Importa porque esto vive en una petición de lectura: `GET /missions` se pide
    al abrir el tablón, al volver a primer plano y en cada reintento de red.
    """
    _pagar_autorreclamadas(db, cfg, usuario.id)
    _pagar_autorreclamadas(db, cfg, usuario.id)
    _pagar_autorreclamadas(db, cfg, usuario.id)

    assert len(_eventos_de_reclamo(db, mision_cumplida_y_vencida)) == 1


def test_una_mision_viva_no_se_paga(
    db: Session, cfg: ServicioConfig, usuario: User, crear_plantilla_mision
) -> None:
    """Cumplida pero sin vencer: la reclama el aprendiz, con su celebración."""
    plantilla = crear_plantilla_mision(f"D-VIVA-{uuid.uuid4().hex[:6]}")
    viva = UserMission(
        user_id=usuario.id,
        template_id=plantilla.id,
        template_code=plantilla.code,
        template_version=1,
        scope=plantilla.scope,
        title="Completa 2 lecciones",
        target=2,
        progress=2,
        status=MissionStatus.COMPLETED,
        reward_xp=40,
        reward_gold=15,
        expires_at=utcnow() + timedelta(hours=6),
    )
    db.add(viva)
    db.flush()

    _pagar_autorreclamadas(db, cfg, usuario.id)

    assert viva.status == MissionStatus.COMPLETED
    assert _eventos_de_reclamo(db, viva) == []


def test_una_mision_sin_cumplir_expira_sin_pagar(
    db: Session, cfg: ServicioConfig, usuario: User, crear_plantilla_mision
) -> None:
    """Vencida a medias: expira, y no cobra nada. El autorreclamo no regala."""
    plantilla = crear_plantilla_mision(f"D-MEDIAS-{uuid.uuid4().hex[:6]}")
    incompleta = UserMission(
        user_id=usuario.id,
        template_id=plantilla.id,
        template_code=plantilla.code,
        template_version=1,
        scope=plantilla.scope,
        title="Completa 2 lecciones",
        target=2,
        progress=1,
        status=MissionStatus.ACTIVE,
        reward_xp=40,
        reward_gold=15,
        expires_at=utcnow() - timedelta(hours=1),
    )
    db.add(incompleta)
    db.flush()

    _pagar_autorreclamadas(db, cfg, usuario.id)

    assert incompleta.status == MissionStatus.EXPIRED
    assert _eventos_de_reclamo(db, incompleta) == []
