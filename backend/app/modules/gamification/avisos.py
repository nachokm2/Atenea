"""Avisos: lo que trae de vuelta al aprendiz al día siguiente.

La tabla `notifications` (§3.5) y los once `NotificationType` existían desde el
principio, igual que la bandeja del cliente y sus tres rutas. Lo que no existía
era **nadie que escribiera una fila**: la bandeja estaba vacía por construcción y
su texto de estado vacío prometía tres avisos que jamás llegaban.

Este módulo es el único sitio que crea notificaciones. Todo lo que decide si un
aviso se manda, cuándo y por qué canal vive aquí, para que ningún productor
tenga que acordarse de las horas de silencio ni de los topes.

## Las cuatro puertas que cruza un aviso

1. **El interruptor del tipo.** `user_settings` tiene una bandera por familia
   (`notify_path_ready`, `notify_streak`, `notify_missions`). Un aviso cuya
   bandera está apagada no se crea: no se crea apagado, no se crea y ya.
2. **Las horas de silencio.** Son locales del usuario y cruzan la medianoche
   (22:00 → 08:00 por defecto), así que la comparación no es `inicio <= t <= fin`
   sino `t >= inicio or t < fin`. Un aviso que caiga dentro se **corre** al final
   del silencio; no se descarta. La columna de `user_settings` manda sobre la
   clave `notifications.quiet_hours`, que es solo el valor de fábrica que el
   cliente enseña en la pantalla de ajustes.
3. **Los topes del día.** Como mucho `notifications.max_per_day.streak_goal` (2)
   avisos de la familia de racha y `notifications.max_per_day.total` (3) de
   cualquier tipo por **fecha local** del usuario. Se cuentan sobre las filas del
   día en cualquier estado menos `FAILED`: si existe la fila, ya ocupó su cupo.
4. **La clave de idempotencia.** `idempotency_key` es única en la tabla, así que
   un planificador que corra dos veces —dos réplicas, un reinicio— no duplica
   nada. Se captura el `IntegrityError` y se devuelve la fila que ya estaba, que
   es exactamente lo que el llamador quería crear.

## Programar no es entregar

Un aviso nace `PENDING` con `scheduled_for` en el futuro, o `SENT` si es para
ahora mismo. `despachar_pendientes()` —que corre en el mantenimiento del worker—
es quien lo pasa a `SENT`. Mientras siga `PENDING` **no aparece en la bandeja**:
programar un recordatorio para las siete de la tarde y que el aprendiz lo lea a
las diez de la mañana sería peor que no programarlo.

Un aviso que lleva más de `VENTANA_ENTREGA` sin entregarse no se entrega: se
marca `FAILED`. Tras una caída de ocho horas, «te quedan minutos para salvar la
racha» a las tres de la mañana es ruido, no un recordatorio.

## Canal

Hasta que la app registre un token de push, todo es `IN_APP`: la bandeja **es**
la entrega. `push_enabled` sin `push_token` no es push, es un permiso concedido
sin dispositivo donde escribir; el aviso degrada a `IN_APP` en vez de fallar.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import date as date_type, datetime, time as time_type, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.core.logging import get_logger
from app.core.time import DEFAULT_TIMEZONE, ensure_utc, get_zone, to_zone, user_local_date, utcnow
from app.models.enums import (
    EventStatus,
    EventType,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    ReminderMode,
)
from app.models.gamification import Notification
from app.models.identity import User, UserSettings
from app.modules.gamification.servicio_config import ConfiguracionAusenteError

logger = get_logger("atenea.avisos")

#: Claves de `game_configs` que gobiernan los avisos (§5.7). Ningún número de
#: estos vive en Python.
CLAVE_TOPE_TOTAL = "notifications.max_per_day.total"
CLAVE_TOPE_RACHA = "notifications.max_per_day.streak_goal"
CLAVE_SILENCIO = "notifications.quiet_hours"

#: Familia que gobierna `notifications.max_per_day.streak_goal`. El contrato la
#: llama «racha y objetivo»: son los tres avisos que hablan del día de hoy.
FAMILIA_RACHA: frozenset[NotificationType] = frozenset(
    {
        NotificationType.STREAK_REMINDER,
        NotificationType.STREAK_LAST_CALL,
        NotificationType.STREAK_MILESTONE_NEAR,
    }
)

#: Bandera de `user_settings` que gobierna cada tipo. Los tipos que no aparecen
#: no tienen interruptor propio y viajan siempre in-app: son consecuencia directa
#: de algo que el aprendiz hizo (desbloqueó un ítem, ganó un logro) o avisos del
#: sistema, y silenciarlos dejaría la bandeja sin explicación.
INTERRUPTOR: dict[NotificationType, str] = {
    NotificationType.PATH_READY: "avisar_ruta",
    NotificationType.GENERATION_FAILED: "avisar_ruta",
    NotificationType.STREAK_REMINDER: "avisar_racha",
    NotificationType.STREAK_LAST_CALL: "avisar_racha",
    NotificationType.STREAK_MILESTONE_NEAR: "avisar_racha",
    NotificationType.DAILY_MISSION: "avisar_misiones",
}

#: Estados en los que una notificación ya se entregó y el aprendiz puede verla.
#: `PENDING` es futuro y `FAILED` nunca llegó: ninguno de los dos está en la
#: bandeja.
ESTADOS_VISIBLES: tuple[NotificationStatus, ...] = (
    NotificationStatus.SENT,
    NotificationStatus.READ,
)

#: Cuánto puede envejecer un aviso programado antes de que entregarlo sea peor
#: que perderlo. Es un parámetro de infraestructura (tolerancia a caídas del
#: worker), no de balance: por eso vive aquí y no en `game_configs`.
VENTANA_ENTREGA = timedelta(hours=6)

#: Tope de filas que `despachar_pendientes` toca por vuelta. El mantenimiento es
#: síncrono dentro del bucle del worker: mientras barre no toma trabajos de
#: ingesta ni de generación.
TOPE_DESPACHO = 200


# ---------------------------------------------------------------------------
# Destinatario
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Preferencias:
    """Lo que hay que saber del destinatario para decidir un aviso.

    Se arma de `users` ⟕ `user_settings`. Un usuario sin fila de ajustes existe
    —se crea de forma perezosa al pedir `GET /settings`—, así que todos los
    campos traen el mismo valor por defecto que la columna.
    """

    usuario_id: uuid.UUID
    zona: str = DEFAULT_TIMEZONE
    modo: ReminderMode = ReminderMode.SMART
    hora_manual: time_type | None = None
    ultima_llamada: bool = False
    silencio_inicio: time_type = time_type(22, 0)
    silencio_fin: time_type = time_type(8, 0)
    avisar_ruta: bool = True
    avisar_racha: bool = True
    avisar_misiones: bool = False
    push: bool = False
    ultimo_recordatorio: date_type | None = None

    @property
    def canal(self) -> NotificationChannel:
        """Push solo si hay permiso **y** dispositivo; si no, la bandeja."""
        return NotificationChannel.PUSH if self.push else NotificationChannel.IN_APP


def preferencias_de_fila(fila: Any) -> Preferencias:
    """Traduce una fila de `seleccion_de_destinatarios()` a `Preferencias`.

    El planificador barre muchos destinatarios de una sola consulta y necesita
    esta traducción sin volver a la base por cada uno.
    """
    vacio = Preferencias(usuario_id=fila.user_id)
    return Preferencias(
        usuario_id=fila.user_id,
        zona=fila.timezone or DEFAULT_TIMEZONE,
        modo=fila.reminder_mode or vacio.modo,
        hora_manual=fila.reminder_time_local,
        ultima_llamada=bool(fila.last_call_enabled),
        silencio_inicio=fila.quiet_hours_start or vacio.silencio_inicio,
        silencio_fin=fila.quiet_hours_end or vacio.silencio_fin,
        avisar_ruta=(
            vacio.avisar_ruta if fila.notify_path_ready is None else bool(fila.notify_path_ready)
        ),
        avisar_racha=vacio.avisar_racha if fila.notify_streak is None else bool(fila.notify_streak),
        avisar_misiones=bool(fila.notify_missions),
        push=bool(fila.push_enabled) and bool(fila.push_token),
        ultimo_recordatorio=fila.last_reminder_sent_on,
    )


def _columnas_de_destinatario() -> list[Any]:
    """Columnas del `select` que alimenta `preferencias_de_fila`."""
    return [
        User.id.label("user_id"),
        User.timezone,
        UserSettings.reminder_mode,
        UserSettings.reminder_time_local,
        UserSettings.last_call_enabled,
        UserSettings.quiet_hours_start,
        UserSettings.quiet_hours_end,
        UserSettings.notify_path_ready,
        UserSettings.notify_streak,
        UserSettings.notify_missions,
        UserSettings.push_enabled,
        UserSettings.push_token,
        UserSettings.last_reminder_sent_on,
    ]


def seleccion_de_destinatarios() -> sa.Select:
    """`SELECT` base de destinatarios vivos con sus ajustes (o los de fábrica)."""
    return (
        sa.select(*_columnas_de_destinatario())
        .select_from(User)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(User.is_active.is_(True), User.deleted_at.is_(None))
    )


def preferencias_de(db: Session, usuario_id: uuid.UUID) -> Preferencias | None:
    """Preferencias de un usuario, o `None` si no existe o está de baja."""
    fila = db.execute(seleccion_de_destinatarios().where(User.id == usuario_id)).one_or_none()
    return preferencias_de_fila(fila) if fila is not None else None


# ---------------------------------------------------------------------------
# Horas de silencio
# ---------------------------------------------------------------------------


def en_silencio(hora: time_type, inicio: time_type, fin: time_type) -> bool:
    """¿Cae `hora` dentro de la franja de silencio?

    La franja cruza la medianoche cuando `inicio > fin`, que es el caso por
    defecto (22:00 → 08:00). `PUT /settings` admite `inicio == fin`, y eso se
    lee como «sin silencio»: la alternativa, silenciar veinticuatro horas,
    dejaría al aprendiz sin ningún aviso sin que él lo haya pedido.
    """
    if inicio == fin:
        return False
    if inicio < fin:
        return inicio <= hora < fin
    return hora >= inicio or hora < fin


def instante_local(dia: date_type, hora: time_type, zona: str) -> datetime:
    """Instante UTC de una `hora` local de un `dia` concreto.

    La conversión se hace sobre la fecha real y no una sola vez: con horario de
    verano, «las 19:00 del martes» y «las 19:00 del miércoles» pueden ser dos
    desfases distintos.
    """
    return ensure_utc(datetime.combine(dia, hora, tzinfo=get_zone(zona)))


def fuera_del_silencio(momento: datetime, prefs: Preferencias) -> datetime:
    """Corre un instante hasta el final del silencio si cae dentro.

    Devuelve el mismo instante si no hay nada que correr.
    """
    local = to_zone(momento, prefs.zona)
    if not en_silencio(local.time(), prefs.silencio_inicio, prefs.silencio_fin):
        return momento
    dia = local.date()
    # Con la franja cruzando la medianoche hay dos mitades: la de antes de
    # medianoche sale al día siguiente, la de después sale hoy mismo.
    if prefs.silencio_inicio > prefs.silencio_fin and local.time() >= prefs.silencio_inicio:
        dia = dia + timedelta(days=1)
    return instante_local(dia, prefs.silencio_fin, prefs.zona)


# ---------------------------------------------------------------------------
# Topes del día
# ---------------------------------------------------------------------------


def _topes(db: Session, cfg: Any) -> tuple[int, int]:
    """`(total, familia de racha)` del día, leídos de `game_configs`.

    Ningún tope tiene valor de reserva escrito en Python (§8.10 regla 5): sin la
    clave sembrada, esto levanta `ConfiguracionAusenteError` y `crear` decide qué
    hacer con ello.
    """
    from app.modules.gamification.servicio_config import ServicioConfig  # noqa: PLC0415

    servicio = cfg if cfg is not None else ServicioConfig(db)
    return int(servicio.obtener_int(CLAVE_TOPE_TOTAL)), int(servicio.obtener_int(CLAVE_TOPE_RACHA))


def _cupo_agotado(
    db: Session,
    usuario_id: uuid.UUID,
    fecha: date_type,
    tipo: NotificationType,
    cfg: Any,
) -> bool:
    """¿Llenó ya el día su cupo de avisos, en total o en la familia de racha?"""
    tope_total, tope_racha = _topes(db, cfg)
    tipos = list(
        db.execute(
            sa.select(Notification.notification_type).where(
                Notification.user_id == usuario_id,
                Notification.local_date == fecha,
                Notification.status != NotificationStatus.FAILED,
            )
        )
        .scalars()
        .all()
    )
    if len(tipos) >= tope_total:
        return True
    if tipo in FAMILIA_RACHA:
        return sum(1 for t in tipos if t in FAMILIA_RACHA) >= tope_racha
    return False


# ---------------------------------------------------------------------------
# Crear
# ---------------------------------------------------------------------------


def crear(
    db: Session,
    *,
    usuario_id: uuid.UUID,
    tipo: NotificationType,
    titulo: str,
    cuerpo: str,
    clave: str,
    enlace: str | None = None,
    carga: dict[str, Any] | None = None,
    programada_para: datetime | None = None,
    cfg: Any = None,
    prefs: Preferencias | None = None,
    momento: datetime | None = None,
) -> Notification | None:
    """Crea un aviso, o devuelve `None` si no le toca existir.

    `None` significa tres cosas distintas y ninguna es un error: el interruptor
    del tipo está apagado, el día ya gastó su cupo, o el destinatario no existe.
    Si la clave de idempotencia ya estaba usada devuelve **la fila que ya había**,
    para que el llamador pueda repetir la llamada sin pensar.
    """
    ahora = ensure_utc(momento) if momento else utcnow()
    destinatario = prefs or preferencias_de(db, usuario_id)
    if destinatario is None:
        return None

    interruptor = INTERRUPTOR.get(tipo)
    if interruptor is not None and not getattr(destinatario, interruptor):
        return None

    deseado = ensure_utc(programada_para) if programada_para else ahora
    entrega = fuera_del_silencio(deseado, destinatario)
    fecha = user_local_date(entrega, destinatario.zona)

    existente = db.execute(
        sa.select(Notification).where(Notification.idempotency_key == clave)
    ).scalar_one_or_none()
    if existente is not None:
        return existente

    try:
        lleno = _cupo_agotado(db, destinatario.usuario_id, fecha, tipo, cfg)
    except ConfiguracionAusenteError:
        # Sin los topes sembrados no hay forma de saber cuántos avisos caben. Se
        # falla cerrado: un aviso de menos es un mal día; una bandeja sin freno,
        # un motivo para desinstalar. Y sobre todo, nunca se lleva por delante a
        # quien lo estaba creando (una generación de ruta, un recálculo).
        logger.warning(
            "aviso.sin_configuracion", usuario_id=str(destinatario.usuario_id), tipo=str(tipo)
        )
        return None
    if lleno:
        logger.info(
            "aviso.cupo_agotado",
            usuario_id=str(destinatario.usuario_id),
            tipo=str(tipo),
            local_date=fecha.isoformat(),
        )
        return None

    programado = entrega > ahora
    aviso = Notification(
        user_id=destinatario.usuario_id,
        notification_type=tipo,
        channel=destinatario.canal,
        status=NotificationStatus.PENDING if programado else NotificationStatus.SENT,
        title=titulo[:120],
        body=cuerpo[:400],
        deep_link=enlace[:160] if enlace else None,
        payload=carga or {},
        scheduled_for=entrega,
        sent_at=None if programado else ahora,
        local_date=fecha,
        idempotency_key=clave[:120],
    )
    punto = db.begin_nested()
    try:
        db.add(aviso)
        db.flush()
    except IntegrityError:
        punto.rollback()
        return db.execute(
            sa.select(Notification).where(Notification.idempotency_key == clave)
        ).scalar_one_or_none()
    punto.commit()

    _anunciar(db, aviso, destinatario)
    return aviso


def _anunciar(db: Session, aviso: Notification, prefs: Preferencias) -> None:
    """Emite `NOTIFICATION_SCHEDULED` (§4.2), que el contrato no hace opcional.

    Nace `PROCESSED`: no hay regla de recompensa que lo consuma y dejarlo
    `PENDING` llenaría la cola del motor de eventos que nadie va a procesar.
    """
    from app.modules.gamification import eventos  # noqa: PLC0415 - evita el ciclo de importación

    evento = eventos.crear_evento_dominio(
        db,
        usuario_id=aviso.user_id,
        tipo=EventType.NOTIFICATION_SCHEDULED,
        payload={
            "notification_id": str(aviso.id),
            "notification_type": str(aviso.notification_type),
            "scheduled_for": aviso.scheduled_for.isoformat() if aviso.scheduled_for else None,
        },
        idempotency_key=f"notification-scheduled:{aviso.id}",
        occurred_at=aviso.scheduled_for,
        local_date=aviso.local_date,
        timezone=prefs.zona,
        source_module="gamification",
    )
    if evento is not None:
        evento.processing_status = EventStatus.PROCESSED
        db.flush()


# ---------------------------------------------------------------------------
# Entregar
# ---------------------------------------------------------------------------


def despachar_pendientes(
    db: Session, *, momento: datetime | None = None, tope: int = TOPE_DESPACHO
) -> dict[str, int]:
    """Entrega los avisos programados que ya vencieron y caduca los rancios.

    Corre dentro del mantenimiento del worker. Toma las filas con `FOR UPDATE
    SKIP LOCKED` para que dos procesos no entreguen el mismo aviso, aunque hoy
    solo haya uno.
    """
    ahora = ensure_utc(momento) if momento else utcnow()
    frontera = ahora - VENTANA_ENTREGA

    entregados = _mover(
        db,
        sa.and_(
            Notification.status == NotificationStatus.PENDING,
            Notification.scheduled_for <= ahora,
            Notification.scheduled_for >= frontera,
        ),
        {"status": NotificationStatus.SENT, "sent_at": ahora},
        tope,
    )
    caducados = _mover(
        db,
        sa.and_(
            Notification.status == NotificationStatus.PENDING,
            Notification.scheduled_for < frontera,
        ),
        {"status": NotificationStatus.FAILED},
        tope,
    )
    return {"entregados": entregados, "caducados": caducados}


def _mover(db: Session, condicion: Any, valores: dict[str, Any], tope: int) -> int:
    """Aplica `valores` a como mucho `tope` filas que cumplan `condicion`."""
    elegidas = (
        sa.select(Notification.id)
        .where(condicion)
        .order_by(Notification.scheduled_for)
        .limit(tope)
        .with_for_update(skip_locked=True)
    )
    ids = list(db.execute(elegidas).scalars().all())
    if not ids:
        return 0
    db.execute(sa.update(Notification).where(Notification.id.in_(ids)).values(**valores))
    db.flush()
    return len(ids)


# ---------------------------------------------------------------------------
# Bandeja
# ---------------------------------------------------------------------------


def sin_leer(db: Session, usuario_id: uuid.UUID) -> int:
    """Cuántos avisos entregados siguen sin leer. Alimenta la campana del panel."""
    return int(
        db.execute(
            sa.select(sa.func.count(Notification.id)).where(
                Notification.user_id == usuario_id,
                Notification.status == NotificationStatus.SENT,
                Notification.read_at.is_(None),
            )
        ).scalar_one()
    )


def codificar_cursor(clave: dict[str, Any]) -> str:
    """Codifica la última clave de orden como cursor opaco `base64(json)` (§8.2)."""
    crudo = json.dumps(clave, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(crudo).decode("ascii")


def decodificar_cursor(cursor: str | None) -> dict[str, Any] | None:
    """Decodifica un cursor; uno corrupto es `422`, nunca un `500`."""
    if not cursor:
        return None
    try:
        relleno = "=" * (-len(cursor) % 4)
        clave = json.loads(base64.urlsafe_b64decode(cursor + relleno).decode("utf-8"))
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValidationFailed(
            "El cursor de paginación no es válido.",
            field_errors=[{"field": "cursor", "message": "Cursor ilegible."}],
        ) from exc
    if not isinstance(clave, dict):
        raise ValidationFailed(
            "El cursor de paginación no es válido.",
            field_errors=[{"field": "cursor", "message": "Cursor ilegible."}],
        )
    return clave


# ---------------------------------------------------------------------------
# Momentos que ya tienen evento
# ---------------------------------------------------------------------------
#
# Estos cuatro avisos no los decide el reloj: cuelgan de algo que acaba de pasar
# y los crea quien provoca ese momento, justo al lado del evento de dominio que
# §4.2 ya ata a un `NotificationType`. Viven aquí, y no en cada productor, para
# que el texto y la clave de idempotencia de un aviso estén siempre en el mismo
# archivo que las reglas que deciden si se manda.


def al_disenar_ruta(
    db: Session,
    *,
    usuario_id: uuid.UUID,
    path_id: uuid.UUID,
    titulo: str,
    job_id: uuid.UUID,
    cfg: Any = None,
) -> Notification | None:
    """`PATH_GENERATED` → «tu ruta está trazada» (§4.2).

    La ruta recién diseñada queda en `PENDING_REVIEW`: el aviso no anuncia que se
    puede estudiar, anuncia que hay algo que revisar.
    """
    return crear(
        db,
        usuario_id=usuario_id,
        tipo=NotificationType.PATH_READY,
        titulo="Tu ruta ya está trazada",
        cuerpo=f"«{titulo}» tiene su mapa listo. Échale un vistazo y dale el visto bueno.",
        clave=f"path-ready:{path_id}:{job_id}",
        enlace=f"route/{path_id}",
        carga={"path_id": str(path_id)},
        cfg=cfg,
    )


def al_terminar_primer_modulo(
    db: Session,
    *,
    usuario_id: uuid.UUID,
    path_id: uuid.UUID,
    module_id: uuid.UUID,
    titulo: str,
    job_id: uuid.UUID,
    cfg: Any = None,
) -> Notification | None:
    """`MODULE_CONTENT_READY` del primer módulo → «ya puedes empezar» (§4.2).

    Solo el primero. Una ruta de seis módulos generaría seis avisos, el tope
    diario se comería cuatro y los dos que pasaran llegarían cuando el aprendiz
    ya está dentro estudiando.
    """
    return crear(
        db,
        usuario_id=usuario_id,
        tipo=NotificationType.PATH_READY,
        titulo="Ya puedes empezar",
        cuerpo=f"El primer tramo de «{titulo}» está escrito y te espera.",
        clave=f"module-ready:{module_id}:{job_id}",
        enlace=f"route/{path_id}",
        carga={"path_id": str(path_id), "module_id": str(module_id)},
        cfg=cfg,
    )


def al_fallar_generacion(
    db: Session,
    *,
    usuario_id: uuid.UUID,
    path_id: uuid.UUID,
    job_id: uuid.UUID,
    cfg: Any = None,
) -> Notification | None:
    """`GENERATION_FAILED` → «tu ruta necesita un empujón» (§4.2).

    El texto no culpa al material del aprendiz: la generación falla por muchas
    razones y casi ninguna es suya.
    """
    return crear(
        db,
        usuario_id=usuario_id,
        tipo=NotificationType.GENERATION_FAILED,
        titulo="Tu ruta se quedó a medias",
        cuerpo="La preparación no terminó. Entra y vuelve a lanzarla: no pierdes nada de lo hecho.",
        clave=f"generation-failed-aviso:{job_id}",
        enlace=f"route/{path_id}/generation",
        carga={"path_id": str(path_id), "job_id": str(job_id)},
        cfg=cfg,
    )


def al_detectar_debilidad(
    db: Session,
    *,
    usuario_id: uuid.UUID,
    topic_id: uuid.UUID,
    titulo: str,
    marca: int,
    cfg: Any = None,
) -> Notification | None:
    """`WEAKNESS_DETECTED` → «un repaso corto» (§4.2).

    Es la única puerta automática al repaso espaciado: hasta ahora, las
    sugerencias de repaso solo aparecían en la pantalla de resultado de una
    evaluación, y quien no llegaba a esa pantalla no las veía nunca.

    `marca` es el instante de la detección. Entra en la clave porque un tema
    puede recuperarse y volver a debilitarse meses después, y esa segunda vez
    merece su propio aviso; el tope diario impide que una mala tarde llene la
    bandeja.
    """
    return crear(
        db,
        usuario_id=usuario_id,
        tipo=NotificationType.REVIEW_RECOMMENDED,
        titulo=f"Un repaso corto de «{titulo}»",
        cuerpo="Unas pocas preguntas bastan para dejarlo firme otra vez.",
        clave=f"review-recommended:{usuario_id}:{topic_id}:{marca}",
        enlace=f"review/{topic_id}",
        carga={"topic_id": str(topic_id)},
        cfg=cfg,
    )


__all__ = [
    "ESTADOS_VISIBLES",
    "FAMILIA_RACHA",
    "INTERRUPTOR",
    "TOPE_DESPACHO",
    "VENTANA_ENTREGA",
    "Preferencias",
    "al_detectar_debilidad",
    "al_disenar_ruta",
    "al_fallar_generacion",
    "al_terminar_primer_modulo",
    "codificar_cursor",
    "crear",
    "decodificar_cursor",
    "despachar_pendientes",
    "en_silencio",
    "fuera_del_silencio",
    "instante_local",
    "preferencias_de",
    "preferencias_de_fila",
    "seleccion_de_destinatarios",
    "sin_leer",
]
