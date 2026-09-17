"""Endpoints de gamificación del contrato §7.8 y §7.9.

Este router se monta bajo `/api/v1` (lo ensambla el agente de integración):

- `GET  /missions` · `POST /missions/{user_mission_id}/claim`
- `GET  /achievements`
- `GET  /streak` · `GET /streak/calendar`
- `GET  /daily-goal` · `PUT /daily-goal` · recomendación adaptativa
- `GET  /notifications` · `POST /notifications/{id}/read` · `POST /notifications/read-all`

Los esquemas de respuesta viven aquí porque `app/schemas/gamification.py` es de
otro agente; los nombres de campo son los del contrato, sin traducir.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type, datetime
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.deps import CurrentUser, DbSession, IdempotencyDep
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.time import isoformat_z, utcnow
from app.models.enums import (
    GoalType,
    LevelScope,
    MissionScope,
    MissionStatus,
    NotificationStatus,
)
from app.models.gamification import Notification, UserMission
from app.modules.gamification import avisos, eventos, logros, misiones, motor, niveles, rachas
from app.modules.gamification.recompensas import ReciboRecompensas
from app.modules.gamification.servicio_config import ServicioConfig

router = APIRouter()


# ---------------------------------------------------------------------------
# Esquemas de salida
# ---------------------------------------------------------------------------


class _Out(BaseModel):
    """Base de los esquemas de salida (se construyen desde el ORM)."""

    model_config = ConfigDict(from_attributes=True)


class LevelOut(_Out):
    """Una fila de la curva de niveles tal como la dibuja la app."""

    level: int
    xp_required: int
    xp_delta: int
    rank_title: str
    is_rank_start: bool = False
    unlocks: dict[str, Any] = Field(default_factory=dict)


class PublicConfigOut(_Out):
    """Todo lo que la app necesita para dibujar sin preguntar dos veces (§7.9).

    Es la única ruta pública además de la de salud: el cliente la pide antes de
    iniciar sesión para poder pintar barras, precios y títulos de rango. Solo
    salen las claves marcadas `is_public`; las reglas anti-abuso nunca.
    """

    config_version: int
    values: dict[str, Any] = Field(default_factory=dict)
    levels: list[LevelOut] = Field(default_factory=list)
    knowledge_levels: list[LevelOut] = Field(default_factory=list)


class MissionOut(_Out):
    """Una misión asignada tal como la ve la app (P19)."""

    user_mission_id: uuid.UUID
    template_code: str
    scope: str
    tier: str | None = None
    title: str
    target: int
    progress: int
    status: str
    expires_at: datetime | None = None
    reward: dict[str, Any] = Field(default_factory=dict)


class MissionsOut(_Out):
    """Respuesta de `GET /missions`."""

    daily: list[MissionOut] = Field(default_factory=list)
    special: list[MissionOut] = Field(default_factory=list)
    weekly: list[MissionOut] = Field(default_factory=list)
    resets_in_seconds: int = 0


class AchievementOut(_Out):
    """Entrada de la sala de trofeos (P20)."""

    code: str
    name: str
    category: str
    visibility: str
    highest_tier: str | None = None
    tiers: list[dict[str, Any]] = Field(default_factory=list)
    progress_pct: float = 0.0
    unlocked_at: datetime | None = None


class PageInfo(_Out):
    """Sobre de paginación del contrato §8.2."""

    limit: int
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None


class PageAchievements(_Out):
    """Página de logros."""

    items: list[AchievementOut] = Field(default_factory=list)
    page: PageInfo


class StreakOut(_Out):
    """Respuesta de `GET /streak` (P18)."""

    current: int
    best: int
    status: str
    total_active_days: int
    grace_available: bool
    next_milestone: dict[str, Any] | None = None


class StreakDayOut(_Out):
    """Día del calendario mensual."""

    date: date_type
    day_status: str
    goal_met: bool
    educational_xp: int
    minutes: int
    activities: int


class StreakCalendarOut(_Out):
    """Respuesta de `GET /streak/calendar`."""

    month: str
    days: list[StreakDayOut] = Field(default_factory=list)
    active_days: int = 0
    best_length: int = 0


class DailyGoalOut(_Out):
    """Respuesta de `GET /daily-goal` y `PUT /daily-goal`."""

    type: str
    target: int
    progress: int
    met: bool
    effective_from: date_type
    pending_type: str | None = None
    pending_target: int | None = None
    pending_from: date_type | None = None
    recommendation: dict[str, Any] = Field(default_factory=dict)


class DailyGoalIn(BaseModel):
    """Cuerpo de `PUT /daily-goal`."""

    type: GoalType
    target: int


class NotificationOut(_Out):
    """Entrada de la bandeja in-app."""

    id: uuid.UUID
    notification_type: str
    channel: str
    status: str
    title: str
    body: str
    deep_link: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    scheduled_for: datetime | None = None
    sent_at: datetime | None = None
    read_at: datetime | None = None
    dismissed_at: datetime | None = None
    created_at: datetime


class PageNotifications(_Out):
    """Página de notificaciones."""

    items: list[NotificationOut] = Field(default_factory=list)
    page: PageInfo


# ---------------------------------------------------------------------------
# Utilidades comunes
# ---------------------------------------------------------------------------


def _contexto(db: DbSession, usuario: Any) -> tuple[ServicioConfig, str, date_type]:
    """Configuración, zona horaria y fecha local del usuario autenticado."""
    cfg = ServicioConfig(db)
    zona = str(getattr(usuario, "timezone", None) or "America/Santiago")
    return cfg, zona, rachas.fecha_local_de(zona)


def _mision_out(mision: UserMission) -> MissionOut:
    """Proyecta una instancia de misión al esquema de salida."""
    return MissionOut(
        user_mission_id=mision.id,
        template_code=mision.template_code,
        scope=mision.scope.value,
        tier=mision.tier.value if mision.tier else None,
        title=mision.title,
        target=int(mision.target),
        progress=int(mision.progress),
        status=mision.status.value,
        expires_at=mision.expires_at,
        reward={"xp": int(mision.reward_xp), "gold": int(mision.reward_gold)},
    )


# ---------------------------------------------------------------------------
# Misiones (§7.9)
# ---------------------------------------------------------------------------


def _pagar_autorreclamadas(db: DbSession, cfg: ServicioConfig, usuario_id: uuid.UUID) -> None:
    """Expira lo vencido y paga de verdad lo que el autorreclamo da por cobrado.

    `missions.claim.auto_on_expiry` promete que «al expirar el periodo se
    reclaman solas las misiones completadas», y `expirar_vencidas` mueve la fila
    a `CLAIMED`. Pero la recompensa no la otorga el estado de la fila sino el
    evento: sin este bucle, el aprendiz cumplía su misión del día, se le pasaba
    reclamarla antes de medianoche, y la perdía entera —además de recibir un 409
    si lo intentaba después, porque `claimed_at` ya no era nulo.

    La clave de idempotencia es determinista y cuelga de la misión, así que abrir
    el tablón dos veces no paga dos veces; y como `registrar_evento` reconstruye
    el recibo de un evento ya existente, tampoco lo hace una petición reintentada.

    El recibo se descarta aquí a sabiendas: `MissionsOut` no lo transporta, así
    que la recompensa llega al monedero sin celebración. Es peor que celebrarla y
    mucho mejor que perderla; encolar la celebración es trabajo aparte y no debe
    colarse en una petición de lectura.
    """
    for mision in misiones.expirar_vencidas(db, cfg, usuario_id):
        if mision.status != MissionStatus.CLAIMED:
            continue
        eventos.registrar_evento(
            db,
            usuario_id=usuario_id,
            tipo=eventos.TipoEvento.MISSION_CLAIMED,
            payload={
                "user_mission_id": str(mision.id),
                "auto": True,
                "reward": {"xp": int(mision.reward_xp), "gold": int(mision.reward_gold)},
            },
            idempotency_key=motor.clave_derivada(
                "mission-claimed-auto", usuario_id, mision.id
            ),
            source_module="gamification",
            cfg=cfg,
        )


@router.get("/missions", response_model=MissionsOut, summary="Misiones del día y de ruta")
def listar_misiones(db: DbSession, usuario: CurrentUser) -> MissionsOut:
    """Devuelve las misiones diarias (generadas de forma perezosa) y las especiales."""
    cfg, zona, hoy = _contexto(db, usuario)
    _pagar_autorreclamadas(db, cfg, usuario.id)
    objetivo = rachas.obtener_o_crear_objetivo(db, cfg, usuario.id, hoy)
    diarias = misiones.asignar_misiones_diarias(
        db,
        cfg,
        usuario_id=usuario.id,
        fecha_local=hoy,
        timezone=zona,
        goal_type=objetivo.goal_type,
        # Sin esto, los predicados de elegibilidad no se evalúan y el tablón se
        # llena de encargos que el aprendiz no puede cumplir.
        contexto=misiones.contexto_de(db, usuario.id, hoy),
    )
    especiales = list(
        db.execute(
            sa.select(UserMission)
            .where(
                UserMission.user_id == usuario.id,
                UserMission.scope == MissionScope.SPECIAL,
                UserMission.status.in_([MissionStatus.ACTIVE, MissionStatus.COMPLETED]),
            )
            .order_by(UserMission.created_at)
        )
        .scalars()
        .all()
    )
    semanales = list(
        db.execute(
            sa.select(UserMission)
            .where(
                UserMission.user_id == usuario.id,
                UserMission.scope == MissionScope.WEEKLY,
                UserMission.status.in_([MissionStatus.ACTIVE, MissionStatus.COMPLETED]),
            )
            .order_by(UserMission.created_at)
        )
        .scalars()
        .all()
    )
    return MissionsOut(
        daily=[_mision_out(m) for m in diarias],
        special=[_mision_out(m) for m in especiales],
        weekly=[_mision_out(m) for m in semanales],
        resets_in_seconds=misiones.segundos_hasta_reinicio(hoy, zona),
    )


@router.post(
    "/missions/{user_mission_id}/claim",
    response_model=ReciboRecompensas,
    summary="Reclama la recompensa de una misión completada",
)
def reclamar_mision(
    user_mission_id: uuid.UUID,
    db: DbSession,
    usuario: CurrentUser,
    idem: IdempotencyDep,
) -> ReciboRecompensas:
    """Reclama una misión completada y devuelve el `RewardsReceipt` (§7.9)."""
    clave = idem.require()
    cfg, _zona, _hoy = _contexto(db, usuario)

    previo = eventos.buscar_por_clave(db, clave)
    if previo is not None:
        return eventos.reconstruir_recibo(db, previo, cfg)

    mision = db.execute(
        sa.select(UserMission).where(
            UserMission.id == user_mission_id, UserMission.user_id == usuario.id
        )
    ).scalar_one_or_none()
    if mision is None:
        raise NotFound()
    if mision.status != MissionStatus.COMPLETED or mision.claimed_at is not None:
        raise Conflict("Esta misión todavía no se puede reclamar.")

    misiones.marcar_reclamada(db, mision)
    return eventos.registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=eventos.TipoEvento.MISSION_CLAIMED,
        payload={
            "user_mission_id": str(mision.id),
            "auto": False,
            "reward": {"xp": int(mision.reward_xp), "gold": int(mision.reward_gold)},
        },
        idempotency_key=clave,
        source_module="gamification",
        cfg=cfg,
    )


# ---------------------------------------------------------------------------
# Logros (§7.9)
# ---------------------------------------------------------------------------


@router.get("/achievements", response_model=PageAchievements, summary="Sala de trofeos")
def listar_logros(
    db: DbSession,
    usuario: CurrentUser,
    state: Annotated[str, Query(pattern="^(all|unlocked|in_progress)$")] = "all",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageAchievements:
    """Catálogo de logros con el progreso del usuario y filtro por estado."""
    filas = logros.progreso_de_usuario(db, usuario.id)
    salida: list[AchievementOut] = []
    for logro, progreso in filas:
        desbloqueado = progreso is not None and progreso.highest_tier is not None
        if state == "unlocked" and not desbloqueado:
            continue
        if state == "in_progress" and desbloqueado:
            continue
        salida.append(
            AchievementOut(
                code=logro.code,
                name=logro.name,
                category=logro.category.value,
                visibility=logro.visibility.value,
                highest_tier=progreso.highest_tier.value if desbloqueado else None,
                tiers=list(logro.tiers or []),
                progress_pct=float(progreso.progress_pct) if progreso else 0.0,
                unlocked_at=progreso.first_unlocked_at if progreso else None,
            )
        )
    total = len(salida)
    return PageAchievements(
        items=salida[:limit],
        page=PageInfo(limit=limit, next_cursor=None, has_more=total > limit, total=total),
    )


# ---------------------------------------------------------------------------
# Racha y calendario (§7.8)
# ---------------------------------------------------------------------------


@router.get("/streak", response_model=StreakOut, summary="Estado de la racha")
def obtener_racha(db: DbSession, usuario: CurrentUser) -> StreakOut:
    """Racha actual, mejor racha, estado visible y próximo hito con su recompensa."""
    cfg, _zona, hoy = _contexto(db, usuario)
    racha = rachas.obtener_o_crear_racha(db, usuario.id)
    return StreakOut(
        current=int(racha.current_length),
        best=int(racha.best_length),
        status=rachas.estado_visible(racha, hoy, cfg),
        total_active_days=int(racha.total_active_days),
        grace_available=rachas.gracia_disponible(cfg, racha, f"{hoy.year:04d}-{hoy.month:02d}"),
        next_milestone=rachas.proximo_hito(cfg, int(racha.current_length)),
    )


@router.get("/streak/calendar", response_model=StreakCalendarOut, summary="Calendario mensual")
def obtener_calendario(
    db: DbSession,
    usuario: CurrentUser,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
) -> StreakCalendarOut:
    """Calendario del mes local pedido (`month=2026-09`; por defecto, el mes en curso)."""
    cfg, _zona, hoy = _contexto(db, usuario)
    if month:
        anio, mes = int(month[:4]), int(month[5:7])
        if not 1 <= mes <= 12:
            raise ValidationFailed(
                "El mes debe tener el formato AAAA-MM.",
                field_errors=[{"field": "month", "message": "Formato esperado: AAAA-MM."}],
            )
    else:
        anio, mes = hoy.year, hoy.month

    dias = rachas.calendario_mensual(db, usuario.id, anio, mes)
    racha = rachas.obtener_o_crear_racha(db, usuario.id)
    return StreakCalendarOut(
        month=f"{anio:04d}-{mes:02d}",
        days=[
            StreakDayOut(
                date=dia.local_date,
                day_status=dia.day_status.value,
                goal_met=dia.goal_met_at is not None,
                educational_xp=int(dia.educational_xp),
                minutes=int(dia.effective_seconds // 60),
                activities=int(dia.activity_units),
            )
            for dia in dias
        ],
        active_days=sum(1 for dia in dias if rachas.dia_activo(cfg, dia)),
        best_length=int(racha.best_length),
    )


# ---------------------------------------------------------------------------
# Objetivo diario (§7.8)
# ---------------------------------------------------------------------------


def _objetivo_out(db: DbSession, cfg: ServicioConfig, usuario_id: uuid.UUID, hoy: date_type) -> DailyGoalOut:
    """Proyecta el objetivo diario vigente y el progreso de hoy."""
    objetivo = rachas.obtener_o_crear_objetivo(db, cfg, usuario_id, hoy)
    dia = rachas.obtener_o_crear_dia(db, cfg, usuario_id, hoy)
    return DailyGoalOut(
        type=objetivo.goal_type.value,
        target=int(objetivo.target),
        progress=rachas.progreso_objetivo(dia),
        met=dia.goal_met_at is not None,
        effective_from=objetivo.effective_from,
        pending_type=objetivo.pending_type.value if objetivo.pending_type else None,
        pending_target=objetivo.pending_target,
        pending_from=objetivo.pending_from,
        recommendation=dict(objetivo.recommendation or {}),
    )


@router.get("/daily-goal", response_model=DailyGoalOut, summary="Objetivo diario vigente")
def obtener_objetivo(db: DbSession, usuario: CurrentUser) -> DailyGoalOut:
    """Objetivo vigente, progreso de hoy y recomendación pendiente."""
    cfg, _zona, hoy = _contexto(db, usuario)
    return _objetivo_out(db, cfg, usuario.id, hoy)


@router.put("/daily-goal", response_model=DailyGoalOut, summary="Cambia el objetivo diario")
def cambiar_objetivo(cuerpo: DailyGoalIn, db: DbSession, usuario: CurrentUser) -> DailyGoalOut:
    """Cambia tipo y meta: las subidas rigen ya; las bajadas, al día siguiente."""
    cfg, _zona, hoy = _contexto(db, usuario)
    opciones = {
        GoalType.MINUTES: "goal.minutes.options",
        GoalType.ACTIVITIES: "goal.activities.options",
        GoalType.XP: "goal.xp.options",
    }[cuerpo.type]
    permitidos = [int(v) for v in cfg.obtener_lista(opciones)]
    if permitidos and int(cuerpo.target) not in permitidos:
        raise ValidationFailed(
            "Ese objetivo no está entre las opciones disponibles.",
            field_errors=[{"field": "target", "message": f"Valores permitidos: {permitidos}."}],
        )
    rachas.cambiar_objetivo(db, cfg, usuario.id, hoy, goal_type=cuerpo.type, target=int(cuerpo.target))
    return _objetivo_out(db, cfg, usuario.id, hoy)


@router.post(
    "/daily-goal/recommendation/accept",
    response_model=DailyGoalOut,
    summary="Acepta la recomendación adaptativa",
)
def aceptar_recomendacion(db: DbSession, usuario: CurrentUser) -> DailyGoalOut:
    """Aplica la recomendación adaptativa calculada por el sistema (§6.11)."""
    cfg, _zona, hoy = _contexto(db, usuario)
    objetivo = rachas.obtener_o_crear_objetivo(db, cfg, usuario.id, hoy)
    recomendacion = dict(objetivo.recommendation or {})
    if not recomendacion.get("suggested_target"):
        raise Conflict("No hay ninguna recomendación pendiente.")
    rachas.cambiar_objetivo(
        db,
        cfg,
        usuario.id,
        hoy,
        goal_type=GoalType(recomendacion.get("suggested_type", objetivo.goal_type.value)),
        target=int(recomendacion["suggested_target"]),
    )
    objetivo.recommendation = {}
    objetivo.recommendation_shown_at = utcnow()
    db.flush()
    return _objetivo_out(db, cfg, usuario.id, hoy)


@router.post(
    "/daily-goal/recommendation/dismiss",
    status_code=204,
    summary="Rechaza la recomendación adaptativa",
)
def rechazar_recomendacion(db: DbSession, usuario: CurrentUser) -> Response:
    """Rechaza la recomendación: no se repite en `goal.adapt.rejected_cooldown_days`."""
    cfg, _zona, hoy = _contexto(db, usuario)
    objetivo = rachas.obtener_o_crear_objetivo(db, cfg, usuario.id, hoy)
    objetivo.recommendation_rejected_at = utcnow()
    objetivo.recommendation = {}
    db.flush()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Notificaciones (§7.9)
# ---------------------------------------------------------------------------


@router.get("/notifications", response_model=PageNotifications, summary="Bandeja in-app")
def listar_notificaciones(
    db: DbSession,
    usuario: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> PageNotifications:
    """Notificaciones **entregadas**, de la más reciente a la más antigua.

    Lo que sigue `PENDING` está programado para más tarde y no se enseña: un
    recordatorio de las siete de la tarde leído a las diez de la mañana deja de
    ser un recordatorio. Lo que quedó `FAILED` nunca se entregó.

    Se ordena y se pagina por `sent_at`, que es cuando el aviso llegó de verdad,
    y no por `created_at`, que es cuando se decidió mandarlo.
    """
    consulta = (
        sa.select(Notification)
        .where(
            Notification.user_id == usuario.id,
            Notification.status.in_(avisos.ESTADOS_VISIBLES),
        )
        .order_by(Notification.sent_at.desc().nullslast(), Notification.id.desc())
        .limit(limit + 1)
    )
    corte = _corte_de_bandeja(avisos.decodificar_cursor(cursor))
    if corte is not None:
        # La comparación va con los tipos ya resueltos en Python: pasar el
        # instante como texto hace que PostgreSQL lo tome por `varchar` y no
        # encuentre ningún operador contra un `timestamptz`.
        consulta = consulta.where(sa.tuple_(Notification.sent_at, Notification.id) < corte)

    filas = list(db.execute(consulta).scalars().all())
    hay_mas = len(filas) > limit
    filas = filas[:limit]

    siguiente = None
    if hay_mas and filas:
        ultima = filas[-1]
        siguiente = avisos.codificar_cursor(
            {
                "sent_at": isoformat_z(ultima.sent_at) if ultima.sent_at else None,
                "id": str(ultima.id),
            }
        )
    return PageNotifications(
        items=[NotificationOut.model_validate(fila) for fila in filas],
        page=PageInfo(limit=limit, next_cursor=siguiente, has_more=hay_mas, total=None),
    )


def _corte_de_bandeja(clave: dict[str, Any] | None) -> tuple[datetime, uuid.UUID] | None:
    """Traduce el cursor de la bandeja al par `(sent_at, id)` que ordena la página."""
    if not clave or not clave.get("sent_at") or not clave.get("id"):
        return None
    try:
        momento = datetime.fromisoformat(str(clave["sent_at"]).replace("Z", "+00:00"))
        identificador = uuid.UUID(str(clave["id"]))
    except ValueError as exc:
        raise ValidationFailed(
            "El cursor de paginación no es válido.",
            field_errors=[{"field": "cursor", "message": "Cursor ilegible."}],
        ) from exc
    return momento, identificador


@router.post("/notifications/{notification_id}/read", status_code=204, summary="Marca como leída")
def marcar_leida(notification_id: uuid.UUID, db: DbSession, usuario: CurrentUser) -> Response:
    """Marca una notificación como leída."""
    notificacion = db.execute(
        sa.select(Notification).where(
            Notification.id == notification_id, Notification.user_id == usuario.id
        )
    ).scalar_one_or_none()
    if notificacion is None:
        raise NotFound()
    if notificacion.read_at is None:
        notificacion.read_at = utcnow()
        notificacion.status = NotificationStatus.READ
        db.flush()
    return Response(status_code=204)


@router.post("/notifications/read-all", status_code=204, summary="Marca todas como leídas")
def marcar_todas_leidas(db: DbSession, usuario: CurrentUser) -> Response:
    """Marca como leídas las notificaciones **entregadas** que siguen sin leer.

    El filtro por estado no es cosmético: sin él, «marcar todas como leídas»
    daría por leídos los avisos aún programados, que el aprendiz no ha visto.
    """
    ahora = utcnow()
    db.execute(
        sa.update(Notification)
        .where(
            Notification.user_id == usuario.id,
            Notification.status == NotificationStatus.SENT,
            Notification.read_at.is_(None),
        )
        .values(read_at=ahora, status=NotificationStatus.READ)
    )
    db.flush()
    return Response(status_code=204)


def _curva(db: DbSession, cfg: ServicioConfig, scope: LevelScope) -> list[LevelOut]:  # noqa: ARG001 - firma fijada por quien llama
    """Curva materializada de `level_definitions` para un ámbito."""
    return [
        LevelOut(
            level=fila.level,
            xp_required=int(fila.xp_required),
            xp_delta=int(fila.xp_delta),
            rank_title=fila.rank_title,
            is_rank_start=bool(fila.is_rank_start),
            unlocks=dict(fila.unlocks or {}),
        )
        for fila in niveles.definiciones_de(db, scope)
    ]


@router.get(
    "/config/public",
    response_model=PublicConfigOut,
    summary="Parámetros públicos del juego, curva de niveles y colores de rareza",
)
def configuracion_publica(db: DbSession, respuesta: Response) -> PublicConfigOut:
    """Devuelve lo que la app necesita para dibujar, sin exigir sesión (§7.9).

    La app la pide al arrancar y la guarda. La cabecera `X-Config-Version` viaja
    en todas las respuestas: cuando el cliente ve una versión mayor que la suya,
    vuelve aquí en vez de quedarse con precios o umbrales viejos.
    """
    cfg = ServicioConfig(db)
    version = cfg.config_version()
    respuesta.headers["X-Config-Version"] = str(version)
    return PublicConfigOut(
        config_version=version,
        values=cfg.publicas(),
        levels=_curva(db, cfg, LevelScope.GLOBAL),
        knowledge_levels=_curva(db, cfg, LevelScope.KNOWLEDGE_AREA),
    )


__all__ = [
    "AchievementOut",
    "DailyGoalIn",
    "DailyGoalOut",
    "MissionOut",
    "MissionsOut",
    "NotificationOut",
    "PageAchievements",
    "PageInfo",
    "PageNotifications",
    "PublicConfigOut",
    "StreakCalendarOut",
    "StreakDayOut",
    "StreakOut",
    "router",
]
