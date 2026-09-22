"""`GET /streak`: la racha rota se guardaba y no llegaba a ningún lado.

Tercer rastreo (22-09). `Streak.previous_length` se calcula de verdad al
romperse una racha (`rachas._cerrar_racha`) y `Streak.last_change` se
actualiza en cada `activar_dia` — pero `StreakOut` nunca serializaba ninguno
de los dos, ni tampoco `started_on`. El cliente Flutter ya tenía el parseo
esperando `previous_length` (comentario de diseño incluido: "Tu mejor marca
sigue siendo 12 días") y una advertencia entera —"Tu racha se reinició"— que
depende de `last_change == "broken"` y que por eso nunca se pintaba: el campo
del que depende jamás llegaba en la respuesta real.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.enums import StreakChange
from app.models.gamification import Streak
from app.models.identity import User
from app.modules.gamification.router import obtener_racha

HOY = date(2026, 9, 22)


def test_streak_out_trae_racha_anterior_y_motivo_del_cambio(
    db: Session, usuario: User
) -> None:
    """Una racha recién rota expone su longitud previa y el motivo del cambio."""
    fila = Streak(
        user_id=usuario.id,
        current_length=1,
        best_length=12,
        previous_length=12,
        last_change=StreakChange.BROKEN,
        started_on=HOY,
        last_active_date=HOY,
        total_active_days=20,
    )
    db.add(fila)
    db.flush()

    salida = obtener_racha(db, usuario)

    assert salida.previous_length == 12
    assert salida.last_change == StreakChange.BROKEN
    assert salida.started_on == HOY


def test_streak_out_sin_racha_previa_no_inventa_un_cambio(
    db: Session, usuario: User
) -> None:
    """Sin fila de racha (usuario nuevo), los tres campos salen en su default."""
    salida = obtener_racha(db, usuario)

    assert salida.previous_length == 0
    assert salida.last_change is None
    assert salida.started_on is None


def test_streak_out_no_confunde_una_racha_extendida_con_una_rota(
    db: Session, usuario: User
) -> None:
    """Mutación: si `last_change` no viajara, esta prueba no lo notaría."""
    fila = Streak(
        user_id=usuario.id,
        current_length=6,
        best_length=6,
        previous_length=0,
        last_change=StreakChange.EXTENDED,
        started_on=HOY - timedelta(days=5),
        last_active_date=HOY,
        total_active_days=6,
    )
    db.add(fila)
    db.flush()

    salida = obtener_racha(db, usuario)

    assert salida.last_change == StreakChange.EXTENDED
    assert salida.last_change != StreakChange.BROKEN
