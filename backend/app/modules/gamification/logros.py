"""Logros: evaluación declarativa por evento y desbloqueo idempotente (§3.5, §5.7).

La regla de un logro es el JSONB `achievements.rule`::

    {type, event, where, success_when, reset_when, stat, op, on_events}

`type` usa los mismos tipos que las misiones (`MissionMetricType`), de modo que
hay **un solo evaluador** para ambas mecánicas. Los niveles viven en
`achievements.tiers` (`[{tier, target, reward}]`, objetivos crecientes) y la
recompensa cae por defecto en `achievements.reward.<tier>` de `game_configs`.

Idempotencia: `user_achievements.last_event_id` evita que un evento reprocesado
vuelva a avanzar el contador, y un nivel ya presente en `unlocked_tiers` **nunca**
se vuelve a desbloquear.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import isoformat_z, utcnow
from app.models.enums import AchievementTier, EventType, MissionMetricType
from app.models.gamification import Achievement, UserAchievement
from app.modules.gamification import reglas
from app.modules.gamification.servicio_config import ServicioConfig

#: Clave de `game_configs` con la recompensa por defecto de cada nivel.
CLAVE_RECOMPENSA_TIER = "achievements.reward.{tier}"


@dataclass(slots=True)
class NivelDesbloqueado:
    """Un nivel de logro desbloqueado por un evento."""

    achievement: Achievement
    tier: AchievementTier
    reward_xp: int
    reward_gold: int
    title_id: str | None = None


@dataclass(slots=True)
class ResultadoLogro:
    """Estado de un logro tras aplicar un evento."""

    achievement: Achievement
    progreso: UserAchievement
    desbloqueados: list[NivelDesbloqueado] = field(default_factory=list)


def _obtener_o_crear_progreso(db: Session, usuario_id: uuid.UUID, logro: Achievement) -> UserAchievement:
    """Fila de `user_achievements` del par usuario-logro, creada si falta."""
    progreso = db.execute(
        sa.select(UserAchievement).where(
            UserAchievement.user_id == usuario_id, UserAchievement.achievement_id == logro.id
        )
    ).scalar_one_or_none()
    if progreso is None:
        progreso = UserAchievement(user_id=usuario_id, achievement_id=logro.id)
        db.add(progreso)
        db.flush()
    return progreso


def logros_para_evento(db: Session, event_type: EventType) -> list[Achievement]:
    """Logros activos cuya regla escucha ese evento (`rule.event` u `on_events`)."""
    activos = (
        db.execute(sa.select(Achievement).where(Achievement.is_active.is_(True)).order_by(Achievement.sort_order))
        .scalars()
        .all()
    )
    interesados: list[Achievement] = []
    for logro in activos:
        regla = dict(logro.rule or {})
        eventos = {str(regla.get("event", ""))} | {str(e) for e in list(regla.get("on_events") or [])}
        if event_type.value in eventos:
            interesados.append(logro)
    return interesados


def recompensa_de_nivel(cfg: ServicioConfig, nivel: dict[str, Any]) -> tuple[int, int, str | None]:
    """XP, oro y título de un nivel: `tiers[].reward` manda; si no, `game_configs`."""
    recompensa = dict(nivel.get("reward") or {})
    tier = str(nivel.get("tier", AchievementTier.SINGLE.value))
    if not recompensa:
        recompensa = cfg.obtener_json(CLAVE_RECOMPENSA_TIER.format(tier=tier), {})
    return (
        int(recompensa.get("xp", 0)),
        int(recompensa.get("gold", 0)),
        recompensa.get("title_id"),
    )


def _valor_actual(regla: dict[str, Any], progreso: UserAchievement) -> int:
    """Magnitud con la que se comparan los objetivos de los niveles."""
    if str(regla.get("type", "")) == MissionMetricType.CONSECUTIVE.value:
        return int(progreso.max_consecutive)
    return int(progreso.counter)


def _aplicar_metrica(
    regla: dict[str, Any], progreso: UserAchievement, payload: dict[str, Any], hechos: dict[str, Any]
) -> bool:
    """Actualiza el estado del logro con un evento. Devuelve si algo cambió."""
    tipo = str(regla.get("type", MissionMetricType.COUNTER.value))
    campo = regla.get("field") or regla.get("stat")

    if tipo == MissionMetricType.COUNTER.value:
        progreso.counter = int(progreso.counter) + 1
        return True
    if tipo == MissionMetricType.SUM.value:
        progreso.counter = int(progreso.counter) + int(payload.get(str(campo), 0) or 0)
        return True
    if tipo == MissionMetricType.MAX.value:
        valor = int(payload.get(str(campo), 0) or 0)
        if valor > int(progreso.counter):
            progreso.counter = valor
            return True
        return False
    if tipo == MissionMetricType.FLAG.value:
        if int(progreso.counter) >= 1:
            return False
        progreso.counter = 1
        return True
    if tipo == MissionMetricType.STAT_THRESHOLD.value:
        valor = int(hechos.get(str(campo), payload.get(str(campo), 0)) or 0)
        if valor > int(progreso.counter):
            progreso.counter = valor
            return True
        return False
    if tipo == MissionMetricType.DISTINCT_COUNT.value:
        valor = payload.get(str(campo))
        if valor is None:
            return False
        vistos = [str(v) for v in list(progreso.distinct_values or [])]
        if str(valor) in vistos:
            return False
        vistos.append(str(valor))
        progreso.distinct_values = vistos
        progreso.counter = len(vistos)
        return True
    if tipo == MissionMetricType.CONSECUTIVE.value:
        exito = reglas.evaluar_condiciones(dict(regla.get("success_when") or {}), hechos)
        reinicio = dict(regla.get("reset_when") or {})
        if exito:
            progreso.current_consecutive = int(progreso.current_consecutive) + 1
            progreso.max_consecutive = max(int(progreso.max_consecutive), int(progreso.current_consecutive))
            return True
        if reinicio and reglas.evaluar_condiciones(reinicio, hechos):
            progreso.current_consecutive = 0
            return True
        return False
    return False


def _actualizar_porcentaje(regla: dict[str, Any], logro: Achievement, progreso: UserAchievement) -> None:
    """Recalcula `progress_pct` hacia el próximo nivel no desbloqueado."""
    valor = _valor_actual(regla, progreso)
    desbloqueados = {str(t.get("tier")) for t in list(progreso.unlocked_tiers or [])}
    pendientes = [n for n in list(logro.tiers or []) if str(n.get("tier")) not in desbloqueados]
    if not pendientes:
        progreso.progress_pct = Decimal("100.00")
        return
    objetivo = max(1, int(pendientes[0].get("target", 1)))
    pct = Decimal(min(valor, objetivo) * 100) / Decimal(objetivo)
    progreso.progress_pct = pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def evaluar_por_evento(
    db: Session,
    cfg: ServicioConfig,
    *,
    usuario_id: uuid.UUID,
    event_type: EventType,
    payload: dict[str, Any],
    event_id: uuid.UUID | None = None,
    estado_usuario: reglas.EstadoUsuario | None = None,
    momento: datetime | None = None,
) -> list[ResultadoLogro]:
    """Evalúa todos los logros que escuchan el evento y desbloquea lo que corresponda."""
    instante = momento or utcnow()
    if payload.get("counts_for_progress") is False:
        return []

    hechos = reglas.construir_hechos(payload, estado_usuario)
    resultados: list[ResultadoLogro] = []

    for logro in logros_para_evento(db, event_type):
        regla = dict(logro.rule or {})
        if not reglas.evaluar_condiciones(dict(regla.get("where") or {}), hechos):
            continue
        progreso = _obtener_o_crear_progreso(db, usuario_id, logro)
        if event_id is not None and progreso.last_event_id == event_id:
            continue  # idempotencia: este evento ya se aplicó a este logro

        cambio = _aplicar_metrica(regla, progreso, payload, hechos)
        progreso.last_event_id = event_id

        valor = _valor_actual(regla, progreso)
        ya_desbloqueados = {str(t.get("tier")) for t in list(progreso.unlocked_tiers or [])}
        nuevos: list[NivelDesbloqueado] = []
        registro = [dict(t) for t in list(progreso.unlocked_tiers or [])]

        for nivel in list(logro.tiers or []):
            etiqueta = str(nivel.get("tier", AchievementTier.SINGLE.value))
            if etiqueta in ya_desbloqueados:
                continue
            if valor < int(nivel.get("target", 1)):
                continue
            xp, oro, titulo = recompensa_de_nivel(cfg, nivel)
            registro.append(
                {
                    "tier": etiqueta,
                    "unlocked_at": isoformat_z(instante),
                    "reward_xp": xp,
                    "reward_gold": oro,
                    "title_id": titulo,
                    "reward_granted": True,
                }
            )
            nuevos.append(
                NivelDesbloqueado(
                    achievement=logro,
                    tier=AchievementTier(etiqueta),
                    reward_xp=xp,
                    reward_gold=oro,
                    title_id=titulo,
                )
            )

        if nuevos:
            progreso.unlocked_tiers = registro
            progreso.highest_tier = nuevos[-1].tier
            progreso.last_unlocked_at = instante
            if progreso.first_unlocked_at is None:
                progreso.first_unlocked_at = instante

        _actualizar_porcentaje(regla, logro, progreso)
        db.flush()

        if cambio or nuevos:
            resultados.append(ResultadoLogro(achievement=logro, progreso=progreso, desbloqueados=nuevos))

    return resultados


def progreso_de_usuario(db: Session, usuario_id: uuid.UUID) -> list[tuple[Achievement, UserAchievement | None]]:
    """Catálogo de logros activos con el progreso del usuario (sala de trofeos, §7.9)."""
    filas = db.execute(
        sa.select(Achievement, UserAchievement)
        .outerjoin(
            UserAchievement,
            sa.and_(
                UserAchievement.achievement_id == Achievement.id,
                UserAchievement.user_id == usuario_id,
            ),
        )
        .where(Achievement.is_active.is_(True))
        .order_by(Achievement.sort_order, Achievement.code)
    ).all()
    return [(fila[0], fila[1]) for fila in filas]


__all__ = [
    "CLAVE_RECOMPENSA_TIER",
    "NivelDesbloqueado",
    "ResultadoLogro",
    "evaluar_por_evento",
    "logros_para_evento",
    "progreso_de_usuario",
    "recompensa_de_nivel",
]
