"""Motor de gamificación: consume un evento de dominio y produce el recibo.

Orden de consumo obligatorio dentro de una acción (CONTRACT.md §4.1 regla 2)::

    XP/oro → agregado diario y objetivo → racha → misiones → logros → desbloqueos

Reglas estructurales que este archivo hace cumplir:

- **Regla anti-bucle** (§4.1 regla 3): el XP con `is_educational = false`
  (misiones, hitos, logros) no vuelve a alimentar el agregado diario ni la racha.
- **Cascada acotada**: los eventos derivados se procesan con
  `AgregadorRecibo.puede_descender()` y con memoria de claves ya vistas.
- **Server-authoritative**: ningún importe viene del cliente. El XP sale de
  `reward_rules` + `game_configs` y de las fórmulas de §6.2; el oro lo aplica
  `economy` a través de su función pública.
- `economy` es el único que escribe `wallets`, `gold_transactions` y
  `user_items`: aquí se le llama con importación perezosa y, si el módulo
  todavía no existe, el recibo se marca `pending_sync`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date as date_type, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.enums import (
    EventStatus,
    EventType,
    GoldSource,
    LedgerDirection,
    LevelScope,
    MissionScope,
    XPSource,
)
from app.models.gamification import DomainEvent, Streak, UserMission
from app.modules.gamification import logros, misiones, niveles, rachas, reglas, xp as motor_xp
from app.modules.gamification.recompensas import (
    AgregadorRecibo,
    ConocimientoRecibo,
    HitoRacha,
    ItemRecibo,
    LogroRecibo,
    MisionRecibo,
    NivelRecibo,
    ObjetivoDiarioRecibo,
    RachaRecibo,
    ReciboRecompensas,
)
from app.modules.gamification.servicio_config import ServicioConfig

logger = get_logger("atenea.motor")

#: Nombre del módulo productor de los eventos derivados (`domain_events.source_module`).
MODULO = "gamification"

#: Eventos de aprendizaje: alimentan agregado diario, racha, misiones y logros.
EVENTOS_APRENDIZAJE: frozenset[EventType] = frozenset(
    {
        EventType.LESSON_COMPLETED,
        EventType.QUESTION_ANSWERED,
        EventType.CHALLENGE_COMPLETED,
        EventType.REVIEW_COMPLETED,
        EventType.ASSESSMENT_COMPLETED,
        EventType.MODULE_COMPLETED,
        EventType.PATH_COMPLETED,
        EventType.STUDY_TIME_TICKED,
    }
)

#: Tipo de actividad (para el tiempo mínimo plausible A4) por evento.
TIPO_ACTIVIDAD: dict[EventType, str] = {
    EventType.LESSON_COMPLETED: "lesson",
    EventType.CHALLENGE_COMPLETED: "challenge",
    EventType.ASSESSMENT_COMPLETED: "assessment",
}

#: Fuente de XP por defecto de cada evento de aprendizaje.
FUENTE_XP: dict[EventType, XPSource] = {
    EventType.LESSON_COMPLETED: XPSource.LESSON,
    EventType.QUESTION_ANSWERED: XPSource.QUESTION,
    EventType.CHALLENGE_COMPLETED: XPSource.CHALLENGE,
    EventType.ASSESSMENT_COMPLETED: XPSource.ASSESSMENT,
    EventType.MODULE_COMPLETED: XPSource.MODULE,
    EventType.PATH_COMPLETED: XPSource.PATH,
    EventType.REVIEW_COMPLETED: XPSource.REVIEW,
}

#: Fuente de oro por defecto de cada evento de aprendizaje.
FUENTE_ORO: dict[EventType, GoldSource] = {
    EventType.LESSON_COMPLETED: GoldSource.LESSON,
    EventType.CHALLENGE_COMPLETED: GoldSource.CHALLENGE,
    EventType.ASSESSMENT_COMPLETED: GoldSource.ASSESSMENT,
    EventType.MODULE_COMPLETED: GoldSource.MODULE,
    EventType.PATH_COMPLETED: GoldSource.PATH,
    EventType.REVIEW_COMPLETED: GoldSource.REVIEW,
}

#: Fuentes de oro que son actividades: las que cuentan para el tope diario de §6.3.
FUENTES_ORO_ACTIVIDAD: list[GoldSource] = [
    GoldSource.LESSON,
    GoldSource.CHALLENGE,
    GoldSource.ASSESSMENT,
    GoldSource.MODULE,
    GoldSource.PATH,
    GoldSource.REVIEW,
]

#: Fuente de XP de la recompensa de una misión según su horizonte.
FUENTE_XP_MISION: dict[MissionScope, XPSource] = {
    MissionScope.DAILY: XPSource.DAILY_MISSION,
    MissionScope.WEEKLY: XPSource.WEEKLY_MISSION,
    MissionScope.SPECIAL: XPSource.SPECIAL_MISSION,
}

#: Fuente de oro de la recompensa de una misión según su horizonte.
FUENTE_ORO_MISION: dict[MissionScope, GoldSource] = {
    MissionScope.DAILY: GoldSource.DAILY_MISSION,
    MissionScope.WEEKLY: GoldSource.WEEKLY_MISSION,
    MissionScope.SPECIAL: GoldSource.SPECIAL_MISSION,
}


@dataclass(slots=True)
class Contexto:
    """Estado compartido por toda la cascada de un evento raíz."""

    cfg: ServicioConfig
    agregador: AgregadorRecibo
    usuario_id: uuid.UUID
    timezone: str | None
    local_date: date_type
    correlation_id: uuid.UUID | None
    profundidad: int = 0


# ---------------------------------------------------------------------------
# Puente con el módulo `economy` (importación perezosa, §1.3)
# ---------------------------------------------------------------------------


def _otorgar_oro(
    db: Session,
    ctx: Contexto,
    *,
    amount: int,
    source: GoldSource,
    reason_code: str,
    event_id: uuid.UUID | None,
    idempotency_key: str,
    momento: datetime | None = None,
    source_id: uuid.UUID | None = None,
) -> int | None:
    """Delega el crédito de oro en `economy` (único dueño de `gold_transactions`).

    Función pública del contrato de módulo::

        app.modules.economy.otorgar_oro(
            db, usuario_id, *, amount, source, reason_code, idempotency_key,
            source_id, momento, ref_event_id, correlation_id) -> GoldTransaction

    `economy` emite por su cuenta `GOLD_AWARDED` y actualiza `wallets`: por eso el
    motor no vuelve a emitirlo. Si el módulo no estuviera disponible, el importe se
    informa igual y el recibo queda `pending_sync` (§7.10 regla 5).
    """
    if amount <= 0:
        return None
    try:
        from app.modules.economy import otorgar_oro as economia_otorgar_oro  # noqa: PLC0415
    except ImportError:
        ctx.agregador.pending_sync = True
        return None
    transaccion = economia_otorgar_oro(
        db,
        ctx.usuario_id,
        amount=int(amount),
        source=source,
        reason_code=reason_code,
        idempotency_key=idempotency_key,
        source_id=source_id,
        momento=momento,
        ref_event_id=event_id,
        correlation_id=ctx.correlation_id,
    )
    return int(transaccion.balance_after) if transaccion is not None else None


def _evaluar_desbloqueos(db: Session, ctx: Contexto, evento: DomainEvent) -> list[ItemRecibo]:
    """Pide a `economy` los desbloqueos de ítems que dispara este evento (§6.13).

    Función pública del contrato de módulo::

        app.modules.economy.evaluar_desbloqueos(db, usuario_id, contexto) -> list[Item]

    Devuelve **solo los ítems recién otorgados**: es idempotente por
    `(user_id, item_id)`, así que reprocesar el evento no duplica nada.
    """
    try:
        from app.modules.economy import evaluar_desbloqueos  # noqa: PLC0415
    except ImportError:
        return []
    otorgados = (
        evaluar_desbloqueos(
            db,
            ctx.usuario_id,
            {
                "event_type": evento.event_type,
                "event_id": evento.id,
                "ahora": evento.occurred_at,
            },
        )
        or []
    )
    return [
        ItemRecibo(
            item_code=item.code,
            name=item.name,
            slot=item.slot.value if item.slot else None,
            rarity=item.rarity.value if item.rarity else None,
            origin=item.origin.value if item.origin else None,
        )
        for item in otorgados
    ]


# ---------------------------------------------------------------------------
# Emisión de eventos derivados
# ---------------------------------------------------------------------------


def clave_derivada(evento_nombre: str, usuario_id: uuid.UUID, entidad_id: Any, n: int = 1) -> str:
    """Clave de idempotencia determinista de un evento derivado (§8.3)."""
    return f"{evento_nombre}:{usuario_id}:{entidad_id}:{n}"[:120]


def _emitir_derivado(
    db: Session,
    ctx: Contexto,
    *,
    tipo: EventType,
    payload: dict[str, Any],
    idempotency_key: str,
    causante: DomainEvent,
) -> DomainEvent | None:
    """Persiste un evento derivado y lo procesa si la cascada lo permite."""
    from app.modules.gamification import eventos  # noqa: PLC0415 - evita el ciclo de importación

    if not ctx.agregador.marcar_visto(idempotency_key):
        return None

    derivado = eventos.crear_evento_dominio(
        db,
        usuario_id=ctx.usuario_id,
        tipo=tipo,
        payload=payload,
        idempotency_key=idempotency_key,
        occurred_at=causante.occurred_at,
        local_date=ctx.local_date,
        timezone=ctx.timezone,
        source_module=MODULO,
        correlation_id=ctx.correlation_id or causante.id,
        causation_id=causante.id,
    )
    if derivado is None:
        return None
    if ctx.agregador.puede_descender():
        # El contador que se incrementa tiene que ser **el que mira la guarda**.
        # Antes se subía `ctx.profundidad` y `puede_descender()` leía el del
        # agregador, que se quedaba en cero: la cascada podía descender sin
        # límite y lo único que la frenaba era que no se repitiera una clave.
        ctx.agregador.profundidad += 1
        ctx.profundidad = ctx.agregador.profundidad
        try:
            _procesar(db, ctx, derivado)
            # El evento derivado se acaba de procesar aquí mismo. Dejarlo en
            # `PENDING` hacía que el estado mintiera: hay cien logros y cincuenta
            # y seis pagos de XP marcados como pendientes que sí se pagaron. Con
            # eso, cualquier reprocesador alimentado por `PENDING` pagaría dos
            # veces la historia entera.
            derivado.processing_status = EventStatus.PROCESSED
            derivado.processed_at = utcnow()
        finally:
            ctx.agregador.profundidad -= 1
            ctx.profundidad = ctx.agregador.profundidad
    return derivado


# ---------------------------------------------------------------------------
# XP y oro
# ---------------------------------------------------------------------------


def _otorgar_y_registrar_xp(
    db: Session,
    ctx: Contexto,
    evento: DomainEvent,
    *,
    calculo: motor_xp.CalculoXP,
    source: XPSource,
    is_educational: bool,
    idempotency_key: str,
    source_id: uuid.UUID | None = None,
    es_pregunta: bool = False,
) -> int:
    """Escribe la transacción de XP, la suma al recibo y emite `XP_AWARDED`."""
    payload = dict(evento.payload or {})
    area = payload.get("knowledge_area_id")
    tema = payload.get("topic_id")
    transaccion = motor_xp.otorgar_xp(
        db,
        ctx.cfg,
        usuario_id=ctx.usuario_id,
        calculo=calculo,
        event_type=evento.event_type,
        source=source,
        local_date=ctx.local_date,
        idempotency_key=idempotency_key,
        event_id=evento.id,
        source_id=source_id,
        knowledge_area_id=uuid.UUID(str(area)) if area else None,
        topic_id=uuid.UUID(str(tema)) if tema else None,
        is_educational=is_educational,
    )
    if transaccion is None:
        return 0

    ctx.agregador.sumar_xp(
        amount=int(transaccion.amount),
        base_amount=int(transaccion.base_amount),
        multiplier=Decimal(str(transaccion.multiplier)),
        reason_code=transaccion.reason_code,
        is_educational=is_educational,
        total_after=int(transaccion.balance_after),
        es_pregunta=es_pregunta,
    )

    if int(transaccion.amount) > 0:
        _emitir_derivado(
            db,
            ctx,
            tipo=EventType.XP_AWARDED,
            payload={
                "amount": int(transaccion.amount),
                "base_amount": int(transaccion.base_amount),
                "multiplier": float(transaccion.multiplier),
                "source": source.value,
                "is_educational": is_educational,
                "knowledge_area_id": str(area) if area else None,
                "reason_code": transaccion.reason_code,
                "balance_after": int(transaccion.balance_after),
                "ref_event_id": str(evento.id),
                "counts_for_progress": payload.get("counts_for_progress", True),
            },
            idempotency_key=clave_derivada("xp-awarded", ctx.usuario_id, transaccion.id),
            causante=evento,
        )
    return int(transaccion.amount) if is_educational else 0


def _otorgar_y_registrar_oro(
    db: Session,
    ctx: Contexto,
    evento: DomainEvent,
    *,
    amount: int,
    source: GoldSource,
    reason_code: str,
    idempotency_key: str,
    source_id: uuid.UUID | None = None,
) -> None:
    """Acredita oro a través de `economy`, lo suma al recibo y emite `GOLD_AWARDED`."""
    if amount <= 0:
        return
    saldo = _otorgar_oro(
        db,
        ctx,
        amount=amount,
        source=source,
        reason_code=reason_code,
        event_id=evento.id,
        idempotency_key=idempotency_key,
        momento=evento.occurred_at,
        source_id=source_id,
    )
    ctx.agregador.sumar_oro(amount=amount, balance_after=saldo, reason_code=reason_code)


def _oro_de_actividad(db: Session, ctx: Contexto, base: int, completion_index: int) -> tuple[int, str]:
    """Aplica al oro las reglas de §6.3: nada en repeticiones y tope diario blando."""
    if base <= 0:
        return 0, ""
    if completion_index > 1:
        return 0, motor_xp.RAZON_REPETICION_0
    tramos = ctx.cfg.obtener_lista("gold.daily_softcap")
    acumulado = _oro_de_actividades_del_dia(db, ctx)
    multiplicador = Decimal("1")
    razon = motor_xp.RAZON_PRIMERA_VEZ
    for tramo in tramos:
        if acumulado > int(tramo["limit"]):
            multiplicador = Decimal(str(tramo["mult"]))
            razon = (
                motor_xp.RAZON_TOPE_50 if multiplicador >= Decimal("0.5") else motor_xp.RAZON_TOPE_10
            )
    monto = int((Decimal(base) * multiplicador).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return monto, razon


def _oro_de_actividades_del_dia(db: Session, ctx: Contexto) -> int:
    """Oro de actividades ya acreditado en la fecha local (magnitud del tope de §6.3).

    Lee el ledger de `economy` en modo **solo lectura**: escribir en
    `gold_transactions` sigue siendo competencia exclusiva de ese módulo.
    """
    from app.models.economy import GoldTransaction  # noqa: PLC0415

    return int(
        db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(GoldTransaction.amount), 0)).where(
                GoldTransaction.user_id == ctx.usuario_id,
                GoldTransaction.local_date == ctx.local_date,
                GoldTransaction.direction == LedgerDirection.CREDIT,
                GoldTransaction.source.in_(FUENTES_ORO_ACTIVIDAD),
            )
        ).scalar()
        or 0
    )


def _aplicar_reglas_de_recompensa(db: Session, ctx: Contexto, evento: DomainEvent) -> int:
    """Aplica las `reward_rules` del evento. Devuelve el XP **educativo** otorgado."""
    payload = dict(evento.payload or {})
    estado = reglas.cargar_estado_usuario(db, ctx.cfg, ctx.usuario_id)
    aplicables = reglas.reglas_aplicables(
        db, ctx.cfg, evento.event_type, payload, estado, momento=evento.occurred_at
    )
    if not aplicables:
        return 0

    completion_index = int(payload.get("completion_index", 1) or 1)
    tipo_actividad = TIPO_ACTIVIDAD.get(evento.event_type)
    tiempo_ok = True
    if tipo_actividad is not None:
        tiempo_ok = motor_xp.tiempo_plausible(
            ctx.cfg,
            tipo_actividad,
            payload.get("duration_s"),
            estimated_seconds=payload.get("estimated_seconds"),
            question_count=payload.get("question_count") or payload.get("questions_total"),
        )
    base_dia = motor_xp.xp_base_actividades_del_dia(db, ctx.usuario_id, ctx.local_date)
    educativo = 0

    for indice, regla in enumerate(aplicables, start=1):
        if regla.xp_amount:
            calculo = motor_xp.calcular_xp(
                ctx.cfg,
                base=regla.xp_amount,
                completion_index=completion_index,
                is_low_content=bool(payload.get("is_low_content", False)),
                base_acumulado_del_dia=base_dia,
                aplica_repeticion=regla.limites.respects_repeat_multiplier,
                aplica_tope_diario=regla.limites.respects_daily_cap,
                tiempo_ok=tiempo_ok,
            )
            educativo += _otorgar_y_registrar_xp(
                db,
                ctx,
                evento,
                calculo=calculo,
                source=regla.xp_source or FUENTE_XP.get(evento.event_type, XPSource.ADJUSTMENT),
                is_educational=regla.is_educational,
                idempotency_key=clave_derivada("xp", ctx.usuario_id, evento.id, indice),
            )

        if regla.gold_amount:
            indice_oro = completion_index if regla.limites.respects_repeat_multiplier else 1
            monto, razon = _oro_de_actividad(db, ctx, regla.gold_amount, indice_oro)
            if not tiempo_ok:
                monto, razon = 0, motor_xp.RAZON_TIEMPO_CORTO
            _otorgar_y_registrar_oro(
                db,
                ctx,
                evento,
                amount=monto,
                source=regla.gold_source or FUENTE_ORO.get(evento.event_type, GoldSource.ADJUSTMENT),
                reason_code=razon,
                idempotency_key=clave_derivada("gold", ctx.usuario_id, evento.id, indice),
            )
    return educativo


def _xp_de_pregunta(db: Session, ctx: Contexto, evento: DomainEvent) -> int:
    """XP de `QUESTION_ANSWERED` por fórmula (§6.2, reglas A2 y A3)."""
    payload = dict(evento.payload or {})
    leccion = payload.get("lesson_id")
    ya_pagado = (
        motor_xp.xp_preguntas_de_leccion(db, ctx.usuario_id, uuid.UUID(str(leccion))) if leccion else 0
    )
    calculo = motor_xp.calcular_xp_pregunta(
        ctx.cfg,
        attempt_no=int(payload.get("attempt_no", 1) or 1),
        is_correct=bool(payload.get("is_correct", False)),
        response_ms=payload.get("response_ms"),
        actividad_abierta=payload.get("study_activity_id") is not None
        or payload.get("assessment_attempt_id") is not None
        or payload.get("context") is not None,
        xp_preguntas_ya_pagado=ya_pagado,
    )
    return _otorgar_y_registrar_xp(
        db,
        ctx,
        evento,
        calculo=calculo,
        source=XPSource.QUESTION,
        is_educational=True,
        idempotency_key=clave_derivada("xp-question", ctx.usuario_id, evento.id),
        source_id=uuid.UUID(str(payload["question_id"])) if payload.get("question_id") else None,
        es_pregunta=True,
    )


def _xp_de_repaso(db: Session, ctx: Contexto, evento: DomainEvent) -> int:
    """XP de `REVIEW_COMPLETED`: base + aciertos con tope y máximo de repasos al día."""
    payload = dict(evento.payload or {})
    calculo = motor_xp.calcular_xp_repaso(
        ctx.cfg,
        aciertos=int(payload.get("questions_correct", 0) or 0),
        repasos_pagados_hoy=motor_xp.repasos_pagados_hoy(db, ctx.usuario_id, ctx.local_date),
    )
    return _otorgar_y_registrar_xp(
        db,
        ctx,
        evento,
        calculo=calculo,
        source=XPSource.REVIEW,
        is_educational=True,
        idempotency_key=clave_derivada("xp-review", ctx.usuario_id, evento.id),
    )


# ---------------------------------------------------------------------------
# Nivel
# ---------------------------------------------------------------------------


def _sincronizar_cache_personaje(
    db: Session, usuario_id: uuid.UUID, xp_total: int, estado: niveles.EstadoNivel
) -> None:
    """Refresca la caché desnormalizada de `characters` tras mover el XP.

    `characters.xp_total`, `level` y `rank_title` son una copia de lo que este
    motor acaba de calcular desde el ledger `xp_transactions`. La tabla es de
    `identity`, pero el único que conoce estos números es la gamificación, así
    que la caché se refresca aquí, en la misma transacción que la otorga. Sin
    esto el panel y el perfil mostrarían siempre un cero aunque el ledger tenga
    la experiencia: es la diferencia entre "gané XP" y "veo que gané XP".
    """
    from app.models.identity import (  # noqa: PLC0415 - cruce perezoso entre módulos (§1.3)
        Character,  # import perezoso: evita el ciclo
    )

    db.execute(
        sa_update(Character)
        .where(Character.user_id == usuario_id)
        .values(xp_total=xp_total, level=estado.nivel, rank_title=estado.rank_title)
    )


def _revisar_nivel(db: Session, ctx: Contexto, evento: DomainEvent, xp_antes: int) -> None:
    """Compara el nivel antes y después del XP otorgado y emite `LEVEL_UP`/`RANK_UP`."""
    xp_despues = motor_xp.xp_total(db, ctx.usuario_id)
    if xp_despues == xp_antes and ctx.agregador.level is not None:
        return

    antes = niveles.estado_nivel(db, ctx.cfg, xp_antes, LevelScope.GLOBAL)
    despues = niveles.estado_nivel(db, ctx.cfg, xp_despues, LevelScope.GLOBAL)
    _sincronizar_cache_personaje(db, ctx.usuario_id, xp_despues, despues)
    subio = despues.nivel > antes.nivel
    cambio_rango = despues.rank_title != antes.rank_title

    bono = 0
    if subio:
        bono = ctx.cfg.obtener_int("gold.level_up_bonus")

    ctx.agregador.level = NivelRecibo(
        before=antes.nivel,
        after=despues.nivel,
        leveled_up=subio,
        rank_title_before=antes.rank_title,
        rank_title_after=despues.rank_title,
        rank_changed=cambio_rango,
        xp_to_next=despues.xp_to_next,
        progress_pct=despues.progress_pct,
        gold_bonus=bono,
        unlocked_shop_rarities=[
            str(r)
            for r in niveles.desbloqueos_de_nivel(db, despues.nivel, LevelScope.GLOBAL).get(
                "shop_rarities", []
            )
        ],
    )

    if not subio:
        return

    _otorgar_y_registrar_oro(
        db,
        ctx,
        evento,
        amount=bono,
        source=GoldSource.LEVEL_UP,
        reason_code=motor_xp.RAZON_PRIMERA_VEZ,
        idempotency_key=clave_derivada("gold-level", ctx.usuario_id, despues.nivel),
    )
    _emitir_derivado(
        db,
        ctx,
        tipo=EventType.LEVEL_UP,
        payload={
            "level_before": antes.nivel,
            "level_after": despues.nivel,
            "rank_title": despues.rank_title,
            "rank_changed": cambio_rango,
            "scope": LevelScope.GLOBAL.value,
        },
        idempotency_key=clave_derivada("level-up", ctx.usuario_id, despues.nivel),
        causante=evento,
    )
    if cambio_rango:
        bono_rango = ctx.cfg.obtener_int("gold.rank_up_bonus")
        _otorgar_y_registrar_oro(
            db,
            ctx,
            evento,
            amount=bono_rango,
            source=GoldSource.RANK_UP,
            reason_code=motor_xp.RAZON_PRIMERA_VEZ,
            idempotency_key=clave_derivada("gold-rank", ctx.usuario_id, despues.nivel),
        )
        _emitir_derivado(
            db,
            ctx,
            tipo=EventType.RANK_UP,
            payload={
                "level": despues.nivel,
                "rank_title": despues.rank_title,
                "gold_bonus": bono_rango,
            },
            idempotency_key=clave_derivada("rank-up", ctx.usuario_id, despues.nivel),
            causante=evento,
        )


def _completar_conocimiento(db: Session, ctx: Contexto, evento: DomainEvent) -> None:
    """Rellena la sección `knowledge` del recibo con el XP y el nivel del área."""
    area = (evento.payload or {}).get("knowledge_area_id")
    if not area:
        return
    area_id = uuid.UUID(str(area))
    xp_area = motor_xp.xp_de_conocimiento(db, ctx.usuario_id, area_id)
    estado = niveles.estado_nivel(db, ctx.cfg, xp_area, LevelScope.KNOWLEDGE_AREA)
    ctx.agregador.knowledge = ConocimientoRecibo(
        knowledge_area_id=area_id,
        xp_after=xp_area,
        level_after=estado.nivel,
        rank_title_after=estado.rank_title,
    )


# ---------------------------------------------------------------------------
# Agregado diario, objetivo y racha
# ---------------------------------------------------------------------------


def _actualizar_dia_y_racha(db: Session, ctx: Contexto, evento: DomainEvent, xp_educativo: int) -> None:
    """Pasos 2 y 3 del orden de consumo: agregado diario, objetivo y racha."""
    payload = dict(evento.payload or {})
    if payload.get("counts_for_progress") is False:
        return

    tipo = evento.event_type
    segundos = 0
    if tipo == EventType.STUDY_TIME_TICKED:
        maximo = ctx.cfg.obtener_int("time.max_tick_s")
        segundos = min(int(payload.get("seconds", 0) or 0), maximo)

    dia_previo = rachas.obtener_o_crear_dia(db, ctx.cfg, ctx.usuario_id, ctx.local_date)
    preguntas_antes = int(dia_previo.questions_total)

    unidades = rachas.unidades_de_actividad(
        ctx.cfg,
        tipo,
        preguntas_antes=preguntas_antes,
        preguntas_despues=preguntas_antes + (1 if tipo == EventType.QUESTION_ANSWERED else 0),
    )
    es_actividad = tipo in {
        EventType.LESSON_COMPLETED,
        EventType.CHALLENGE_COMPLETED,
        EventType.REVIEW_COMPLETED,
        EventType.ASSESSMENT_COMPLETED,
    }

    dia, primera_actividad = rachas.registrar_actividad(
        db,
        ctx.cfg,
        usuario_id=ctx.usuario_id,
        local_date=ctx.local_date,
        momento=evento.occurred_at,
        educational_xp=max(0, xp_educativo),
        effective_seconds=segundos,
        activity_units=unidades,
        lessons_completed=1 if tipo == EventType.LESSON_COMPLETED else 0,
        questions_total=1 if tipo == EventType.QUESTION_ANSWERED else 0,
        questions_correct=1 if tipo == EventType.QUESTION_ANSWERED and payload.get("is_correct") else 0,
        activities_completed=1 if es_actividad else 0,
    )

    # Bono de primera actividad del día (XP educativo, no cuenta para el tope A5).
    if primera_actividad:
        bono = ctx.cfg.obtener_int("xp.first_activity_of_day")
        if bono > 0:
            extra = _otorgar_y_registrar_xp(
                db,
                ctx,
                evento,
                calculo=motor_xp.CalculoXP(
                    amount=bono,
                    base_amount=bono,
                    multiplier=Decimal("1.000"),
                    reason_code=motor_xp.RAZON_PRIMERA_VEZ,
                ),
                source=XPSource.FIRST_ACTIVITY_OF_DAY,
                is_educational=True,
                idempotency_key=clave_derivada("xp-first-activity", ctx.usuario_id, ctx.local_date),
            )
            if extra:
                dia, _ = rachas.registrar_actividad(
                    db,
                    ctx.cfg,
                    usuario_id=ctx.usuario_id,
                    local_date=ctx.local_date,
                    momento=evento.occurred_at,
                    educational_xp=extra,
                )

    objetivo = rachas.evaluar_objetivo(db, ctx.cfg, dia, momento=evento.occurred_at)

    resultado_racha: rachas.ResultadoRacha | None = None
    if rachas.dia_activo(ctx.cfg, dia):
        resultado_racha = rachas.activar_dia(
            db, ctx.cfg, ctx.usuario_id, ctx.local_date, momento=evento.occurred_at
        )

    racha_actual = resultado_racha.current if resultado_racha else _racha_actual(db, ctx.usuario_id)

    if objetivo.just_met:
        objetivo.bonus_gold = rachas.bono_de_objetivo(ctx.cfg, racha_actual)
        _otorgar_y_registrar_oro(
            db,
            ctx,
            evento,
            amount=objetivo.bonus_gold,
            source=GoldSource.DAILY_GOAL,
            reason_code=motor_xp.RAZON_PRIMERA_VEZ,
            idempotency_key=clave_derivada("gold-goal", ctx.usuario_id, ctx.local_date),
        )
        _emitir_derivado(
            db,
            ctx,
            tipo=EventType.DAILY_GOAL_MET,
            payload={
                "local_date": ctx.local_date.isoformat(),
                "goal_type": objetivo.goal_type.value,
                "goal_target": objetivo.target,
                "achieved": objetivo.progress,
                "streak_after": racha_actual,
            },
            idempotency_key=clave_derivada("daily-goal-met", ctx.usuario_id, ctx.local_date),
            causante=evento,
        )

    ctx.agregador.daily_goal = ObjetivoDiarioRecibo(
        type=objetivo.goal_type.value,
        target=objetivo.target,
        progress=objetivo.progress,
        met=objetivo.met,
        just_met=objetivo.just_met,
        bonus_gold=objetivo.bonus_gold,
    )

    if resultado_racha is not None:
        _registrar_racha_en_recibo(db, ctx, evento, resultado_racha, primera_actividad)


def _racha_actual(db: Session, usuario_id: uuid.UUID) -> int:
    """Longitud actual de la racha del usuario (0 si aún no tiene fila)."""
    valor = db.execute(sa.select(Streak.current_length).where(Streak.user_id == usuario_id)).scalar()
    return int(valor or 0)


def _registrar_racha_en_recibo(
    db: Session,
    ctx: Contexto,
    evento: DomainEvent,
    resultado: rachas.ResultadoRacha,
    primera_actividad: bool,
) -> None:
    """Vuelca la racha en el recibo y emite `STREAK_UPDATED` / `STREAK_MILESTONE_REACHED`."""
    hito = None
    if resultado.milestone_length is not None:
        hito = HitoRacha(
            length=resultado.milestone_length,
            first_time=resultado.milestone_first_time,
            reward=dict(resultado.milestone_reward or {}),
        )

    ctx.agregador.streak = RachaRecibo(
        current=resultado.current,
        best=resultado.best,
        change=resultado.change.value if resultado.change else None,
        day_status=resultado.day_status.value,
        is_first_activity_of_day=primera_actividad,
        milestone=hito,
    )

    if not resultado.cambio_efectivo:
        return

    _emitir_derivado(
        db,
        ctx,
        tipo=EventType.STREAK_UPDATED,
        payload={
            "previous_length": resultado.previous,
            "current_length": resultado.current,
            "best_length": resultado.best,
            "change": resultado.change.value if resultado.change else None,
            "day_status": resultado.day_status.value,
        },
        idempotency_key=clave_derivada("streak-updated", ctx.usuario_id, ctx.local_date),
        causante=evento,
    )

    if hito is None:
        return

    _emitir_derivado(
        db,
        ctx,
        tipo=EventType.STREAK_MILESTONE_REACHED,
        payload={
            "length": hito.length,
            "first_time": hito.first_time,
            "reward": hito.reward,
        },
        idempotency_key=clave_derivada("streak-milestone", ctx.usuario_id, hito.length),
        causante=evento,
    )


def _recompensa_de_hito(db: Session, ctx: Contexto, evento: DomainEvent) -> None:
    """Paga el XP y el oro de un hito de racha (XP de bonificación, §4.1 regla 3)."""
    payload = dict(evento.payload or {})
    recompensa = dict(payload.get("reward") or {})
    longitud = int(payload.get("length", 0) or 0)

    xp_hito = int(recompensa.get("xp", 0) or 0)
    if xp_hito:
        _otorgar_y_registrar_xp(
            db,
            ctx,
            evento,
            calculo=motor_xp.CalculoXP(xp_hito, xp_hito, Decimal("1.000"), motor_xp.RAZON_PRIMERA_VEZ),
            source=XPSource.STREAK_MILESTONE,
            is_educational=False,
            idempotency_key=clave_derivada("xp-milestone", ctx.usuario_id, longitud),
        )
    oro_hito = int(recompensa.get("gold", 0) or 0)
    if oro_hito:
        _otorgar_y_registrar_oro(
            db,
            ctx,
            evento,
            amount=oro_hito,
            source=GoldSource.STREAK_MILESTONE,
            reason_code=motor_xp.RAZON_PRIMERA_VEZ,
            idempotency_key=clave_derivada("gold-milestone", ctx.usuario_id, longitud),
        )


def _recompensa_de_mision_reclamada(db: Session, ctx: Contexto, evento: DomainEvent) -> None:
    """Paga la recompensa de una misión reclamada leyendo la fila, no el payload."""
    payload = dict(evento.payload or {})
    mision_id = payload.get("user_mission_id")
    if not mision_id:
        return
    mision = db.execute(
        sa.select(UserMission).where(
            UserMission.id == uuid.UUID(str(mision_id)), UserMission.user_id == ctx.usuario_id
        )
    ).scalar_one_or_none()
    if mision is None:
        return

    if int(mision.reward_xp) > 0:
        _otorgar_y_registrar_xp(
            db,
            ctx,
            evento,
            calculo=motor_xp.CalculoXP(
                int(mision.reward_xp), int(mision.reward_xp), Decimal("1.000"), motor_xp.RAZON_PRIMERA_VEZ
            ),
            source=FUENTE_XP_MISION.get(mision.scope, XPSource.DAILY_MISSION),
            is_educational=False,
            idempotency_key=clave_derivada("xp-mission", ctx.usuario_id, mision.id),
            source_id=mision.id,
        )
    if int(mision.reward_gold) > 0:
        _otorgar_y_registrar_oro(
            db,
            ctx,
            evento,
            amount=int(mision.reward_gold),
            source=FUENTE_ORO_MISION.get(mision.scope, GoldSource.DAILY_MISSION),
            reason_code=motor_xp.RAZON_PRIMERA_VEZ,
            idempotency_key=clave_derivada("gold-mission", ctx.usuario_id, mision.id),
            source_id=mision.id,
        )
    ctx.agregador.agregar_mision(
        MisionRecibo(
            user_mission_id=mision.id,
            template_code=mision.template_code,
            title=mision.title,
            progress=int(mision.progress),
            target=int(mision.target),
            status=mision.status.value,
            auto_claimed=bool(payload.get("auto", False)),
            reward={"xp": int(mision.reward_xp), "gold": int(mision.reward_gold)},
        )
    )


def _recompensa_de_logro(db: Session, ctx: Contexto, evento: DomainEvent) -> None:
    """Paga el XP y el oro de un logro desbloqueado (XP de bonificación)."""
    payload = dict(evento.payload or {})
    recompensa = dict(payload.get("reward") or {})
    codigo = str(payload.get("achievement_code", ""))

    xp_logro = int(recompensa.get("xp", 0) or 0)
    if xp_logro:
        _otorgar_y_registrar_xp(
            db,
            ctx,
            evento,
            calculo=motor_xp.CalculoXP(xp_logro, xp_logro, Decimal("1.000"), motor_xp.RAZON_PRIMERA_VEZ),
            source=XPSource.ACHIEVEMENT,
            is_educational=False,
            idempotency_key=clave_derivada("xp-achievement", ctx.usuario_id, codigo),
        )
    oro_logro = int(recompensa.get("gold", 0) or 0)
    if oro_logro:
        _otorgar_y_registrar_oro(
            db,
            ctx,
            evento,
            amount=oro_logro,
            source=GoldSource.ACHIEVEMENT,
            reason_code=motor_xp.RAZON_PRIMERA_VEZ,
            idempotency_key=clave_derivada("gold-achievement", ctx.usuario_id, codigo),
        )


# ---------------------------------------------------------------------------
# Misiones, logros y desbloqueos
# ---------------------------------------------------------------------------


def _cosmeticos_del_conocimiento(db: Session, evento: DomainEvent) -> None:
    """Deriva los cosméticos del conocimiento que el aprendiz acaba de crear.

    El catálogo trae tres moldes —Capa del Estudiante, Capa del Maestro e
    Insignia de la Perfección— cuyo nombre lleva el hueco `{short_name}`. Sin
    derivarlos, terminar una ruta de un conocimiento propio prometía una capa que
    no existía como fila, y el desbloqueo del paso 6 no tenía nada que otorgar.

    Los conocimientos canónicos los derivan las semillas; este camino es solo el
    de los que crea el aprendiz.
    """
    from app.models.content import KnowledgeArea  # noqa: PLC0415 - §1.3
    from app.modules.economy import plantillas  # noqa: PLC0415 - §1.3

    payload = dict(evento.payload or {})
    area_id = payload.get("knowledge_area_id") or payload.get("area_id")
    if not area_id:
        return
    area = db.get(KnowledgeArea, uuid.UUID(str(area_id)))
    if area is None:
        return
    plantillas.derivar_para_area(db, area)


def _misiones_de_la_ruta(db: Session, ctx: Contexto, evento: DomainEvent) -> None:
    """Instancia las misiones especiales de una ruta recién empezada (§5.7).

    `asignar_misiones_de_ruta` existía desde el principio, estaba exportada y no
    la llamaba nadie: la pantalla de Misiones tenía una sección de especiales
    que iba a salir vacía para siempre, sin que ninguna prueba lo notara.

    Se engancha aquí y no en los dos sitios que crean rutas —crear una propia y
    adoptar una del Reino— porque los dos pasan por `PATH_CREATED` y el motor es
    justamente quien consume los eventos. Un sitio en vez de dos, y el día que
    haya una tercera forma de empezar una ruta, esto sigue funcionando.

    La función es idempotente: si la ruta ya tiene sus misiones, las devuelve sin
    crear nada, así que adoptar dos veces no duplica.
    """
    payload = dict(evento.payload or {})
    path_id = payload.get("path_id")
    if not path_id:
        return
    area = payload.get("knowledge_area_id")
    creadas = misiones.asignar_misiones_de_ruta(
        db,
        ctx.cfg,
        usuario_id=ctx.usuario_id,
        learning_path_id=uuid.UUID(str(path_id)),
        knowledge_area_id=uuid.UUID(str(area)) if area else None,
    )
    if creadas:
        logger.info(
            "mision.ruta_instanciada",
            usuario_id=str(ctx.usuario_id),
            path_id=str(path_id),
            cuantas=len(creadas),
        )


def _avanzar_misiones(db: Session, ctx: Contexto, evento: DomainEvent) -> None:
    """Paso 4: avance de misiones y emisión de `MISSION_COMPLETED`."""
    progresos = misiones.avanzar_por_evento(
        db,
        ctx.cfg,
        usuario_id=ctx.usuario_id,
        event_type=evento.event_type,
        payload=dict(evento.payload or {}),
        event_id=evento.id,
        momento=evento.occurred_at,
    )
    for progreso in progresos:
        mision = progreso.mision
        ctx.agregador.agregar_mision(
            MisionRecibo(
                user_mission_id=mision.id,
                template_code=mision.template_code,
                title=mision.title,
                progress=int(mision.progress),
                target=int(mision.target),
                status=mision.status.value,
                reward={"xp": int(mision.reward_xp), "gold": int(mision.reward_gold)},
            )
        )
        if progreso.completada_ahora:
            _emitir_derivado(
                db,
                ctx,
                tipo=EventType.MISSION_COMPLETED,
                payload={
                    "user_mission_id": str(mision.id),
                    "template_code": mision.template_code,
                    "scope": mision.scope.value,
                    "tier": mision.tier.value if mision.tier else None,
                    "target": int(mision.target),
                    "progress": int(mision.progress),
                },
                idempotency_key=clave_derivada("mission-completed", ctx.usuario_id, mision.id),
                causante=evento,
            )


def _evaluar_logros(db: Session, ctx: Contexto, evento: DomainEvent) -> None:
    """Paso 5: evaluación de logros y emisión de `ACHIEVEMENT_UNLOCKED`."""
    estado = reglas.cargar_estado_usuario(db, ctx.cfg, ctx.usuario_id)
    resultados = logros.evaluar_por_evento(
        db,
        ctx.cfg,
        usuario_id=ctx.usuario_id,
        event_type=evento.event_type,
        payload=dict(evento.payload or {}),
        event_id=evento.id,
        estado_usuario=estado,
        momento=evento.occurred_at,
    )
    for resultado in resultados:
        for nivel in resultado.desbloqueados:
            ctx.agregador.agregar_logro(
                LogroRecibo(
                    code=nivel.achievement.code,
                    name=nivel.achievement.name,
                    tier=nivel.tier.value,
                    reward={
                        "xp": nivel.reward_xp,
                        "gold": nivel.reward_gold,
                        "title_id": nivel.title_id,
                    },
                )
            )
            _emitir_derivado(
                db,
                ctx,
                tipo=EventType.ACHIEVEMENT_UNLOCKED,
                payload={
                    "achievement_code": nivel.achievement.code,
                    "tier": nivel.tier.value,
                    "reward": {
                        "xp": nivel.reward_xp,
                        "gold": nivel.reward_gold,
                        "title_id": nivel.title_id,
                    },
                },
                idempotency_key=clave_derivada(
                    "achievement-unlocked", ctx.usuario_id, f"{nivel.achievement.code}:{nivel.tier.value}"
                ),
                causante=evento,
            )


def _aplicar_desbloqueos(db: Session, ctx: Contexto, evento: DomainEvent) -> None:
    """Paso 6: desbloqueos de ítems por conocimiento, racha, nivel o logro (§6.13)."""
    for item in _evaluar_desbloqueos(db, ctx, evento):
        ctx.agregador.agregar_item(ItemRecibo(**item) if isinstance(item, dict) else item)


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------


def _procesar(db: Session, ctx: Contexto, evento: DomainEvent) -> None:
    """Ejecuta el orden de consumo del contrato para un evento concreto."""
    tipo = evento.event_type

    # El tiempo de estudio es un caso aparte (§4.2): lo consumen el agregado del
    # día —de donde sale el objetivo en minutos— y las misiones de tiempo. No
    # otorga XP ni oro, así que no puede cambiar el nivel, desbloquear ítems ni
    # completar logros. Se atiende con ese camino corto porque llega cada treinta
    # segundos por usuario activo y no debe arrastrar el motor entero.
    if tipo == EventType.STUDY_TIME_TICKED:
        _actualizar_dia_y_racha(db, ctx, evento, 0)
        _avanzar_misiones(db, ctx, evento)
        return

    xp_antes = motor_xp.xp_total(db, ctx.usuario_id)

    # 1 · XP y oro
    xp_educativo = 0
    if tipo == EventType.QUESTION_ANSWERED:
        xp_educativo += _xp_de_pregunta(db, ctx, evento)
    elif tipo == EventType.REVIEW_COMPLETED:
        xp_educativo += _xp_de_repaso(db, ctx, evento)
    elif tipo == EventType.STREAK_MILESTONE_REACHED:
        _recompensa_de_hito(db, ctx, evento)
    elif tipo == EventType.MISSION_CLAIMED:
        _recompensa_de_mision_reclamada(db, ctx, evento)
    elif tipo == EventType.ACHIEVEMENT_UNLOCKED:
        _recompensa_de_logro(db, ctx, evento)

    if tipo not in {
        EventType.STREAK_MILESTONE_REACHED,
        EventType.MISSION_CLAIMED,
        EventType.ACHIEVEMENT_UNLOCKED,
        EventType.QUESTION_ANSWERED,
        EventType.XP_AWARDED,
        EventType.GOLD_AWARDED,
    }:
        xp_educativo += _aplicar_reglas_de_recompensa(db, ctx, evento)

    # 2 y 3 · Agregado diario, objetivo y racha (nunca con XP de bonificación).
    if tipo in EVENTOS_APRENDIZAJE:
        _actualizar_dia_y_racha(db, ctx, evento, xp_educativo)

    # Nivel: se revisa después de todo el XP del evento.
    _revisar_nivel(db, ctx, evento, xp_antes)
    if tipo in EVENTOS_APRENDIZAJE:
        _completar_conocimiento(db, ctx, evento)

    # Un conocimiento nuevo estrena sus cosméticos antes de nada: los
    # desbloqueos del paso 6 solo pueden otorgar ítems que existan.
    if tipo == EventType.KNOWLEDGE_AREA_CREATED:
        _cosmeticos_del_conocimiento(db, evento)

    # 4 y 5 · Misiones y logros. Empezar una ruta instancia primero las suyas,
    # para que el mismo evento pueda ya avanzarlas.
    if tipo == EventType.PATH_CREATED:
        _misiones_de_la_ruta(db, ctx, evento)
    _avanzar_misiones(db, ctx, evento)
    _evaluar_logros(db, ctx, evento)

    # 6 · Desbloqueos de ítems (los otorga `economy`).
    _aplicar_desbloqueos(db, ctx, evento)


def procesar_evento(
    db: Session,
    evento: DomainEvent,
    *,
    cfg: ServicioConfig | None = None,
    timezone: str | None = None,
    momento: datetime | None = None,
) -> ReciboRecompensas:
    """Procesa un evento de dominio y devuelve el `ReciboRecompensas` resultante."""
    configuracion = cfg or ServicioConfig(db)
    agregador = AgregadorRecibo(
        receipt_id=evento.id,
        event_type=evento.event_type.value,
        occurred_at=evento.occurred_at or momento or utcnow(),
    )
    agregador.config_version = configuracion.config_version()
    agregador.marcar_visto(evento.idempotency_key)

    if evento.user_id is None:
        return agregador.construir()

    ctx = Contexto(
        cfg=configuracion,
        agregador=agregador,
        usuario_id=evento.user_id,
        timezone=timezone or evento.timezone,
        local_date=evento.local_date or utcnow().date(),
        correlation_id=evento.correlation_id or evento.id,
    )
    _procesar(db, ctx, evento)
    return agregador.construir()


__all__ = [
    "EVENTOS_APRENDIZAJE",
    "FUENTE_ORO",
    "FUENTE_ORO_MISION",
    "FUENTE_XP",
    "FUENTE_XP_MISION",
    "MODULO",
    "TIPO_ACTIVIDAD",
    "Contexto",
    "clave_derivada",
    "procesar_evento",
]
