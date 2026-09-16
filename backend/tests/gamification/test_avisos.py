"""La bandeja: quién recibe un aviso, cuándo lo ve y cuándo deja de verlo.

Las cuatro puertas de `avisos.crear` (interruptor, silencio, tope, idempotencia)
y la diferencia entre programar y entregar, que es donde estaba el agujero: una
notificación con `scheduled_for` en el futuro existía en la tabla y nadie la
pasaba nunca a entregada.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import to_zone
from app.models.enums import (
    EventStatus,
    EventType,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)
from app.models.gamification import DomainEvent, Notification
from app.models.identity import User, UserSettings
from app.modules.gamification import avisos
from app.modules.gamification.router import listar_notificaciones, marcar_todas_leidas
from app.modules.gamification.servicio_config import ServicioConfig

SANTIAGO = "America/Santiago"

#: Un día cualquiera, y su mediodía. Toda prueba de esta suite trabaja sobre un
#: reloj fijado: sin él, las que esperan un aviso ENTREGADO pasaban de día y
#: fallaban de noche, porque a partir de las diez el aviso cae en horas de
#: silencio y nace programado para la mañana siguiente. Una prueba que depende de
#: cuándo se ejecuta no prueba nada.
DIA = dt.date(2026, 3, 10)


def _instante(dia: dt.date, hora: dt.time, zona: str = SANTIAGO) -> dt.datetime:
    """Atajo legible: «las 19:00 del martes en Santiago», en UTC."""
    return avisos.instante_local(dia, hora, zona)


def _crear(db: Session, cfg: ServicioConfig, usuario: User, **kwargs) -> Notification | None:
    base = {
        "usuario_id": usuario.id,
        "tipo": NotificationType.SYSTEM,
        "titulo": "Aviso",
        "cuerpo": "Cuerpo del aviso.",
        "clave": f"prueba:{uuid.uuid4().hex}",
        "cfg": cfg,
        "momento": _instante(DIA, dt.time(12, 0)),
    }
    base.update(kwargs)
    return avisos.crear(db, **base)


# ---------------------------------------------------------------------------
# Horas de silencio
# ---------------------------------------------------------------------------


def test_el_silencio_cruza_la_medianoche() -> None:
    """De 22:00 a 08:00 el silencio abarca las dos mitades de la noche."""
    inicio, fin = dt.time(22, 0), dt.time(8, 0)
    assert avisos.en_silencio(dt.time(23, 30), inicio, fin) is True
    assert avisos.en_silencio(dt.time(3, 0), inicio, fin) is True
    assert avisos.en_silencio(dt.time(8, 0), inicio, fin) is False
    assert avisos.en_silencio(dt.time(19, 0), inicio, fin) is False
    assert avisos.en_silencio(dt.time(21, 59), inicio, fin) is False


def test_una_franja_de_silencio_vacia_no_silencia_nada() -> None:
    """`PUT /settings` admite inicio == fin; eso no puede callar el día entero."""
    assert avisos.en_silencio(dt.time(3, 0), dt.time(9, 0), dt.time(9, 0)) is False


def test_el_aviso_de_medianoche_se_corre_al_final_del_silencio(usuario: User) -> None:
    """Las 23:30 salen a las 08:00 del día siguiente, no se pierden."""
    prefs = avisos.Preferencias(usuario_id=usuario.id, zona=SANTIAGO)
    tarde = _instante(dt.date(2026, 3, 10), dt.time(23, 30))

    corrido = avisos.fuera_del_silencio(tarde, prefs)

    local = to_zone(corrido, SANTIAGO)
    assert local.date() == dt.date(2026, 3, 11)
    assert local.time() == dt.time(8, 0)


def test_el_aviso_de_madrugada_sale_esa_misma_manana(usuario: User) -> None:
    """Las 03:00 son la mitad de después de medianoche: salen a las 08:00 de hoy."""
    prefs = avisos.Preferencias(usuario_id=usuario.id, zona=SANTIAGO)
    madrugada = _instante(dt.date(2026, 3, 11), dt.time(3, 0))

    local = to_zone(avisos.fuera_del_silencio(madrugada, prefs), SANTIAGO)

    assert local.date() == dt.date(2026, 3, 11)
    assert local.time() == dt.time(8, 0)


# ---------------------------------------------------------------------------
# Las puertas de `crear`
# ---------------------------------------------------------------------------


def test_el_interruptor_apagado_no_crea_el_aviso(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Con `notify_streak` en falso, el recordatorio no llega a existir."""
    db.add(UserSettings(user_id=usuario.id, notify_streak=False))
    db.flush()

    creado = _crear(db, cfg, usuario, tipo=NotificationType.STREAK_REMINDER)

    assert creado is None
    assert db.execute(sa.select(sa.func.count(Notification.id))).scalar_one() == 0


def test_un_tipo_sin_interruptor_siempre_pasa(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """El repaso no cuelga de ninguna bandera: es consecuencia de lo que hizo."""
    db.add(UserSettings(user_id=usuario.id, notify_streak=False, notify_path_ready=False))
    db.flush()

    creado = _crear(db, cfg, usuario, tipo=NotificationType.REVIEW_RECOMMENDED)

    assert creado is not None


def test_el_tope_diario_corta_el_cuarto_aviso(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """`notifications.max_per_day.total` es 3: el cuarto del día no se crea."""
    for numero in range(3):
        assert _crear(db, cfg, usuario, clave=f"tope:{numero}") is not None

    assert _crear(db, cfg, usuario, clave="tope:4") is None


def test_el_tope_de_racha_corta_el_tercer_aviso_de_racha(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """De la familia de racha caben dos al día aunque el total permita tres."""
    assert _crear(db, cfg, usuario, tipo=NotificationType.STREAK_REMINDER, clave="r1")
    assert _crear(db, cfg, usuario, tipo=NotificationType.STREAK_LAST_CALL, clave="r2")

    tercero = _crear(db, cfg, usuario, tipo=NotificationType.STREAK_MILESTONE_NEAR, clave="r3")

    assert tercero is None
    # El cupo total todavía tiene sitio para un aviso de otra familia.
    assert _crear(db, cfg, usuario, tipo=NotificationType.SYSTEM, clave="otro") is not None


def test_la_misma_clave_devuelve_la_fila_que_ya_estaba(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Un planificador que corra dos veces no duplica ni se queja."""
    primero = _crear(db, cfg, usuario, clave="repetida")
    segundo = _crear(db, cfg, usuario, clave="repetida", titulo="Otro título")

    assert primero is not None
    assert segundo is not None
    assert primero.id == segundo.id
    assert segundo.title == "Aviso"
    assert db.execute(sa.select(sa.func.count(Notification.id))).scalar_one() == 1


def test_sin_token_de_dispositivo_el_canal_es_la_bandeja(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Permiso de push concedido pero sin token: no hay dónde escribir."""
    db.add(UserSettings(user_id=usuario.id, push_enabled=True, push_token=None))
    db.flush()

    creado = _crear(db, cfg, usuario)

    assert creado is not None
    assert creado.channel == NotificationChannel.IN_APP


def test_con_token_el_canal_es_push(db: Session, cfg: ServicioConfig, usuario: User) -> None:
    db.add(UserSettings(user_id=usuario.id, push_enabled=True, push_token="token-del-aparato"))
    db.flush()

    creado = _crear(db, cfg, usuario)

    assert creado is not None
    assert creado.channel == NotificationChannel.PUSH


def test_un_usuario_dado_de_baja_no_recibe_nada(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    usuario.is_active = False
    db.flush()

    assert _crear(db, cfg, usuario) is None


# ---------------------------------------------------------------------------
# Programar no es entregar
# ---------------------------------------------------------------------------


def test_un_aviso_para_ahora_nace_entregado(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    creado = _crear(db, cfg, usuario)

    assert creado is not None
    assert creado.status == NotificationStatus.SENT
    assert creado.sent_at is not None


def test_un_aviso_programado_nace_pendiente_y_no_se_ve(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Mientras siga pendiente no cuenta como no leído: nadie lo ha recibido."""
    momento = _instante(dt.date(2026, 3, 10), dt.time(9, 0))
    creado = _crear(
        db,
        cfg,
        usuario,
        momento=momento,
        programada_para=_instante(dt.date(2026, 3, 10), dt.time(19, 0)),
    )

    assert creado is not None
    assert creado.status == NotificationStatus.PENDING
    assert creado.sent_at is None
    assert avisos.sin_leer(db, usuario.id) == 0


def test_el_despachador_entrega_lo_que_ya_vencio(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Es el paso que faltaba: sin él, `scheduled_for` es una promesa sin cumplir."""
    manana = _instante(dt.date(2026, 3, 10), dt.time(9, 0))
    tarde = _instante(dt.date(2026, 3, 10), dt.time(19, 0))
    creado = _crear(db, cfg, usuario, momento=manana, programada_para=tarde)
    assert creado is not None

    cuenta = avisos.despachar_pendientes(db, momento=tarde + dt.timedelta(minutes=1))

    db.refresh(creado)
    assert cuenta["entregados"] == 1
    assert creado.status == NotificationStatus.SENT
    assert creado.sent_at is not None
    assert avisos.sin_leer(db, usuario.id) == 1


def test_el_despachador_no_toca_lo_que_aun_no_toca(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    manana = _instante(dt.date(2026, 3, 10), dt.time(9, 0))
    creado = _crear(
        db,
        cfg,
        usuario,
        momento=manana,
        programada_para=_instante(dt.date(2026, 3, 10), dt.time(19, 0)),
    )
    assert creado is not None

    cuenta = avisos.despachar_pendientes(db, momento=manana + dt.timedelta(minutes=5))

    db.refresh(creado)
    assert cuenta["entregados"] == 0
    assert creado.status == NotificationStatus.PENDING


def test_un_aviso_rancio_caduca_en_vez_de_entregarse(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Tras una caída larga, «salva tu racha» a deshora es ruido, no recordatorio."""
    manana = _instante(dt.date(2026, 3, 10), dt.time(9, 0))
    tarde = _instante(dt.date(2026, 3, 10), dt.time(19, 0))
    creado = _crear(db, cfg, usuario, momento=manana, programada_para=tarde)
    assert creado is not None

    cuenta = avisos.despachar_pendientes(db, momento=tarde + avisos.VENTANA_ENTREGA + dt.timedelta(minutes=1))

    db.refresh(creado)
    assert cuenta["entregados"] == 0
    assert cuenta["caducados"] == 1
    assert creado.status == NotificationStatus.FAILED
    assert creado.sent_at is None


# ---------------------------------------------------------------------------
# El contador de la campana
# ---------------------------------------------------------------------------


def test_sin_leer_cuenta_solo_lo_entregado_y_no_leido(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    entregado = _crear(db, cfg, usuario, clave="a")
    leido = _crear(db, cfg, usuario, clave="b")
    assert entregado is not None and leido is not None
    leido.status = NotificationStatus.READ
    leido.read_at = leido.sent_at
    db.flush()

    assert avisos.sin_leer(db, usuario.id) == 1


# ---------------------------------------------------------------------------
# El evento que el contrato no hace opcional
# ---------------------------------------------------------------------------


def test_crear_un_aviso_emite_notification_scheduled(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    creado = _crear(db, cfg, usuario, clave="con-evento")
    assert creado is not None

    evento = db.execute(
        sa.select(DomainEvent).where(DomainEvent.event_type == EventType.NOTIFICATION_SCHEDULED)
    ).scalar_one()
    assert evento.payload["notification_id"] == str(creado.id)
    # Nace procesado: ninguna regla de recompensa lo consume y dejarlo pendiente
    # llenaría la cola del motor de eventos con trabajo que nadie hará.
    assert evento.processing_status == EventStatus.PROCESSED


# ---------------------------------------------------------------------------
# Las rutas de la bandeja
# ---------------------------------------------------------------------------
#
# Se llaman directamente en vez de por HTTP: lo que se prueba es qué filas
# devuelven y cuáles tocan, no el enrutado ni la autenticación, que tienen sus
# propias pruebas.


def test_la_bandeja_no_ensena_lo_que_aun_no_ha_llegado(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    manana = _instante(dt.date(2026, 3, 10), dt.time(9, 0))
    _crear(db, cfg, usuario, momento=manana, clave="ya")
    _crear(
        db,
        cfg,
        usuario,
        momento=manana,
        clave="luego",
        programada_para=_instante(dt.date(2026, 3, 10), dt.time(19, 0)),
    )

    pagina = listar_notificaciones(db, usuario)

    assert [n.idempotency_key for n in db.execute(sa.select(Notification)).scalars()] == [
        "ya",
        "luego",
    ]
    assert len(pagina.items) == 1
    assert pagina.items[0].title == "Aviso"


def test_marcar_todas_como_leidas_no_toca_lo_programado(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Sin el filtro por estado, «marcar todas» daba por leído lo que nadie vio."""
    manana = _instante(dt.date(2026, 3, 10), dt.time(9, 0))
    entregado = _crear(db, cfg, usuario, momento=manana, clave="ya")
    futuro = _crear(
        db,
        cfg,
        usuario,
        momento=manana,
        clave="luego",
        programada_para=_instante(dt.date(2026, 3, 10), dt.time(19, 0)),
    )
    assert entregado is not None and futuro is not None

    marcar_todas_leidas(db, usuario)

    db.refresh(entregado)
    db.refresh(futuro)
    assert entregado.status == NotificationStatus.READ
    assert futuro.status == NotificationStatus.PENDING
    assert futuro.read_at is None


def test_el_cursor_de_la_bandeja_avanza(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """El cliente enviaba `cursor` y la ruta lo ignoraba: la segunda página no existía."""
    # El tope diario es por fecha local, así que cada aviso va a un día distinto.
    for numero in range(3):
        momento = _instante(dt.date(2026, 3, 8 + numero), dt.time(12, 0))
        assert _crear(db, cfg, usuario, momento=momento, clave=f"p{numero}") is not None

    primera = listar_notificaciones(db, usuario, limit=2)
    assert len(primera.items) == 2
    assert primera.page.has_more is True
    assert primera.page.next_cursor is not None

    segunda = listar_notificaciones(db, usuario, limit=2, cursor=primera.page.next_cursor)

    assert len(segunda.items) == 1
    assert segunda.page.has_more is False
    vistos = {n.id for n in primera.items} | {n.id for n in segunda.items}
    assert len(vistos) == 3
