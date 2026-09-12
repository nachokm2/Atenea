"""Semilla de `level_definitions`: las dos curvas de nivel del contrato §6.1.

Se materializan **dos** escalas, nunca derivadas una de otra:

- `LevelScope.GLOBAL` (`level.base = 80`): la progresión del personaje, del nivel 1
  al `level.max`.
- `LevelScope.KNOWLEDGE_AREA` (`knowledge.level.base = 50`): el nivel dentro de un
  conocimiento, cuya curva es más barata porque el XP de conocimiento excluye el XP
  de bonificación.

Ningún número se escribe aquí: la base, el exponente, el nivel máximo, el redondeo
y los títulos de rango salen de `game_configs` y la aritmética la hace
`app.modules.gamification.niveles`, que es el mismo código que usa el motor en
producción. Así la tabla materializada y el cálculo al vuelo no pueden divergir.

Valores de control de §6.1 que esta semilla debe reproducir exactamente:

===========  ====  =====  =====  ======  ======  ======  =======  =======  =======
Nivel           2      3      5      10      15      20       30       40       50
XP acumulado   80    370  1.690  10.060  26.580  52.040  131.940  253.180  418.330
===========  ====  =====  =====  ======  ======  ======  =======  =======  =======

Curva por conocimiento: nivel 2 = 50, 5 = 1.060, 10 = 6.280, 20 = 32.530, 30 = 82.460.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import ItemRarity, LevelScope
from app.modules.gamification import niveles as motor_niveles
from app.modules.gamification.servicio_config import ServicioConfig

__all__ = [
    "CONTROL_GLOBAL",
    "CONTROL_KNOWLEDGE",
    "FilaNivel",
    "curva",
    "filas_nivel",
]

#: XP acumulado de control de la curva global (CONTRACT.md §6.1).
CONTROL_GLOBAL: dict[int, int] = {
    2: 80,
    3: 370,
    5: 1_690,
    10: 10_060,
    15: 26_580,
    20: 52_040,
    30: 131_940,
    40: 253_180,
    50: 418_330,
}

#: XP acumulado de control de la curva por conocimiento (CONTRACT.md §6.1).
CONTROL_KNOWLEDGE: dict[int, int] = {
    2: 50,
    5: 1_060,
    10: 6_280,
    20: 32_530,
    30: 82_460,
}


@dataclass(frozen=True, slots=True)
class FilaNivel:
    """Una fila de `level_definitions` lista para insertarse."""

    scope: LevelScope
    level: int
    xp_required: int
    """XP **acumulado** necesario para alcanzar el nivel (no incremental)."""

    xp_delta: int
    """XP entre este nivel y el anterior; alimenta la barra de progreso."""

    rank_title: str
    is_rank_start: bool
    """`True` en los niveles que estrenan rango: son los que emiten `RANK_UP`."""

    unlocks: dict[str, Any] = field(default_factory=dict)
    """`{"shop_rarities": [...], "shop": true}`: lo que se abre al llegar aquí."""


def _desbloqueos_globales(cfg: ServicioConfig) -> dict[int, dict[str, Any]]:
    """Mapa `nivel -> desbloqueos` de la curva global, leído de `game_configs`.

    Las rarezas de la tienda aparecen en el nivel mínimo que fija
    `shop.min_level_by_rarity`, y el nivel `shop.unlock_level` abre la tienda.
    """
    por_nivel: dict[int, dict[str, Any]] = {}

    nivel_tienda = cfg.obtener_int("shop.unlock_level")
    por_nivel.setdefault(nivel_tienda, {})["shop"] = True

    minimos = cfg.obtener_json("shop.min_level_by_rarity")
    vendibles = {str(r) for r in cfg.obtener_lista("shop.sellable_rarities")}
    orden = [rareza.value for rareza in ItemRarity]
    for rareza in orden:
        if rareza not in minimos or rareza not in vendibles:
            continue
        nivel = int(minimos[rareza])
        entrada = por_nivel.setdefault(nivel, {})
        entrada.setdefault("shop_rarities", []).append(rareza)
    return por_nivel


def curva(cfg: ServicioConfig, scope: LevelScope) -> list[FilaNivel]:
    """Curva completa de un ámbito, calculada con las fórmulas de §6.1."""
    params = motor_niveles.parametros_curva(cfg, scope)
    desbloqueos = _desbloqueos_globales(cfg) if scope is LevelScope.GLOBAL else {}

    filas: list[FilaNivel] = []
    for nivel, requerido, delta in motor_niveles.curva_completa(params):
        filas.append(
            FilaNivel(
                scope=scope,
                level=nivel,
                xp_required=requerido,
                xp_delta=delta,
                rank_title=motor_niveles.titulo_de_rango(nivel, params),
                is_rank_start=motor_niveles.es_inicio_de_rango(nivel, params),
                unlocks=dict(desbloqueos.get(nivel, {})),
            )
        )
    return filas


def filas_nivel(db: Session, cfg: ServicioConfig | None = None) -> list[FilaNivel]:
    """Las dos curvas completas: primero la global, después la de conocimiento."""
    servicio = cfg or ServicioConfig(db)
    return curva(servicio, LevelScope.GLOBAL) + curva(servicio, LevelScope.KNOWLEDGE_AREA)
