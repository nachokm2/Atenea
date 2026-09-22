"""El panel: la tarjeta de continuar y el número de la campana.

Dos agujeros del día dos vivían aquí. El primero: cuando la ruta se terminaba, la
tarjeta «continuar tu aventura» era un callejón sin salida —una felicitación sin
nada que tocar—, y el repaso espaciado no tenía ninguna puerta en la pantalla de
Inicio. El segundo: `DashboardOut` no traía el número de avisos sin leer, así que
la campana no se encendía nunca hasta que el aprendiz abría la bandeja por su
cuenta, que es justo lo contrario de para lo que sirve una campana.
"""

from __future__ import annotations

import datetime as dt
import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.enums import NotificationType, ProgressState, StreakChange
from app.models.gamification import Streak
from app.models.identity import User
from app.models.progress import UserPathProgress, UserTopicProgress
from app.modules.gamification import avisos
from app.modules.gamification.servicio_config import ServicioConfig
from app.modules.progress.panel import (
    CONTINUAR_LECCION,
    CONTINUAR_REPASO,
    CONTINUAR_RUTA_COMPLETA,
    ServicioPanel,
)
from app.modules.progress.schemas import DashboardOut

ZONA = "America/Santiago"

#: Un día cualquiera, a una hora en la que nadie está en silencio.
MEDIODIA = dt.date(2026, 3, 10)


def _ruta_del_usuario(
    db: Session, usuario: User, contenido, *, estado: ProgressState
) -> UserPathProgress:
    fila = UserPathProgress(
        user_id=usuario.id,
        learning_path_id=contenido.ruta.id,
        status=estado,
        current_module_id=contenido.modulo.id,
        current_lesson_id=None if estado == ProgressState.COMPLETED else contenido.lecciones[0].id,
    )
    db.add(fila)
    db.flush()
    return fila


def _tema_flojo(db: Session, usuario: User, contenido, *, dominio: float) -> UserTopicProgress:
    fila = UserTopicProgress(
        user_id=usuario.id,
        topic_id=contenido.tema.id,
        module_id=contenido.modulo.id,
        knowledge_area_id=contenido.area.id,
        mastery=dominio,
        evidence_count=5,
    )
    db.add(fila)
    db.flush()
    return fila


# ---------------------------------------------------------------------------
# La tarjeta de continuar
# ---------------------------------------------------------------------------


def test_una_leccion_en_curso_no_trae_tema(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    """`topic_id` solo viaja en una tarjeta de repaso; en el hilo normal es nulo."""
    _ruta_del_usuario(db, usuario, contenido, estado=ProgressState.IN_PROGRESS)

    panel = ServicioPanel(db).construir(usuario.id, ZONA)

    assert panel.continue_action.type == CONTINUAR_LECCION
    assert panel.continue_action.topic_id is None


def test_la_ruta_terminada_propone_repasar_el_tema_mas_flojo(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    """Era un callejón sin salida: ahora la salida es el repaso."""
    _ruta_del_usuario(db, usuario, contenido, estado=ProgressState.COMPLETED)
    _tema_flojo(db, usuario, contenido, dominio=45.0)

    panel = ServicioPanel(db).construir(usuario.id, ZONA)

    assert panel.continue_action.type == CONTINUAR_REPASO
    assert panel.continue_action.topic_id == contenido.tema.id
    assert panel.continue_action.title == contenido.tema.title
    # La recompensa que se enseña es la del repaso, no la de una lección.
    assert panel.continue_action.reward_preview["xp"] == 30


def test_la_ruta_terminada_sin_temas_flojos_se_queda_como_estaba(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    """Un tema por encima del umbral de riesgo no se propone repasar."""
    _ruta_del_usuario(db, usuario, contenido, estado=ProgressState.COMPLETED)
    _tema_flojo(db, usuario, contenido, dominio=92.0)

    panel = ServicioPanel(db).construir(usuario.id, ZONA)

    assert panel.continue_action.type == CONTINUAR_RUTA_COMPLETA
    assert panel.continue_action.topic_id is None


def test_un_tema_sin_evidencias_no_es_un_repaso(
    db: Session, config_sembrada: None, usuario: User, contenido
) -> None:
    """Dominio cero por no haberlo tocado nunca no es debilidad: es no empezado."""
    _ruta_del_usuario(db, usuario, contenido, estado=ProgressState.COMPLETED)
    fila = _tema_flojo(db, usuario, contenido, dominio=0.0)
    fila.evidence_count = 0
    db.flush()

    panel = ServicioPanel(db).construir(usuario.id, ZONA)

    assert panel.continue_action.type == CONTINUAR_RUTA_COMPLETA


# ---------------------------------------------------------------------------
# La campana
# ---------------------------------------------------------------------------


def test_el_panel_trae_los_avisos_sin_leer(
    db: Session, config_sembrada: None, usuario: User
) -> None:
    """Sin este número la campana del Inicio no se enciende nunca."""
    cfg = ServicioConfig(db)
    for indice in range(2):
        creado = avisos.crear(
            db,
            usuario_id=usuario.id,
            tipo=NotificationType.SYSTEM,
            titulo="Aviso",
            cuerpo="Cuerpo.",
            clave=f"panel:{uuid.uuid4().hex}:{indice}",
            cfg=cfg,
            # Mediodía, y fijado a propósito. Sin esto la prueba usaba la hora
            # de quien la ejecutara: pasadas las diez de la noche el aviso cae en
            # horas de silencio, nace programado para las ocho de la mañana en
            # vez de entregado, y la campana marca cero con toda la razón. La
            # prueba pasaba de día y fallaba de noche.
            momento=avisos.instante_local(MEDIODIA, dt.time(12, 0), ZONA),
        )
        assert creado is not None

    panel = ServicioPanel(db).construir(usuario.id, ZONA)

    assert panel.unread_notifications == 2


def test_un_aviso_programado_no_enciende_la_campana(
    db: Session, config_sembrada: None, usuario: User
) -> None:
    """Lo que todavía no se ha entregado no está esperando a nadie."""
    creado = avisos.crear(
        db,
        usuario_id=usuario.id,
        tipo=NotificationType.SYSTEM,
        titulo="Aviso",
        cuerpo="Cuerpo.",
        clave=f"panel-futuro:{uuid.uuid4().hex}",
        programada_para=utcnow() + timedelta(hours=3),
        cfg=ServicioConfig(db),
    )
    assert creado is not None

    panel = ServicioPanel(db).construir(usuario.id, ZONA)

    assert panel.unread_notifications == 0


# ---------------------------------------------------------------------------
# El bloque `streak`: racha anterior y motivo del último cambio
# ---------------------------------------------------------------------------


def test_el_bloque_streak_trae_la_racha_anterior_y_su_motivo(
    db: Session, config_sembrada: None, usuario: User
) -> None:
    """`previous_length` y `last_change` se calculan en `rachas.py` y antes
    morían ahí: el panel solo traía `{current, best, status, day_status}`."""
    db.add(
        Streak(
            user_id=usuario.id,
            current_length=1,
            best_length=12,
            previous_length=12,
            last_change=StreakChange.BROKEN,
            started_on=dt.date(2026, 3, 10),
            last_active_date=MEDIODIA,
            total_active_days=20,
        )
    )
    db.flush()

    panel = ServicioPanel(db).construir(usuario.id, ZONA)

    assert panel.streak.previous_length == 12
    assert panel.streak.last_change == StreakChange.BROKEN
    assert panel.streak.started_on == dt.date(2026, 3, 10)

    # La forma que de verdad viaja por HTTP: no solo el dataclass interno.
    salida = DashboardOut.model_validate(panel)
    assert salida.streak.previous_length == 12
    assert salida.streak.last_change == StreakChange.BROKEN
    assert salida.streak.started_on == dt.date(2026, 3, 10)


def test_sin_fila_de_racha_el_bloque_streak_no_inventa_un_cambio(
    db: Session, config_sembrada: None, usuario: User
) -> None:
    """Usuario nuevo, sin `Streak`: los tres campos salen en su default."""
    panel = ServicioPanel(db).construir(usuario.id, ZONA)

    assert panel.streak.previous_length == 0
    assert panel.streak.last_change is None
    assert panel.streak.started_on is None
