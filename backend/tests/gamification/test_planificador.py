"""El barrido del reloj: a quién le toca un aviso y a qué hora local suya.

Lo que se prueba aquí es lo que no tiene evento. Que la racha esté en riesgo hoy
no es un suceso: es una ausencia, y una ausencia no dispara nada. El barrido es
el único que se entera.
"""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.enums import NotificationType, ReminderMode
from app.models.gamification import Notification, Streak, StreakDay
from app.models.identity import User, UserSettings
from app.modules.gamification import avisos, planificador
from app.modules.gamification.servicio_config import ServicioConfig

SANTIAGO = "America/Santiago"
HOY = dt.date(2026, 3, 10)


def _en(hora: dt.time, dia: dt.date = HOY) -> dt.datetime:
    """«Las `hora` del `dia` en Santiago», en UTC."""
    return avisos.instante_local(dia, hora, SANTIAGO)


def _racha(db: Session, usuario: User, *, dias: int, ultima: dt.date | None) -> Streak:
    fila = Streak(user_id=usuario.id, current_length=dias, last_active_date=ultima)
    db.add(fila)
    db.flush()
    return fila


def _avisos_de(db: Session, usuario: User, tipo: NotificationType) -> list[Notification]:
    return list(
        db.execute(
            sa.select(Notification).where(
                Notification.user_id == usuario.id,
                Notification.notification_type == tipo,
            )
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# La hora
# ---------------------------------------------------------------------------


def test_la_hora_habitual_es_la_mediana_de_las_primeras_actividades(
    db: Session, usuario: User
) -> None:
    """Tres días empezando a las 18, 19 y 20: la costumbre son las 19."""
    for indice, hora in enumerate((dt.time(18, 0), dt.time(19, 0), dt.time(20, 0))):
        dia = HOY - dt.timedelta(days=indice + 1)
        db.add(
            StreakDay(
                user_id=usuario.id,
                local_date=dia,
                first_activity_at=_en(hora, dia),
            )
        )
    db.flush()
    prefs = avisos.Preferencias(usuario_id=usuario.id, zona=SANTIAGO)

    assert planificador.hora_habitual(db, prefs, HOY, dias=14) == dt.time(19, 0)


def test_sin_dias_suficientes_no_hay_costumbre(db: Session, usuario: User) -> None:
    """Con dos días, una mediana es la hora de un día suelto disfrazada."""
    for indice in range(2):
        dia = HOY - dt.timedelta(days=indice + 1)
        db.add(
            StreakDay(
                user_id=usuario.id,
                local_date=dia,
                first_activity_at=_en(dt.time(18, 0), dia),
            )
        )
    db.flush()
    prefs = avisos.Preferencias(usuario_id=usuario.id, zona=SANTIAGO)

    assert planificador.hora_habitual(db, prefs, HOY, dias=14) is None


def test_el_modo_apagado_no_tiene_hora(db: Session, cfg: ServicioConfig, usuario: User) -> None:
    prefs = avisos.Preferencias(usuario_id=usuario.id, zona=SANTIAGO, modo=ReminderMode.OFF)

    assert planificador.hora_del_recordatorio(db, cfg, prefs, HOY) is None


def test_el_modo_inteligente_sin_datos_cae_en_la_hora_por_defecto(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    prefs = avisos.Preferencias(usuario_id=usuario.id, zona=SANTIAGO, modo=ReminderMode.SMART)

    assert planificador.hora_del_recordatorio(db, cfg, prefs, HOY) == dt.time(19, 0)


def test_el_modo_inteligente_desplaza_la_costumbre(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Costumbre a las 18:00 más los 45 minutos de `reminder.offset_min`."""
    for indice in range(3):
        dia = HOY - dt.timedelta(days=indice + 1)
        db.add(
            StreakDay(
                user_id=usuario.id,
                local_date=dia,
                first_activity_at=_en(dt.time(18, 0), dia),
            )
        )
    db.flush()
    prefs = avisos.Preferencias(usuario_id=usuario.id, zona=SANTIAGO, modo=ReminderMode.SMART)

    assert planificador.hora_del_recordatorio(db, cfg, prefs, HOY) == dt.time(18, 45)


def test_una_hora_manual_de_madrugada_se_aprieta_contra_la_franja(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Las 23:30 caerían en el silencio y saldrían al día siguiente: no es eso."""
    prefs = avisos.Preferencias(
        usuario_id=usuario.id,
        zona=SANTIAGO,
        modo=ReminderMode.MANUAL,
        hora_manual=dt.time(23, 30),
    )

    assert planificador.hora_del_recordatorio(db, cfg, prefs, HOY) == dt.time(21, 30)


# ---------------------------------------------------------------------------
# El barrido
# ---------------------------------------------------------------------------


def test_recuerda_a_quien_estudio_ayer_y_hoy_todavia_no(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """El día dos: ayer sí, hoy aún no, y su reloj local ya pasó por las 19:00."""
    _racha(db, usuario, dias=4, ultima=HOY - dt.timedelta(days=1))

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(19, 30)))

    assert cuenta["recordatorios"] == 1
    creados = _avisos_de(db, usuario, NotificationType.STREAK_REMINDER)
    assert len(creados) == 1
    assert "4 días" in creados[0].title
    assert creados[0].deep_link == "streak"
    assert creados[0].local_date == HOY


def test_no_recuerda_antes_de_su_hora(db: Session, cfg: ServicioConfig, usuario: User) -> None:
    """A las diez de la mañana todavía le queda todo el día por delante."""
    _racha(db, usuario, dias=4, ultima=HOY - dt.timedelta(days=1))

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(10, 0)))

    assert cuenta["recordatorios"] == 0


def test_no_recuerda_a_quien_ya_estudio_hoy(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    _racha(db, usuario, dias=4, ultima=HOY)

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(19, 30)))

    assert cuenta["recordatorios"] == 0


def test_dos_barridos_seguidos_no_duplican_el_recordatorio(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """La marca antifatiga y la clave única sostienen esto por separado."""
    _racha(db, usuario, dias=4, ultima=HOY - dt.timedelta(days=1))

    planificador.planificar(db, cfg, momento=_en(dt.time(19, 30)))
    segunda = planificador.planificar(db, cfg, momento=_en(dt.time(20, 0)))

    assert segunda["recordatorios"] == 0
    assert len(_avisos_de(db, usuario, NotificationType.STREAK_REMINDER)) == 1


def test_el_recordatorio_deja_la_marca_antifatiga(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """`last_reminder_sent_on` nunca se escribía; ahora es quien lleva la cuenta."""
    _racha(db, usuario, dias=4, ultima=HOY - dt.timedelta(days=1))

    planificador.planificar(db, cfg, momento=_en(dt.time(19, 30)))

    ajustes = db.execute(
        sa.select(UserSettings).where(UserSettings.user_id == usuario.id)
    ).scalar_one()
    assert ajustes.last_reminder_sent_on == HOY


def test_quien_apago_los_avisos_de_racha_no_recibe_nada(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    db.add(UserSettings(user_id=usuario.id, notify_streak=False))
    _racha(db, usuario, dias=4, ultima=HOY - dt.timedelta(days=1))

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(19, 30)))

    assert cuenta["recordatorios"] == 0
    assert _avisos_de(db, usuario, NotificationType.STREAK_REMINDER) == []


def test_el_dia_de_gracia_todavia_merece_recordatorio(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Dos días sin estudiar, pero queda la gracia del mes: aún se puede salvar."""
    _racha(db, usuario, dias=9, ultima=HOY - dt.timedelta(days=2))

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(19, 30)))

    assert cuenta["recordatorios"] == 1
    creados = _avisos_de(db, usuario, NotificationType.STREAK_REMINDER)
    assert "gracia" in creados[0].body


def test_sin_gracia_el_segundo_dia_ya_no_promete_nada(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """La gracia del mes ya se gastó: mañana la racha está rota igual."""
    perdido = HOY - dt.timedelta(days=1)
    racha = _racha(db, usuario, dias=9, ultima=HOY - dt.timedelta(days=2))
    racha.grace_used_for_month = f"{perdido.year:04d}-{perdido.month:02d}"
    db.flush()

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(19, 30)))

    assert cuenta["recordatorios"] == 0


# ---------------------------------------------------------------------------
# Última llamada
# ---------------------------------------------------------------------------


def test_la_ultima_llamada_pide_permiso_expreso(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """`last_call_enabled` nace apagado: sin pedirlo no llega."""
    _racha(db, usuario, dias=10, ultima=HOY - dt.timedelta(days=1))

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(21, 40)))

    assert cuenta["ultimas_llamadas"] == 0


def test_la_ultima_llamada_llega_a_quien_la_pidio(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    db.add(UserSettings(user_id=usuario.id, last_call_enabled=True))
    _racha(db, usuario, dias=10, ultima=HOY - dt.timedelta(days=1))

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(21, 40)))

    assert cuenta["ultimas_llamadas"] == 1
    assert len(_avisos_de(db, usuario, NotificationType.STREAK_LAST_CALL)) == 1


def test_la_ultima_llamada_exige_una_racha_ya_larga(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """`last_call.min_streak` es 7: con tres días no hay tanto que perder."""
    db.add(UserSettings(user_id=usuario.id, last_call_enabled=True))
    _racha(db, usuario, dias=3, ultima=HOY - dt.timedelta(days=1))

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(21, 40)))

    assert cuenta["ultimas_llamadas"] == 0


def test_pasada_la_hora_de_silencio_la_ultima_llamada_ya_no_sirve(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """A las 22:30 se correría a las 08:00 del día siguiente: ya no es aviso."""
    db.add(UserSettings(user_id=usuario.id, last_call_enabled=True))
    _racha(db, usuario, dias=10, ultima=HOY - dt.timedelta(days=1))

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(22, 30)))

    assert cuenta["ultimas_llamadas"] == 0


# ---------------------------------------------------------------------------
# Reactivación
# ---------------------------------------------------------------------------


def test_a_los_tres_dias_llega_un_aviso_de_vuelta(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    _racha(db, usuario, dias=0, ultima=HOY - dt.timedelta(days=3))

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(19, 30)))

    assert cuenta["reactivaciones"] == 1
    creados = _avisos_de(db, usuario, NotificationType.REACTIVATION)
    assert creados[0].payload["days_away"] == 3
    assert creados[0].deep_link == "home"


def test_a_los_cuatro_dias_no_llega_nada(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Los escalones son 3, 7 y 30, no «cada día a partir del tercero»."""
    _racha(db, usuario, dias=0, ultima=HOY - dt.timedelta(days=4))

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(19, 30)))

    assert cuenta["reactivaciones"] == 0


def test_quien_nunca_estudio_se_cuenta_desde_que_creo_el_personaje(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Sin `last_active_date` no hay racha, pero sí hay alguien a quien recuperar."""
    racha = _racha(db, usuario, dias=0, ultima=None)
    racha.created_at = _en(dt.time(12, 0), HOY - dt.timedelta(days=3))
    db.flush()

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(19, 30)))

    assert cuenta["reactivaciones"] == 1


# ---------------------------------------------------------------------------
# Misiones
# ---------------------------------------------------------------------------


def test_el_aviso_de_misiones_es_matutino_y_opcional(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    db.add(UserSettings(user_id=usuario.id, notify_missions=True))
    _racha(db, usuario, dias=4, ultima=HOY - dt.timedelta(days=1))

    temprano = planificador.planificar(db, cfg, momento=_en(dt.time(8, 30)))
    assert temprano["misiones"] == 1
    assert _avisos_de(db, usuario, NotificationType.DAILY_MISSION)[0].deep_link == "missions"


def test_sin_pedirlo_no_hay_aviso_de_misiones(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """`notify_missions` es el único interruptor que nace apagado."""
    _racha(db, usuario, dias=4, ultima=HOY - dt.timedelta(days=1))

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(8, 30)))

    assert cuenta["misiones"] == 0
