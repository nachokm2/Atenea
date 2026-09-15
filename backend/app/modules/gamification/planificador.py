"""El planificador: quién merece un aviso ahora mismo y de qué.

Los avisos de Atenea se dividen en dos familias. Unos cuelgan de algo que pasó
—la ruta terminó de generarse, un tema se marcó débil— y los crea quien provoca
ese momento. Los otros no cuelgan de nada: nacen del reloj. Que la racha esté en
riesgo hoy no es un suceso, es una ausencia, y una ausencia no dispara ningún
evento. Ese es el trabajo de este módulo.

## Un barrido, no un cron por zona horaria

Cada usuario tiene su propio «hoy» según `users.timezone`, así que no hay una
hora del servidor a la que mandar nada. En vez de programar un cron por zona, el
barrido corre a menudo y en cada vuelta se pregunta, para cada candidato, si su
**reloj local** ya pasó por la hora que le toca. El que va por delante ya recibió
el suyo; el que va por detrás lo recibirá en una vuelta posterior.

La ventana `notifications.reminder.window` (08:00–21:30) es la que impide que un
worker que estuvo caído mande a las dos de la mañana el recordatorio de las
siete: fuera de la franja, el candidato simplemente no cumple la condición.

## Cómo se deduce la hora del modo SMART

El contrato deja la forma pero no el algoritmo: «hora habitual de estudio» más
`notifications.reminder.offset_min`, acotado a la franja, y
`notifications.reminder.default_hour` cuando no hay datos. Aquí la hora habitual
es **la mediana de la hora local de `streak_days.first_activity_at`** de los
últimos días activos, que es el único dato que el esquema guarda para esto (el
contrato describe esa columna, literalmente, como «primera actividad (bono +20 XP
y hora habitual)»).

Cuántos días se miran sale de `goal.adapt.window_days` (14). Es la ventana que el
juego ya usa para observar el comportamiento del aprendiz y sembrar una clave
nueva solo para esto descuadraría los 177 parámetros del contrato §5 sin añadir
ninguna decisión de balance distinta.

## Por qué la racha viva no se lee de `current_length`

`streaks.current_length` no caduca sola: solo se reescribe la próxima vez que el
aprendiz vuelve. Quien desapareció hace un mes sigue diciendo «30 días» con
`broken_at` en nulo. La única verdad sobre la racha es `last_active_date`, y de
ahí sale el `delta` que decide todo lo de abajo.
"""

from __future__ import annotations

import statistics
import uuid
from datetime import date as date_type, datetime, time as time_type, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.time import ensure_utc, to_zone, utcnow
from app.models.enums import NotificationType, ReminderMode
from app.models.gamification import Streak, StreakDay
from app.models.identity import User
from app.modules.gamification import avisos
from app.modules.gamification.avisos import Preferencias

logger = get_logger("atenea.planificador")

#: Claves de `game_configs` que gobiernan el barrido (§5.7).
CLAVE_HORA_POR_DEFECTO = "notifications.reminder.default_hour"
CLAVE_DESPLAZAMIENTO = "notifications.reminder.offset_min"
CLAVE_VENTANA = "notifications.reminder.window"
CLAVE_HORA_ULTIMA_LLAMADA = "notifications.last_call.hour"
CLAVE_RACHA_MINIMA = "notifications.last_call.min_streak"
CLAVE_REACTIVACION = "notifications.reactivation_days"
CLAVE_VENTANA_HABITO = "goal.adapt.window_days"

#: Mínimo de días con actividad para que una mediana signifique algo. Por debajo
#: de tres, la «hora habitual» sería la hora de un día suelto disfrazada de
#: costumbre: mejor la hora por defecto, que al menos es honesta.
MIN_DIAS_PARA_HABITO = 3

#: Cuánto dura la ventana matutina del aviso de misiones, contada desde el inicio
#: de la franja de recordatorios.
HORAS_VENTANA_MISIONES = 2

#: Destinatarios que mira el barrido por vuelta. El mantenimiento es síncrono
#: dentro del bucle del worker: mientras barre no toma ningún trabajo de la cola.
#: Si el corte deja gente fuera queda escrito en el registro, nunca en silencio.
TOPE_BARRIDO = 500

#: Los días de racha en riesgo. Uno es «ayer estudiaste, hoy todavía no»; dos es
#: el día que puede salvar el día de gracia del mes.
DELTAS_EN_RIESGO = (1, 2)


# ---------------------------------------------------------------------------
# Horas
# ---------------------------------------------------------------------------


def leer_hora(texto: str) -> time_type:
    """Convierte un `'HH:MM'` de `game_configs` en una hora."""
    horas, _, minutos = texto.partition(":")
    return time_type(int(horas), int(minutos or 0))


def _minutos(hora: time_type) -> int:
    return hora.hour * 60 + hora.minute


def _de_minutos(minutos: int) -> time_type:
    acotado = max(0, min(23 * 60 + 59, int(minutos)))
    return time_type(acotado // 60, acotado % 60)


def acotar(hora: time_type, inicio: time_type, fin: time_type) -> time_type:
    """Aprieta una hora contra los bordes de la franja de recordatorios."""
    if hora < inicio:
        return inicio
    if hora > fin:
        return fin
    return hora


def dentro(hora: time_type, inicio: time_type, fin: time_type) -> bool:
    """¿Está `hora` en `[inicio, fin)`? La franja nunca cruza la medianoche."""
    return inicio <= hora < fin


def hora_habitual(
    db: Session, prefs: Preferencias, hoy: date_type, *, dias: int
) -> time_type | None:
    """Mediana de la hora local en que el aprendiz suele empezar a estudiar.

    Devuelve `None` si no hay suficientes días para que la mediana signifique
    algo. Índice usado: `ix_streak_days_user_id_local_date`.
    """
    marcas = list(
        db.execute(
            sa.select(StreakDay.first_activity_at)
            .where(
                StreakDay.user_id == prefs.usuario_id,
                StreakDay.first_activity_at.is_not(None),
                StreakDay.local_date <= hoy,
            )
            .order_by(StreakDay.local_date.desc())
            .limit(max(1, dias))
        )
        .scalars()
        .all()
    )
    if len(marcas) < MIN_DIAS_PARA_HABITO:
        return None
    minutos = [_minutos(to_zone(marca, prefs.zona).time()) for marca in marcas]
    return _de_minutos(round(statistics.median(minutos)))


def hora_del_recordatorio(
    db: Session, cfg: Any, prefs: Preferencias, hoy: date_type
) -> time_type | None:
    """Hora local a la que le toca el recordatorio diario, o `None` si no le toca.

    Las tres ramas acaban acotadas a `notifications.reminder.window`, también la
    manual: una hora fija a las 23:30 caería dentro del silencio y el aviso se
    correría a la mañana siguiente, que no es lo que el aprendiz pidió.
    """
    if prefs.modo == ReminderMode.OFF:
        return None
    ventana = cfg.obtener_json(CLAVE_VENTANA)
    inicio, fin = leer_hora(ventana["start"]), leer_hora(ventana["end"])
    por_defecto = leer_hora(cfg.obtener_str(CLAVE_HORA_POR_DEFECTO))

    if prefs.modo == ReminderMode.MANUAL:
        return acotar(prefs.hora_manual or por_defecto, inicio, fin)

    habitual = hora_habitual(db, prefs, hoy, dias=cfg.obtener_int(CLAVE_VENTANA_HABITO))
    if habitual is None:
        return acotar(por_defecto, inicio, fin)
    desplazada = _de_minutos(_minutos(habitual) + cfg.obtener_int(CLAVE_DESPLAZAMIENTO))
    return acotar(desplazada, inicio, fin)


# ---------------------------------------------------------------------------
# Textos
# ---------------------------------------------------------------------------


def _texto_recordatorio(dias: int, delta: int, con_gracia: bool) -> tuple[str, str]:
    """Título y cuerpo del recordatorio diario. Sin culpa y sin alarma."""
    if delta == 2 and con_gracia:
        return (
            "Tu racha aguanta un día más",
            f"Ayer no pudiste y el Reino te guarda el día de gracia del mes. "
            f"Con un rato de hoy, tus {dias} días siguen enteros.",
        )
    if dias >= 1:
        return (
            f"Tu racha de {dias} días sigue en pie",
            "Todavía no has estudiado hoy. Un rato basta para que siga contando.",
        )
    return (
        "El Reino te espera",
        "Un rato de estudio hoy y empiezas racha nueva.",
    )


def _texto_ultima_llamada(dias: int) -> tuple[str, str]:
    return (
        "Último tramo del día",
        f"Quedan unas horas para cerrar el día y que tus {dias} días sigan contando.",
    )


def _texto_reactivacion(dias: int) -> tuple[str, str]:
    if dias <= 3:
        return (
            "Tu aventura está donde la dejaste",
            "Nada se ha perdido: tu progreso y tus conocimientos siguen intactos.",
        )
    if dias <= 7:
        return (
            "Una semana sin pisar el Reino",
            "Volver es barato: una lección corta y retomas el hilo donde lo dejaste.",
        )
    return (
        "Hace tiempo que no te vemos",
        "Tu personaje, tu oro y tus conocimientos te esperan tal como los dejaste.",
    )


# ---------------------------------------------------------------------------
# Barrido
# ---------------------------------------------------------------------------


def _candidatos(db: Session, limite: date_type, tope: int) -> list[Any]:
    """Usuarios vivos con racha, ordenados del más reciente al más antiguo.

    El filtro se hace sobre una fecha UTC con dos días de holgura: cada usuario
    tiene su propio hoy y el corte por zona no se puede hacer en SQL. Es un
    superconjunto, no un resultado: la decisión real es por fila.
    """
    consulta = (
        avisos.seleccion_de_destinatarios()
        .join(Streak, Streak.user_id == User.id)
        .add_columns(
            Streak.current_length,
            Streak.last_active_date,
            Streak.grace_used_for_month,
            Streak.created_at.label("racha_creada_en"),
        )
        .where(
            sa.or_(
                Streak.last_active_date >= limite,
                sa.and_(
                    Streak.last_active_date.is_(None),
                    sa.func.date(Streak.created_at) >= limite,
                ),
            )
        )
        .order_by(Streak.last_active_date.desc().nullslast(), User.id)
        .limit(tope + 1)
    )
    return list(db.execute(consulta).all())


def planificar(
    db: Session,
    cfg: Any,
    *,
    momento: datetime | None = None,
    tope: int = TOPE_BARRIDO,
) -> dict[str, int]:
    """Crea los avisos que dependen del reloj. Devuelve cuántos de cada clase."""
    ahora = ensure_utc(momento) if momento else utcnow()
    escalones = [int(d) for d in cfg.obtener_lista(CLAVE_REACTIVACION)]
    holgura = max(escalones or [0]) + 2
    filas = _candidatos(db, (ahora - timedelta(days=holgura)).date(), tope)

    if len(filas) > tope:
        logger.warning("planificador.barrido_truncado", vistos=tope, tope=tope)
        filas = filas[:tope]

    cuenta = {"recordatorios": 0, "ultimas_llamadas": 0, "reactivaciones": 0, "misiones": 0}
    for fila in filas:
        prefs = avisos.preferencias_de_fila(fila)
        local = to_zone(ahora, prefs.zona)
        hoy = local.date()
        ancla = fila.last_active_date or to_zone(fila.racha_creada_en, prefs.zona).date()
        delta = (hoy - ancla).days

        if delta in DELTAS_EN_RIESGO:
            if _recordar(db, cfg, prefs, fila, hoy=hoy, local=local, delta=delta, ahora=ahora):
                cuenta["recordatorios"] += 1
            if _ultima_llamada(db, cfg, prefs, fila, hoy=hoy, local=local, ahora=ahora):
                cuenta["ultimas_llamadas"] += 1
        elif delta in escalones and _reactivar(
            db, cfg, prefs, hoy=hoy, local=local, delta=delta, ahora=ahora
        ):
            cuenta["reactivaciones"] += 1

        if delta >= 1 and _misiones(db, cfg, prefs, hoy=hoy, local=local, ahora=ahora):
            cuenta["misiones"] += 1

    if any(cuenta.values()):
        logger.info("planificador.barrido", candidatos=len(filas), **cuenta)
    return cuenta


def _recordar(
    db: Session,
    cfg: Any,
    prefs: Preferencias,
    fila: Any,
    *,
    hoy: date_type,
    local: datetime,
    delta: int,
    ahora: datetime,
) -> bool:
    """Recordatorio diario: la racha sigue viva y todavía no se ha estudiado hoy."""
    if prefs.ultimo_recordatorio == hoy:
        return False
    objetivo = hora_del_recordatorio(db, cfg, prefs, hoy)
    if objetivo is None:
        return False
    fin = leer_hora(cfg.obtener_json(CLAVE_VENTANA)["end"])
    if not dentro(local.time(), objetivo, fin):
        return False

    dias = int(fila.current_length or 0)
    con_gracia = delta == 2 and _queda_gracia(cfg, fila, hoy)
    if delta == 2 and not con_gracia:
        # Sin día de gracia, mañana la racha ya estará rota: el recordatorio
        # prometería algo que no se puede cumplir.
        return False
    titulo, cuerpo = _texto_recordatorio(dias, delta, con_gracia)
    aviso = avisos.crear(
        db,
        usuario_id=prefs.usuario_id,
        tipo=NotificationType.STREAK_REMINDER,
        titulo=titulo,
        cuerpo=cuerpo,
        clave=f"streak-reminder:{prefs.usuario_id}:{hoy.isoformat()}",
        enlace="streak",
        carga={"streak_days": dias, "delta": delta},
        cfg=cfg,
        prefs=prefs,
        momento=ahora,
    )
    if aviso is None:
        return False
    _marcar_recordado(db, prefs.usuario_id, hoy)
    return True


def _ultima_llamada(
    db: Session,
    cfg: Any,
    prefs: Preferencias,
    fila: Any,
    *,
    hoy: date_type,
    local: datetime,
    ahora: datetime,
) -> bool:
    """Segundo aviso del día, opt-in y solo para rachas ya largas."""
    if not prefs.ultima_llamada:
        return False
    dias = int(fila.current_length or 0)
    if dias < cfg.obtener_int(CLAVE_RACHA_MINIMA):
        return False
    hora = leer_hora(cfg.obtener_str(CLAVE_HORA_ULTIMA_LLAMADA))
    # El borde superior es el inicio del silencio: más tarde, el aviso se correría
    # a la mañana siguiente y llegaría cuando ya no sirve de nada.
    if not dentro(local.time(), hora, prefs.silencio_inicio):
        return False
    titulo, cuerpo = _texto_ultima_llamada(dias)
    return (
        avisos.crear(
            db,
            usuario_id=prefs.usuario_id,
            tipo=NotificationType.STREAK_LAST_CALL,
            titulo=titulo,
            cuerpo=cuerpo,
            clave=f"streak-last-call:{prefs.usuario_id}:{hoy.isoformat()}",
            enlace="streak",
            carga={"streak_days": dias},
            cfg=cfg,
            prefs=prefs,
            momento=ahora,
        )
        is not None
    )


def _reactivar(
    db: Session,
    cfg: Any,
    prefs: Preferencias,
    *,
    hoy: date_type,
    local: datetime,
    delta: int,
    ahora: datetime,
) -> bool:
    """Aviso de vuelta a los 3, 7 y 30 días de silencio.

    No usa la hora habitual: quien lleva una semana fuera no tiene costumbre que
    respetar, así que va a la hora por defecto.
    """
    ventana = cfg.obtener_json(CLAVE_VENTANA)
    objetivo = acotar(
        leer_hora(cfg.obtener_str(CLAVE_HORA_POR_DEFECTO)),
        leer_hora(ventana["start"]),
        leer_hora(ventana["end"]),
    )
    if not dentro(local.time(), objetivo, leer_hora(ventana["end"])):
        return False
    titulo, cuerpo = _texto_reactivacion(delta)
    return (
        avisos.crear(
            db,
            usuario_id=prefs.usuario_id,
            tipo=NotificationType.REACTIVATION,
            titulo=titulo,
            cuerpo=cuerpo,
            clave=f"reactivation:{prefs.usuario_id}:{hoy.isoformat()}",
            enlace="home",
            carga={"days_away": delta},
            cfg=cfg,
            prefs=prefs,
            momento=ahora,
        )
        is not None
    )


def _misiones(
    db: Session,
    cfg: Any,
    prefs: Preferencias,
    *,
    hoy: date_type,
    local: datetime,
    ahora: datetime,
) -> bool:
    """Aviso matutino de misiones (opt-in: `notify_missions` nace apagado).

    No asigna nada: las misiones del día se instancian solas la primera vez que
    el aprendiz abre el tablón, de forma determinista. El aviso solo abre la
    puerta.
    """
    if not prefs.avisar_misiones:
        return False
    inicio = leer_hora(cfg.obtener_json(CLAVE_VENTANA)["start"])
    fin = _de_minutos(_minutos(inicio) + HORAS_VENTANA_MISIONES * 60)
    if not dentro(local.time(), inicio, fin):
        return False
    return (
        avisos.crear(
            db,
            usuario_id=prefs.usuario_id,
            tipo=NotificationType.DAILY_MISSION,
            titulo="Encargos nuevos en el tablón",
            cuerpo="Las misiones de hoy ya están puestas. Échales un vistazo cuando puedas.",
            clave=f"daily-mission:{prefs.usuario_id}:{hoy.isoformat()}",
            enlace="missions",
            cfg=cfg,
            prefs=prefs,
            momento=ahora,
        )
        is not None
    )


def _queda_gracia(cfg: Any, fila: Any, hoy: date_type) -> bool:
    """¿Queda día de gracia para el día perdido? (§6.10).

    El mes que cuenta es el del **día perdido**, no el de hoy: los dos difieren
    el día 1 de cada mes, que es justo cuando la respuesta importa.
    """
    from app.modules.gamification import rachas  # noqa: PLC0415 - evita el ciclo de importación

    perdido = hoy - timedelta(days=1)
    # `gracia_disponible` solo mira `grace_used_for_month`, que la fila del
    # barrido ya trae: se reutiliza la regla en vez de escribir una tercera copia.
    return rachas.gracia_disponible(cfg, fila, f"{perdido.year:04d}-{perdido.month:02d}")


def _marcar_recordado(db: Session, usuario_id: uuid.UUID, hoy: date_type) -> None:
    """Deja la marca antifatiga: un recordatorio como mucho por fecha local."""
    from app.modules.identity import servicio_usuario  # noqa: PLC0415 - evita el ciclo

    ajustes = servicio_usuario.obtener_o_crear_ajustes(db, usuario_id)
    ajustes.last_reminder_sent_on = hoy
    db.flush()


__all__ = [
    "DELTAS_EN_RIESGO",
    "MIN_DIAS_PARA_HABITO",
    "TOPE_BARRIDO",
    "acotar",
    "dentro",
    "hora_del_recordatorio",
    "hora_habitual",
    "leer_hora",
    "planificar",
]
