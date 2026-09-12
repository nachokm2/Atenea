"""Motor de reglas declarativo del MVP (tabla `reward_rules`, CONTRACT.md §3.5).

**Acotado a propósito**: no es un lenguaje genérico. Una regla tiene exactamente

- **disparador**: `event_type`;
- **condiciones**: `condition`, un mapa plano `{campo[_op]: valor}` evaluado contra
  el payload del evento y contra el estado del usuario (prefijo `user.`);
- **acciones**: XP y oro (importe fijo o clave de `game_configs`) e ítem;
- **límites**: `first_time_only`, `respects_daily_cap`, `respects_repeat_multiplier`;
- **vigencia**: `is_active`, `valid_from`, `valid_to`;
- **versión**: la de `game_configs` con la que se resolvieron los importes
  (se copia a `xp_transactions.config_version`; `reward_rules` no versiona
  filas: se cierra una con `valid_to` y se abre otra con otro `code`).

Operadores admitidos en las claves de `condition` (sufijos): `_gte`, `_gt`,
`_lte`, `_lt`, `_ne`, `_in`, `_not_in`. Sin sufijo, igualdad estricta.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.enums import EventType, GoldSource, LevelScope, XPSource
from app.models.gamification import RewardRule, Streak, XPTransaction
from app.modules.gamification import niveles
from app.modules.gamification.servicio_config import ServicioConfig

#: Sufijos de operador reconocidos, del más largo al más corto (el orden importa).
SUFIJOS_OPERADOR: tuple[str, ...] = ("_not_in", "_gte", "_lte", "_gt", "_lt", "_ne", "_in")

#: Prefijo que indica que el hecho se busca en el estado del usuario, no en el payload.
PREFIJO_USUARIO = "user."


@dataclass(frozen=True, slots=True)
class EstadoUsuario:
    """Estado del usuario visible para las condiciones de una regla.

    Es deliberadamente pequeño: solo lo que el MVP necesita para decidir una
    recompensa. Todo lo demás se toma del payload del evento.
    """

    user_id: uuid.UUID
    xp_total: int = 0
    level: int = 1
    streak_current: int = 0
    streak_best: int = 0
    total_active_days: int = 0

    def como_hechos(self) -> dict[str, Any]:
        """Proyecta el estado como hechos con el prefijo `user.`."""
        return {
            f"{PREFIJO_USUARIO}xp_total": self.xp_total,
            f"{PREFIJO_USUARIO}level": self.level,
            f"{PREFIJO_USUARIO}streak_current": self.streak_current,
            f"{PREFIJO_USUARIO}streak_best": self.streak_best,
            f"{PREFIJO_USUARIO}total_active_days": self.total_active_days,
        }


@dataclass(frozen=True, slots=True)
class LimitesRegla:
    """Límites anti-abuso declarados por la regla (§6.9)."""

    first_time_only: bool = True
    respects_daily_cap: bool = True
    respects_repeat_multiplier: bool = True


@dataclass(slots=True)
class Regla:
    """Regla declarativa evento → recompensa, ya resuelta contra `game_configs`."""

    code: str
    event_type: EventType
    condition: dict[str, Any] = field(default_factory=dict)
    xp_amount: int = 0
    xp_source: XPSource | None = None
    is_educational: bool = True
    gold_amount: int = 0
    gold_source: GoldSource | None = None
    item_id: uuid.UUID | None = None
    limites: LimitesRegla = field(default_factory=LimitesRegla)
    priority: int = 100
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    version: int = 0

    def vigente(self, momento: datetime | None = None) -> bool:
        """Indica si la regla está dentro de su ventana de vigencia."""
        ahora = momento or utcnow()
        if self.valid_from is not None and self.valid_from > ahora:
            return False
        return not (self.valid_to is not None and self.valid_to <= ahora)


# ---------------------------------------------------------------------------
# Evaluador de condiciones
# ---------------------------------------------------------------------------


def _descomponer(clave: str) -> tuple[str, str]:
    """Separa `campo_gte` en `("campo", "gte")`; sin sufijo devuelve `("campo", "eq")`."""
    for sufijo in SUFIJOS_OPERADOR:
        if clave.endswith(sufijo) and len(clave) > len(sufijo):
            return clave[: -len(sufijo)], sufijo[1:]
    return clave, "eq"


def _comparable(valor: Any) -> Any:
    """Normaliza números para comparar sin sorpresas de tipo (int/float/Decimal/str)."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int | float):
        return Decimal(str(valor))
    return valor


def comparar(actual: Any, operador: str, esperado: Any) -> bool:
    """Aplica un operador del DSL a un par de valores."""
    if operador == "in":
        return actual in (esperado or [])
    if operador == "not_in":
        return actual not in (esperado or [])

    izq, der = _comparable(actual), _comparable(esperado)
    if operador == "eq":
        return izq == der
    if operador == "ne":
        return izq != der
    if izq is None or der is None:
        return False
    try:
        if operador == "gte":
            return izq >= der
        if operador == "lte":
            return izq <= der
        if operador == "gt":
            return izq > der
        if operador == "lt":
            return izq < der
    except TypeError:
        return False
    return False


def evaluar_condiciones(condicion: dict[str, Any] | None, hechos: dict[str, Any]) -> bool:
    """Evalúa el mapa de condiciones contra los hechos (conjunción de todas)."""
    if not condicion:
        return True
    for clave, esperado in condicion.items():
        campo, operador = _descomponer(str(clave))
        if campo not in hechos:
            return False
        if not comparar(hechos.get(campo), operador, esperado):
            return False
    return True


def construir_hechos(payload: dict[str, Any], estado: EstadoUsuario | None = None) -> dict[str, Any]:
    """Mezcla el payload del evento con el estado del usuario (prefijo `user.`)."""
    hechos: dict[str, Any] = dict(payload or {})
    if estado is not None:
        hechos.update(estado.como_hechos())
    return hechos


# ---------------------------------------------------------------------------
# Carga desde `reward_rules`
# ---------------------------------------------------------------------------


def _importe(cfg: ServicioConfig, clave_config: str | None, importe: int) -> int:
    """La clave de `game_configs` manda sobre el importe literal de la fila (§3.5)."""
    if clave_config:
        return cfg.obtener_int(clave_config, importe)
    return int(importe or 0)


def cargar_reglas(
    db: Session,
    cfg: ServicioConfig,
    event_type: EventType,
    *,
    momento: datetime | None = None,
) -> list[Regla]:
    """Carga las reglas activas y vigentes de un evento, ordenadas por prioridad."""
    ahora = momento or utcnow()
    filas = (
        db.execute(
            sa.select(RewardRule)
            .where(
                RewardRule.event_type == event_type,
                RewardRule.is_active.is_(True),
                RewardRule.valid_from <= ahora,
                sa.or_(RewardRule.valid_to.is_(None), RewardRule.valid_to > ahora),
            )
            .order_by(RewardRule.priority, RewardRule.code)
        )
        .scalars()
        .all()
    )
    version = cfg.config_version()
    return [
        Regla(
            code=fila.code,
            event_type=fila.event_type,
            condition=dict(fila.condition or {}),
            xp_amount=_importe(cfg, fila.xp_config_key, fila.xp_amount),
            xp_source=fila.xp_source,
            is_educational=bool(fila.is_educational),
            gold_amount=_importe(cfg, fila.gold_config_key, fila.gold_amount),
            gold_source=fila.gold_source,
            item_id=fila.item_id,
            limites=LimitesRegla(
                first_time_only=bool(fila.first_time_only),
                respects_daily_cap=bool(fila.respects_daily_cap),
                respects_repeat_multiplier=bool(fila.respects_repeat_multiplier),
            ),
            priority=int(fila.priority),
            valid_from=fila.valid_from,
            valid_to=fila.valid_to,
            version=version,
        )
        for fila in filas
    ]


def reglas_aplicables(
    db: Session,
    cfg: ServicioConfig,
    event_type: EventType,
    payload: dict[str, Any],
    estado: EstadoUsuario | None = None,
    *,
    momento: datetime | None = None,
) -> list[Regla]:
    """Reglas del evento cuyas condiciones se cumplen, en orden de prioridad."""
    hechos = construir_hechos(payload, estado)
    return [
        regla
        for regla in cargar_reglas(db, cfg, event_type, momento=momento)
        if regla.vigente(momento) and evaluar_condiciones(regla.condition, hechos)
    ]


# ---------------------------------------------------------------------------
# Estado del usuario
# ---------------------------------------------------------------------------


def cargar_estado_usuario(db: Session, cfg: ServicioConfig, usuario_id: uuid.UUID) -> EstadoUsuario:
    """Lee el estado del usuario que las condiciones pueden consultar.

    El XP total sale del ledger `xp_transactions` (fuente de verdad, §1.1) y el
    nivel se deriva con la curva de §6.1; la racha, de `streaks`.
    """
    xp_total = int(
        db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(XPTransaction.amount), 0)).where(
                XPTransaction.user_id == usuario_id
            )
        ).scalar()
        or 0
    )
    racha = db.execute(sa.select(Streak).where(Streak.user_id == usuario_id)).scalar_one_or_none()
    return EstadoUsuario(
        user_id=usuario_id,
        xp_total=xp_total,
        level=niveles.nivel_para_xp(db, cfg, xp_total, LevelScope.GLOBAL),
        streak_current=int(racha.current_length) if racha else 0,
        streak_best=int(racha.best_length) if racha else 0,
        total_active_days=int(racha.total_active_days) if racha else 0,
    )


__all__ = [
    "PREFIJO_USUARIO",
    "SUFIJOS_OPERADOR",
    "EstadoUsuario",
    "LimitesRegla",
    "Regla",
    "cargar_estado_usuario",
    "cargar_reglas",
    "comparar",
    "construir_hechos",
    "evaluar_condiciones",
    "reglas_aplicables",
]
