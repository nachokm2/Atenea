"""`activar_dia` y el ajuste de racha por viaje hacia el este (§6.10).

`viaje_hacia_el_este` existía como parámetro de `activar_dia` y su único
llamador (`motor.py`) nunca se lo pasaba: quien viajaba al este y perdía un
día por el salto horario gastaba el día de gracia del mes en vez de recibir
la protección que el contrato promete por viajar. `activar_dia` ya no acepta
ese parámetro externo — lo calcula él mismo, con `users.previous_timezone` y
`timezone_changed_at`, que `cambiar_zona_horaria` (identity) ya escribía sin
que nadie los leyera del otro lado.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.core.time import UTC
from app.models.enums import DayStatus, StreakChange
from app.models.gamification import Streak
from app.modules.gamification import rachas

pytestmark = pytest.mark.db

#: Un jueves cualquiera, lejos de cualquier borde de año o de DST.
HOY = date(2026, 9, 24)

#: Dentro de la ventana del día perdido (`hoy - 2` .. `hoy`).
CAMBIO_RECIENTE = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)

#: Fuera de la ventana: catorce días antes de `hoy`.
CAMBIO_VIEJO = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def _racha_con_un_dia_perdido(db, usuario) -> Streak:
    """Deja la racha justo en la rama de `hoy - 2`: un día (`hoy - 1`) sin marcar."""
    fila = Streak(
        user_id=usuario.id,
        current_length=5,
        best_length=5,
        last_active_date=HOY - timedelta(days=2),
        started_on=HOY - timedelta(days=6),
        total_active_days=5,
    )
    db.add(fila)
    db.flush()
    return fila


def test_viaje_hacia_el_este_protege_el_dia_perdido(db, cfg, usuario):
    """Santiago → Tokio (~12-13 h al este) habilita el ajuste por viaje."""
    _racha_con_un_dia_perdido(db, usuario)
    usuario.previous_timezone = "America/Santiago"
    usuario.timezone = "Asia/Tokyo"
    usuario.timezone_changed_at = CAMBIO_RECIENTE
    db.flush()

    resultado = rachas.activar_dia(db, cfg, usuario.id, HOY)

    assert resultado.change is StreakChange.TRAVEL_SKIP
    assert resultado.current == 6

    perdido = HOY - timedelta(days=1)
    dia_perdido = rachas.obtener_o_crear_dia(db, cfg, usuario.id, perdido)
    assert dia_perdido.day_status is DayStatus.TRAVEL


def test_viaje_hacia_el_oeste_no_protege_nada(db, cfg, usuario):
    """Tokio → Santiago es hacia el oeste: no es el mismo problema y no protege.

    Sin esto, cualquier cambio de zona —sin importar la dirección— podría
    activar el ajuste por error. El día perdido cae a la gracia del mes, como
    si no hubiera pasado nada especial de zona horaria.
    """
    _racha_con_un_dia_perdido(db, usuario)
    usuario.previous_timezone = "Asia/Tokyo"
    usuario.timezone = "America/Santiago"
    usuario.timezone_changed_at = CAMBIO_RECIENTE
    db.flush()

    resultado = rachas.activar_dia(db, cfg, usuario.id, HOY)

    assert resultado.change is StreakChange.GRACE_USED
    assert resultado.current == 6


def test_un_cambio_de_zona_viejo_no_protege_el_dia_de_hoy(db, cfg, usuario):
    """El cambio de zona tiene que caer dentro de la ventana del día perdido.

    Uno de hace dos semanas no explica que ayer no hubiera actividad: sin la
    ventana, cualquier viaje pasado protegería una racha rota mucho después.
    """
    _racha_con_un_dia_perdido(db, usuario)
    usuario.previous_timezone = "America/Santiago"
    usuario.timezone = "Asia/Tokyo"
    usuario.timezone_changed_at = CAMBIO_VIEJO
    db.flush()

    resultado = rachas.activar_dia(db, cfg, usuario.id, HOY)

    assert resultado.change is StreakChange.GRACE_USED
