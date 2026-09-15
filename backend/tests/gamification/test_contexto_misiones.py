"""Las misiones que se reparten tienen que ser posibles.

Ocho de las trece plantillas diarias llevan predicado de elegibilidad, y nadie
construía el diccionario contra el que se evalúan: `listar_misiones` pedía la
asignación sin contexto y `_elegible` daba por cumplido todo predicado que no
conociera. El aprendiz del día uno recibía «repasa un tema que se te resiste» sin
tener ningún tema flojo, y «supera un desafío» cuando los desafíos ni siquiera
existen como tabla.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models.enums import MissionScope
from app.models.gamification import Streak
from app.models.identity import User
from app.modules.gamification import misiones

HOY = dt.date(2026, 3, 10)


def _candidatas(db: Session, contexto: dict) -> set[str]:
    return {
        p.code
        for p in misiones.plantillas_candidatas(db, MissionScope.DAILY, contexto=contexto)
    }


# ---------------------------------------------------------------------------
# El contexto
# ---------------------------------------------------------------------------


def test_un_aprendiz_recien_llegado_no_cumple_ningun_predicado(
    db: Session, usuario: User
) -> None:
    """Sin progreso no hay tema flojo, ni prueba pendiente, ni racha."""
    contexto = misiones.contexto_de(db, usuario.id, HOY)

    assert contexto["has_weak_topic"] is False
    assert contexto["has_available_assessment"] is False
    assert contexto["has_unstarted_topic"] is False
    assert contexto["active_areas"] == 0
    assert contexto["has_failed_questions"] == 0
    assert contexto["streak"] == 0


def test_los_desafios_no_existen_y_el_contexto_lo_dice(db: Session, usuario: User) -> None:
    """No hay tabla de desafíos: la misión que los pide es imposible por ahora."""
    assert misiones.contexto_de(db, usuario.id, HOY)["has_available_challenge"] is False


def test_la_racha_del_contexto_no_se_fia_de_current_length(
    db: Session, usuario: User
) -> None:
    """`current_length` no caduca solo: quien desapareció hace un mes sigue en 30."""
    db.add(
        Streak(
            user_id=usuario.id,
            current_length=30,
            last_active_date=HOY - dt.timedelta(days=30),
        )
    )
    db.flush()

    assert misiones.contexto_de(db, usuario.id, HOY)["streak"] == 0


def test_una_racha_viva_si_cuenta(db: Session, usuario: User) -> None:
    db.add(
        Streak(user_id=usuario.id, current_length=9, last_active_date=HOY - dt.timedelta(days=1))
    )
    db.flush()

    assert misiones.contexto_de(db, usuario.id, HOY)["streak"] == 9


# ---------------------------------------------------------------------------
# El filtrado
# ---------------------------------------------------------------------------


def test_sin_contexto_se_cuela_todo_lo_imposible(
    db: Session, usuario: User, crear_plantilla_mision
) -> None:
    """El comportamiento viejo, fijado aquí para que se vea lo que se arregló."""
    crear_plantilla_mision("T_LIBRE")
    crear_plantilla_mision("T_DESAFIO", eligibility=["has_available_challenge"])
    crear_plantilla_mision("T_FLOJO", eligibility=["has_weak_topic"])

    assert _candidatas(db, {}) >= {"T_LIBRE", "T_DESAFIO", "T_FLOJO"}


def test_con_contexto_las_imposibles_quedan_fuera(
    db: Session, usuario: User, crear_plantilla_mision
) -> None:
    crear_plantilla_mision("T_LIBRE")
    crear_plantilla_mision("T_DESAFIO", eligibility=["has_available_challenge"])
    crear_plantilla_mision("T_FLOJO", eligibility=["has_weak_topic"])

    codigos = _candidatas(db, misiones.contexto_de(db, usuario.id, HOY))

    assert "T_LIBRE" in codigos
    assert "T_DESAFIO" not in codigos
    assert "T_FLOJO" not in codigos


def test_un_predicado_numerico_compara_de_verdad(
    db: Session, usuario: User, crear_plantilla_mision
) -> None:
    """«racha >= 3»: con dos días no entra, con tres sí."""
    crear_plantilla_mision("T_RACHA", eligibility=[{"predicate": "streak", "value": 3}])

    assert "T_RACHA" not in _candidatas(db, {"streak": 2})
    assert "T_RACHA" in _candidatas(db, {"streak": 3})
    assert "T_RACHA" in _candidatas(db, {"streak": 10})


def test_un_predicado_desconocido_sigue_pasando_pero_deja_rastro(
    db: Session, usuario: User, crear_plantilla_mision, caplog
) -> None:
    """Preferimos una misión de más a dejar a alguien sin misiones; en voz alta."""
    crear_plantilla_mision("T_RARO", eligibility=["predicado_que_nadie_calcula"])

    with caplog.at_level("WARNING"):
        codigos = _candidatas(db, misiones.contexto_de(db, usuario.id, HOY))

    assert "T_RARO" in codigos
    assert "predicado_desconocido" in caplog.text
