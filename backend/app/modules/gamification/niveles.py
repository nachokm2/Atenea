"""Curvas de nivel global y por conocimiento (CONTRACT.md §6.1).

Fórmulas exactas del contrato::

    xp_required(n, base, exponent=2.2) = round_to_10( base * (n - 1) ** exponent )   para n >= 2
    xp_required(1, ...)                = 0
    level(xp, base) = max{ n en [1, level.max] : xp_required(n, base) <= xp }
    progress_pct(xp, n) = 100 * (xp - xp_required(n)) / (xp_required(n + 1) - xp_required(n))
    xp_to_next(xp, n)   = xp_required(n + 1) - xp

`round_to_10(x)` redondea al múltiplo de 10 más cercano, con el medio hacia arriba.

La tabla `level_definitions` materializa ambas curvas (la siembra A8). Aquí se lee
esa tabla y, si todavía está vacía, se calcula la curva al vuelo desde `game_configs`
con las mismas constantes: el resultado es idéntico por construcción.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.enums import LevelScope
from app.models.gamification import LevelDefinition
from app.modules.gamification.servicio_config import ServicioConfig

#: Claves de `game_configs` de cada curva (§5.2). No son valores de juego: son nombres.
CLAVES_CURVA: dict[LevelScope, dict[str, str]] = {
    LevelScope.GLOBAL: {
        "base": "level.base",
        "exponent": "level.exponent",
        "max": "level.max",
        "round_to": "level.round_to",
        "rank_titles": "level.rank_titles",
    },
    LevelScope.KNOWLEDGE_AREA: {
        "base": "knowledge.level.base",
        "exponent": "knowledge.level.exponent",
        "max": "level.max",
        "round_to": "level.round_to",
        "rank_titles": "knowledge.rank_titles",
    },
}


@dataclass(frozen=True, slots=True)
class ParametrosCurva:
    """Constantes de una curva de nivel, tal como salen de `game_configs`."""

    base: int
    exponente: Decimal
    nivel_max: int
    redondeo: int
    titulos: dict[str, str]


@dataclass(frozen=True, slots=True)
class EstadoNivel:
    """Estado de nivel de un usuario (o de un conocimiento) para un XP acumulado."""

    scope: LevelScope
    xp_total: int
    nivel: int
    xp_nivel_actual: int
    xp_siguiente_nivel: int | None
    xp_to_next: int
    progress_pct: Decimal
    rank_title: str
    is_rank_start: bool


def redondear_a_decena(valor: Decimal | float | int, multiplo: int = 10) -> int:
    """Redondea al múltiplo indicado (10 por defecto) con el medio hacia arriba."""
    if multiplo <= 0:
        return int(valor)
    exacto = Decimal(str(valor)) / Decimal(multiplo)
    return int(exacto.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * multiplo


def parametros_curva(cfg: ServicioConfig, scope: LevelScope = LevelScope.GLOBAL) -> ParametrosCurva:
    """Lee de `game_configs` las constantes de la curva pedida."""
    claves = CLAVES_CURVA[scope]
    return ParametrosCurva(
        base=cfg.obtener_int(claves["base"]),
        exponente=cfg.obtener_decimal(claves["exponent"]),
        nivel_max=cfg.obtener_int(claves["max"]),
        redondeo=cfg.obtener_int(claves["round_to"]),
        titulos=dict(cfg.obtener_json(claves["rank_titles"])),
    )


def xp_requerido_calculado(nivel: int, params: ParametrosCurva) -> int:
    """`xp_required(n)` de §6.1 calculado con las constantes de la curva."""
    if nivel <= 1:
        return 0
    bruto = Decimal(params.base) * (Decimal(nivel - 1) ** params.exponente)
    return redondear_a_decena(bruto, params.redondeo)


def curva_completa(params: ParametrosCurva) -> list[tuple[int, int, int]]:
    """Curva `[(nivel, xp_required, xp_delta)]` desde el nivel 1 hasta `level.max`."""
    filas: list[tuple[int, int, int]] = []
    anterior = 0
    for nivel in range(1, params.nivel_max + 1):
        requerido = xp_requerido_calculado(nivel, params)
        filas.append((nivel, requerido, requerido - anterior))
        anterior = requerido
    return filas


def titulo_de_rango(nivel: int, params: ParametrosCurva) -> str:
    """Título del rango vigente: el mayor `k` de `rank_titles` con `k <= nivel` (§6.1)."""
    candidatos = [int(k) for k in params.titulos if int(k) <= nivel]
    if not candidatos:
        return ""
    return str(params.titulos[str(max(candidatos))])


def es_inicio_de_rango(nivel: int, params: ParametrosCurva) -> bool:
    """`true` en los niveles que estrenan rango (1, 5, 10, 15, …)."""
    return str(nivel) in params.titulos


def titulo_de_conocimiento(nivel: int, mastery: Decimal | float | int, cfg: ServicioConfig) -> str:
    """Título del conocimiento: "Maestro/a de" exige dominio suficiente (§6.1).

    Si el título vigente es el de maestría y el dominio no llega a
    `knowledge.master_title_requires_mastery`, se devuelve
    `knowledge.master_title_fallback`.
    """
    params = parametros_curva(cfg, LevelScope.KNOWLEDGE_AREA)
    titulo = titulo_de_rango(nivel, params)
    if not titulo:
        return titulo
    niveles_titulo = sorted(int(k) for k in params.titulos)
    nivel_maestro = niveles_titulo[-1] if niveles_titulo else None
    if nivel_maestro is not None and titulo == str(params.titulos[str(nivel_maestro)]):
        minimo = Decimal(cfg.obtener_int("knowledge.master_title_requires_mastery"))
        if Decimal(str(mastery)) < minimo:
            return cfg.obtener_str("knowledge.master_title_fallback")
    return titulo


# ---------------------------------------------------------------------------
# Lectura de `level_definitions` (con respaldo calculado)
# ---------------------------------------------------------------------------


def _definiciones(db: Session, scope: LevelScope) -> list[LevelDefinition]:
    """Filas de `level_definitions` de la curva pedida, ordenadas por nivel."""
    return list(
        db.execute(
            sa.select(LevelDefinition)
            .where(LevelDefinition.scope == scope)
            .order_by(LevelDefinition.level)
        )
        .scalars()
        .all()
    )


def tabla_niveles(
    db: Session, cfg: ServicioConfig, scope: LevelScope = LevelScope.GLOBAL
) -> list[tuple[int, int, int]]:
    """Curva `[(nivel, xp_required, xp_delta)]` desde `level_definitions`.

    Si la tabla aún no está sembrada, se calcula con las constantes de §5.2.
    """
    filas = _definiciones(db, scope)
    if filas:
        return [(f.level, int(f.xp_required), int(f.xp_delta)) for f in filas]
    return curva_completa(parametros_curva(cfg, scope))


def xp_para_nivel(
    db: Session, cfg: ServicioConfig, nivel: int, scope: LevelScope = LevelScope.GLOBAL
) -> int:
    """XP acumulado necesario para alcanzar `nivel` en la curva indicada."""
    if nivel <= 1:
        return 0
    for lvl, requerido, _delta in tabla_niveles(db, cfg, scope):
        if lvl == nivel:
            return requerido
    return xp_requerido_calculado(nivel, parametros_curva(cfg, scope))


def nivel_para_xp(
    db: Session, cfg: ServicioConfig, xp: int, scope: LevelScope = LevelScope.GLOBAL
) -> int:
    """Nivel alcanzado con `xp` acumulado: el mayor `n` con `xp_required(n) <= xp`."""
    nivel = 1
    for lvl, requerido, _delta in tabla_niveles(db, cfg, scope):
        if xp >= requerido:
            nivel = max(nivel, lvl)
        else:
            break
    return nivel


def estado_nivel(
    db: Session, cfg: ServicioConfig, xp: int, scope: LevelScope = LevelScope.GLOBAL
) -> EstadoNivel:
    """Estado completo de nivel para un XP acumulado (§6.1 y `RewardsReceipt.level`)."""
    params = parametros_curva(cfg, scope)
    tabla = tabla_niveles(db, cfg, scope)
    xp = max(0, int(xp))
    nivel = nivel_para_xp(db, cfg, xp, scope)
    requerido_actual = next((r for lvl, r, _d in tabla if lvl == nivel), 0)
    siguiente = next((r for lvl, r, _d in tabla if lvl == nivel + 1), None)

    if siguiente is None or siguiente <= requerido_actual:
        progreso = Decimal("100.00")
        faltan = 0
    else:
        bruto = Decimal(xp - requerido_actual) * 100 / Decimal(siguiente - requerido_actual)
        progreso = bruto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        faltan = siguiente - xp

    return EstadoNivel(
        scope=scope,
        xp_total=xp,
        nivel=nivel,
        xp_nivel_actual=requerido_actual,
        xp_siguiente_nivel=siguiente,
        xp_to_next=max(0, faltan),
        progress_pct=progreso,
        rank_title=titulo_de_rango(nivel, params),
        is_rank_start=es_inicio_de_rango(nivel, params),
    )


def desbloqueos_de_nivel(db: Session, nivel: int, scope: LevelScope = LevelScope.GLOBAL) -> dict:
    """`unlocks` declarados en `level_definitions` para un nivel (rarezas de tienda…)."""
    fila = db.execute(
        sa.select(LevelDefinition).where(
            LevelDefinition.scope == scope, LevelDefinition.level == nivel
        )
    ).scalar_one_or_none()
    return dict(fila.unlocks) if fila is not None and fila.unlocks else {}


__all__ = [
    "CLAVES_CURVA",
    "EstadoNivel",
    "ParametrosCurva",
    "curva_completa",
    "desbloqueos_de_nivel",
    "es_inicio_de_rango",
    "estado_nivel",
    "nivel_para_xp",
    "parametros_curva",
    "redondear_a_decena",
    "tabla_niveles",
    "titulo_de_conocimiento",
    "titulo_de_rango",
    "xp_para_nivel",
    "xp_requerido_calculado",
]
