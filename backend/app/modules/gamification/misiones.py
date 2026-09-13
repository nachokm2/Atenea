"""Misiones: instanciación determinista, avance por evento, expiración y reclamo.

Contrato §3.5 (`mission_templates`, `user_missions`) y §5.7 (`missions.*`).

- **Sin IA**: el selector de las misiones diarias es determinista y ponderado; la
  semilla es `(user_id, fecha_local)`, de modo que dos llamadas del mismo día
  devuelven exactamente el mismo trío (generación perezosa desde `GET /missions`).
- **Avance por evento**: la métrica declarativa `{type, event, where, field}` de la
  plantilla decide cuánto suma cada evento. `user_missions.last_event_id` hace el
  avance idempotente.
- **Expiración**: a medianoche local; con `missions.claim.auto_on_expiry` las
  completadas se reclaman solas.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import date as date_type, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import day_start_utc, utcnow
from app.models.enums import (
    EventType,
    GoalType,
    MissionMetricType,
    MissionScope,
    MissionStatus,
    MissionTier,
)
from app.models.gamification import MissionTemplate, UserMission
from app.modules.gamification import reglas
from app.modules.gamification.servicio_config import ServicioConfig

#: Perfiles de recompensa y las claves de `game_configs` de cada nivel (§5.7).
CLAVES_RECOMPENSA: dict[str, dict[str, tuple[str, str]]] = {
    "daily_default": {
        MissionTier.EASY.value: ("xp.mission_daily_easy", "gold.mission_daily_easy"),
        MissionTier.MEDIUM.value: ("xp.mission_daily_medium", "gold.mission_daily_medium"),
        MissionTier.HARD.value: ("xp.mission_daily_hard", "gold.mission_daily_hard"),
    },
    "weekly_default": {
        MissionTier.MEDIUM.value: ("xp.mission_weekly_medium", "gold.mission_weekly_medium"),
        MissionTier.HARD.value: ("xp.mission_weekly_hard", "gold.mission_weekly_hard"),
    },
}

#: Niveles elegibles cuando la mezcla del día pide "variety".
TIERS_VARIEDAD: tuple[MissionTier, ...] = (MissionTier.EASY, MissionTier.MEDIUM, MissionTier.HARD)


@dataclass(slots=True)
class ProgresoMision:
    """Resultado de aplicar un evento a una misión."""

    mision: UserMission
    delta: int
    completada_ahora: bool


# ---------------------------------------------------------------------------
# Recompensas de una plantilla
# ---------------------------------------------------------------------------


def recompensa_de_plantilla(
    cfg: ServicioConfig, plantilla: MissionTemplate, tier: MissionTier | None
) -> tuple[int, int]:
    """XP y oro de una instancia según su perfil de recompensa (o `rewards` explícito)."""
    explicita = dict(plantilla.rewards or {})
    if explicita:
        return int(explicita.get("xp", 0)), int(explicita.get("gold", 0))

    perfil = CLAVES_RECOMPENSA.get(plantilla.reward_profile or "")
    if not perfil:
        return 0, 0
    clave_tier = (tier or MissionTier.EASY).value
    claves = perfil.get(clave_tier)
    if claves is None:
        return 0, 0
    return cfg.obtener_int(claves[0]), cfg.obtener_int(claves[1])


def resolver_parametros(plantilla: MissionTemplate, tier: MissionTier | None) -> dict[str, Any]:
    """Resuelve `params` de la plantilla para el nivel de dificultad de la instancia."""
    resueltos: dict[str, Any] = {}
    clave_tier = (tier or MissionTier.EASY).value
    for nombre, valor in dict(plantilla.params or {}).items():
        if isinstance(valor, dict):
            resueltos[nombre] = valor.get(clave_tier, next(iter(valor.values()), 0))
        else:
            resueltos[nombre] = valor
    return resueltos


def objetivo_de_parametros(parametros: dict[str, Any]) -> int:
    """Objetivo numérico de la misión: el parámetro `n`, o 1 si no lo hay."""
    valor = parametros.get("n", 1)
    try:
        return max(1, int(valor))
    except (TypeError, ValueError):
        return 1


def titulo_interpolado(plantilla: MissionTemplate, parametros: dict[str, Any]) -> str:
    """Interpola `title_template` con los parámetros resueltos."""
    try:
        return plantilla.title_template.format(**parametros)
    except (KeyError, IndexError, ValueError):
        return plantilla.title_template


# ---------------------------------------------------------------------------
# Selección determinista de las misiones diarias
# ---------------------------------------------------------------------------


def _semilla(usuario_id: uuid.UUID, fecha: date_type) -> int:
    """Semilla determinista por usuario y fecha local."""
    return int.from_bytes(f"{usuario_id}:{fecha.isoformat()}".encode(), "big", signed=False) % (2**63)


def _elegible(plantilla: MissionTemplate, contexto: dict[str, Any]) -> bool:
    """Evalúa los predicados de `eligibility` contra el contexto disponible.

    Los predicados los alimenta quien pide la asignación (normalmente el propio
    módulo al leer el estado del usuario). Un predicado del que no se sabe nada
    se considera cumplido: el MVP prefiere asignar una misión de más a dejar al
    usuario sin misiones del día.
    """
    for predicado in list(plantilla.eligibility or []):
        if isinstance(predicado, dict):
            nombre = str(predicado.get("predicate", ""))
            esperado = predicado.get("value", True)
        else:
            nombre, esperado = str(predicado), True
        if nombre not in contexto:
            continue
        numerico = isinstance(esperado, int | float) and not isinstance(esperado, bool)
        operador = "gte" if numerico else "eq"
        if not reglas.comparar(contexto[nombre], operador, esperado):
            return False
    return True


def plantillas_candidatas(
    db: Session,
    scope: MissionScope,
    *,
    goal_type: GoalType | None = None,
    contexto: dict[str, Any] | None = None,
    excluir_codigos: set[str] | None = None,
) -> list[MissionTemplate]:
    """Plantillas activas del horizonte pedido que pasan filtros y elegibilidad."""
    filas = (
        db.execute(
            sa.select(MissionTemplate)
            .where(MissionTemplate.scope == scope, MissionTemplate.is_active.is_(True))
            .order_by(MissionTemplate.code)
        )
        .scalars()
        .all()
    )
    contexto = contexto or {}
    excluir = excluir_codigos or set()
    candidatas: list[MissionTemplate] = []
    for plantilla in filas:
        if plantilla.code in excluir:
            continue
        excluidos = [str(x) for x in list(plantilla.exclude_if_goal_type or [])]
        if goal_type is not None and goal_type.value in excluidos:
            continue
        if not _elegible(plantilla, contexto):
            continue
        candidatas.append(plantilla)
    return candidatas


def _elegir_ponderado(azar: random.Random, candidatas: list[MissionTemplate]) -> MissionTemplate:
    """Elección ponderada por `weight` con un generador determinista."""
    pesos = [max(1, int(p.weight)) for p in candidatas]
    return azar.choices(candidatas, weights=pesos, k=1)[0]


def _codigos_recientes(db: Session, usuario_id: uuid.UUID, hoy: date_type, dias: int) -> set[str]:
    """Códigos de misión diaria asignados en los últimos `dias` días."""
    if dias <= 0:
        return set()
    desde = hoy - timedelta(days=dias)
    filas = db.execute(
        sa.select(UserMission.template_code).where(
            UserMission.user_id == usuario_id,
            UserMission.scope == MissionScope.DAILY,
            UserMission.assigned_for.is_not(None),
            UserMission.assigned_for >= desde,
            UserMission.assigned_for < hoy,
        )
    ).all()
    return {fila[0] for fila in filas}


def misiones_del_dia(db: Session, usuario_id: uuid.UUID, fecha: date_type) -> list[UserMission]:
    """Misiones diarias ya asignadas para esa fecha local."""
    return list(
        db.execute(
            sa.select(UserMission)
            .where(
                UserMission.user_id == usuario_id,
                UserMission.scope == MissionScope.DAILY,
                UserMission.assigned_for == fecha,
            )
            .order_by(UserMission.created_at, UserMission.template_code)
        )
        .scalars()
        .all()
    )


def instanciar(
    db: Session,
    cfg: ServicioConfig,
    *,
    usuario_id: uuid.UUID,
    plantilla: MissionTemplate,
    tier: MissionTier | None,
    assigned_for: date_type | None,
    expires_at: datetime | None,
    learning_path_id: uuid.UUID | None = None,
    knowledge_area_id: uuid.UUID | None = None,
) -> UserMission:
    """Crea una instancia de misión congelando parámetros, versión y recompensa."""
    parametros = resolver_parametros(plantilla, tier)
    xp, oro = recompensa_de_plantilla(cfg, plantilla, tier)
    mision = UserMission(
        user_id=usuario_id,
        template_id=plantilla.id,
        template_code=plantilla.code,
        template_version=int(plantilla.version),
        scope=plantilla.scope,
        tier=tier,
        params=parametros,
        title=titulo_interpolado(plantilla, parametros),
        target=objetivo_de_parametros(parametros),
        status=MissionStatus.ACTIVE,
        learning_path_id=learning_path_id,
        knowledge_area_id=knowledge_area_id,
        assigned_for=assigned_for,
        expires_at=expires_at,
        reward_xp=xp,
        reward_gold=oro,
    )
    db.add(mision)
    db.flush()
    return mision


def asignar_misiones_diarias(
    db: Session,
    cfg: ServicioConfig,
    *,
    usuario_id: uuid.UUID,
    fecha_local: date_type,
    timezone: str | None,
    goal_type: GoalType | None = None,
    contexto: dict[str, Any] | None = None,
) -> list[UserMission]:
    """Genera (de forma perezosa y determinista) las misiones diarias del usuario."""
    existentes = misiones_del_dia(db, usuario_id, fecha_local)
    if existentes:
        return existentes

    cuantas = cfg.obtener_int("missions.daily.count")
    mezcla = [str(t) for t in cfg.obtener_lista("missions.daily.tier_mix")]
    sin_repetir = cfg.obtener_int("missions.daily.no_repeat_days")
    recientes = _codigos_recientes(db, usuario_id, fecha_local, sin_repetir)

    azar = random.Random(_semilla(usuario_id, fecha_local))
    disponibles = plantillas_candidatas(
        db, MissionScope.DAILY, goal_type=goal_type, contexto=contexto, excluir_codigos=recientes
    )
    if not disponibles:
        disponibles = plantillas_candidatas(db, MissionScope.DAILY, goal_type=goal_type, contexto=contexto)
    if not disponibles:
        return []

    expira = day_start_utc(fecha_local + timedelta(days=1), timezone)
    creadas: list[UserMission] = []
    usadas: set[uuid.UUID] = set()
    for posicion in range(cuantas):
        restantes = [p for p in disponibles if p.id not in usadas]
        if not restantes:
            break
        etiqueta = mezcla[posicion] if posicion < len(mezcla) else "variety"
        tier = azar.choice(TIERS_VARIEDAD) if etiqueta == "variety" else MissionTier(etiqueta)
        plantilla = _elegir_ponderado(azar, restantes)
        usadas.add(plantilla.id)
        creadas.append(
            instanciar(
                db,
                cfg,
                usuario_id=usuario_id,
                plantilla=plantilla,
                tier=tier,
                assigned_for=fecha_local,
                expires_at=expira,
            )
        )
    return creadas


def asignar_misiones_de_ruta(
    db: Session,
    cfg: ServicioConfig,
    *,
    usuario_id: uuid.UUID,
    learning_path_id: uuid.UUID,
    knowledge_area_id: uuid.UUID | None = None,
) -> list[UserMission]:
    """Instancia las misiones especiales de una ruta (no expiran, §5.7)."""
    existentes = list(
        db.execute(
            sa.select(UserMission).where(
                UserMission.user_id == usuario_id,
                UserMission.learning_path_id == learning_path_id,
                UserMission.scope == MissionScope.SPECIAL,
            )
        )
        .scalars()
        .all()
    )
    if existentes:
        return existentes

    cuantas = cfg.obtener_int("missions.path.per_path")
    plantillas = plantillas_candidatas(db, MissionScope.SPECIAL)[:cuantas]
    return [
        instanciar(
            db,
            cfg,
            usuario_id=usuario_id,
            plantilla=plantilla,
            tier=None,
            assigned_for=None,
            expires_at=None,
            learning_path_id=learning_path_id,
            knowledge_area_id=knowledge_area_id,
        )
        for plantilla in plantillas
    ]


# ---------------------------------------------------------------------------
# Avance por evento
# ---------------------------------------------------------------------------


def misiones_activas(db: Session, usuario_id: uuid.UUID) -> list[tuple[UserMission, MissionTemplate]]:
    """Misiones activas del usuario junto a su plantilla."""
    filas = db.execute(
        sa.select(UserMission, MissionTemplate)
        .join(MissionTemplate, MissionTemplate.id == UserMission.template_id)
        .where(UserMission.user_id == usuario_id, UserMission.status == MissionStatus.ACTIVE)
        .order_by(UserMission.created_at)
    ).all()
    return [(fila[0], fila[1]) for fila in filas]


def _valor_del_campo(payload: dict[str, Any], campo: str | None) -> Any:
    """Lee el campo declarado por la métrica en el payload del evento."""
    if not campo:
        return None
    return payload.get(campo)


def _delta_de_metrica(
    metrica: dict[str, Any], mision: UserMission, payload: dict[str, Any]
) -> tuple[int, dict[str, Any] | None]:
    """Calcula el avance que aporta un evento y el nuevo estado auxiliar, si lo hay."""
    tipo = str(metrica.get("type", MissionMetricType.COUNTER.value))
    campo = metrica.get("field")
    estado = dict(mision.params or {})

    if tipo == MissionMetricType.COUNTER.value:
        return 1, None
    if tipo == MissionMetricType.SUM.value:
        valor = _valor_del_campo(payload, campo)
        return int(valor or 0), None
    if tipo == MissionMetricType.MAX.value:
        valor = int(_valor_del_campo(payload, campo) or 0)
        return max(0, valor - int(mision.progress)), None
    if tipo == MissionMetricType.FLAG.value:
        return int(mision.target) - int(mision.progress), None
    if tipo == MissionMetricType.STAT_THRESHOLD.value:
        valor = int(_valor_del_campo(payload, campo) or 0)
        return max(0, valor - int(mision.progress)), None
    if tipo == MissionMetricType.DISTINCT_COUNT.value:
        valor = _valor_del_campo(payload, campo)
        if valor is None:
            return 0, None
        vistos = [str(v) for v in estado.get("_distinct", [])]
        if str(valor) in vistos:
            return 0, None
        vistos.append(str(valor))
        estado["_distinct"] = vistos
        return 1, estado
    if tipo == MissionMetricType.CONSECUTIVE.value:
        consecutivos = int(estado.get("_consecutive", 0)) + 1
        estado["_consecutive"] = consecutivos
        return max(0, consecutivos - int(mision.progress)), estado
    return 0, None


def avanzar_por_evento(
    db: Session,
    cfg: ServicioConfig,  # noqa: ARG001 - homogeneidad de firma con el resto del motor
    *,
    usuario_id: uuid.UUID,
    event_type: EventType,
    payload: dict[str, Any],
    event_id: uuid.UUID | None = None,
    momento: datetime | None = None,
) -> list[ProgresoMision]:
    """Aplica un evento a las misiones activas del usuario (§4.1, orden 4)."""
    instante = momento or utcnow()
    if payload.get("counts_for_progress") is False:
        return []

    resultados: list[ProgresoMision] = []
    for mision, plantilla in misiones_activas(db, usuario_id):
        metrica = dict(plantilla.metric or {})
        if str(metrica.get("event", "")) != event_type.value:
            continue
        if event_id is not None and mision.last_event_id == event_id:
            continue  # idempotencia: este evento ya se aplicó a esta misión
        if not reglas.evaluar_condiciones(dict(metrica.get("where") or {}), payload):
            continue
        if mision.learning_path_id is not None and payload.get("path_id") not in (
            None,
            str(mision.learning_path_id),
        ):
            continue
        if mision.knowledge_area_id is not None and payload.get("knowledge_area_id") not in (
            None,
            str(mision.knowledge_area_id),
        ):
            continue

        delta, nuevo_estado = _delta_de_metrica(metrica, mision, payload)
        if delta <= 0:
            if nuevo_estado is not None:
                mision.params = nuevo_estado
            continue

        anterior = int(mision.progress)
        mision.progress = min(int(mision.target), anterior + delta)
        if nuevo_estado is not None:
            mision.params = nuevo_estado
        mision.last_event_id = event_id
        completada = False
        if mision.progress >= int(mision.target) and mision.status == MissionStatus.ACTIVE:
            mision.status = MissionStatus.COMPLETED
            mision.completed_at = instante
            completada = True
        db.flush()
        resultados.append(
            ProgresoMision(mision=mision, delta=mision.progress - anterior, completada_ahora=completada)
        )
    return resultados


# ---------------------------------------------------------------------------
# Expiración y reclamo
# ---------------------------------------------------------------------------


def expirar_vencidas(
    db: Session, cfg: ServicioConfig, usuario_id: uuid.UUID, *, momento: datetime | None = None
) -> list[UserMission]:
    """Expira las misiones vencidas; con `missions.claim.auto_on_expiry` autorreclama."""
    instante = momento or utcnow()
    auto = cfg.obtener_bool("missions.claim.auto_on_expiry")
    vencidas = list(
        db.execute(
            sa.select(UserMission).where(
                UserMission.user_id == usuario_id,
                UserMission.status.in_([MissionStatus.ACTIVE, MissionStatus.COMPLETED]),
                UserMission.expires_at.is_not(None),
                UserMission.expires_at <= instante,
            )
        )
        .scalars()
        .all()
    )
    afectadas: list[UserMission] = []
    for mision in vencidas:
        if mision.status == MissionStatus.COMPLETED and auto and mision.claimed_at is None:
            mision.claimed_at = instante
            mision.status = MissionStatus.CLAIMED
        elif mision.status == MissionStatus.ACTIVE:
            mision.status = MissionStatus.EXPIRED
        afectadas.append(mision)
    if afectadas:
        db.flush()
    return afectadas


def marcar_reclamada(
    db: Session, mision: UserMission, *, momento: datetime | None = None
) -> bool:
    """Marca la misión como reclamada. `False` si ya lo estaba (idempotencia)."""
    if mision.claimed_at is not None or mision.status == MissionStatus.CLAIMED:
        return False
    mision.claimed_at = momento or utcnow()
    mision.status = MissionStatus.CLAIMED
    db.flush()
    return True


def segundos_hasta_reinicio(fecha_local: date_type, timezone: str | None, momento: datetime | None = None) -> int:
    """Segundos hasta la medianoche local (campo `resets_in_seconds` de §7.9)."""
    instante = momento or utcnow()
    proxima = day_start_utc(fecha_local + timedelta(days=1), timezone)
    return max(0, int((proxima - instante).total_seconds()))


__all__ = [
    "CLAVES_RECOMPENSA",
    "TIERS_VARIEDAD",
    "ProgresoMision",
    "asignar_misiones_de_ruta",
    "asignar_misiones_diarias",
    "avanzar_por_evento",
    "expirar_vencidas",
    "instanciar",
    "marcar_reclamada",
    "misiones_activas",
    "misiones_del_dia",
    "objetivo_de_parametros",
    "plantillas_candidatas",
    "recompensa_de_plantilla",
    "resolver_parametros",
    "segundos_hasta_reinicio",
    "titulo_interpolado",
]
