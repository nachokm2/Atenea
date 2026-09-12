"""Módulo `progress`: progreso por usuario, dominio, sesiones de estudio y estadísticas.

Contrato §1.3, §3.4, §6.4–§6.9, §7.4, §7.8.

Este paquete es dueño de la lógica de negocio de:

* `dominio.py` — fórmula exacta de dominio (§6.4–§6.8) y su recálculo por evento.
* `sesiones.py` — `learning_sessions`, latidos de tiempo activo y acumulación de tiempo.
* `progreso.py` — avance por lección, módulo y ruta, y desbloqueo progresivo.
* `panel.py` — agregado del panel principal (P04, §7.8).
* `estadisticas.py` — perfil y estadísticas del usuario.
* `schemas.py` / `router.py` — contrato HTTP de este módulo.

**Los tres medidores viven separados** (§1.1): el tiempo mide dedicación y jamás
alimenta XP ni dominio; el dominio sale solo de `question_attempts` y
`assessment_attempts`; el XP lo paga el ledger del módulo `gamification`.

Aquí vive además el **lector de configuración de juego**: ningún número de balance
se escribe como literal en el código (§5 y §8.10 regla 5); todo sale de la tabla
`game_configs`, que se lee con la caché en memoria de 60 s que fija el contrato.
El lector consulta la **tabla** (dato compartido), no un servicio de otro módulo, de
modo que no se rompe la dirección de dependencias de §1.3.
"""

from __future__ import annotations

import time as _time
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import AteneaError
from app.models.gamification import GameConfig

#: TTL de la caché en memoria de `game_configs` (§5: «con caché en memoria de 60 s»).
#: Es un parámetro de infraestructura, no un valor de balance del juego.
CONFIG_CACHE_TTL_SECONDS = 60


class ConfiguracionAusente(AteneaError):
    """Falta una clave obligatoria de `game_configs` (semillas incompletas).

    Se prefiere fallar de forma explícita antes que inventar un valor por defecto:
    el contrato prohíbe que un número de §5 aparezca como literal en el código.
    """

    code = "INTERNAL_ERROR"

    def __init__(self, key: str) -> None:
        super().__init__(
            f"Falta la clave de configuración de juego «{key}» en game_configs.",
            details={"config_key": key},
        )
        self.key = key


class LectorConfiguracion:
    """Lee los valores vigentes de `game_configs` con caché de proceso.

    El valor vigente de una clave es la fila con
    `valid_from <= now() < coalesce(valid_to, 'infinity')` y mayor `version`
    (definición del modelo `GameConfig`, contrato §3.5).

    Uso::

        cfg = LectorConfiguracion(db)
        media_vida = cfg.decimal("mastery.recency_half_life_days")
    """

    __slots__ = ("_cache", "_db", "_ttl")

    def __init__(self, db: Session, *, ttl_seconds: int = CONFIG_CACHE_TTL_SECONDS) -> None:
        self._db = db
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}

    # -- lectura cruda ----------------------------------------------------

    def raw(self, key: str) -> Any:
        """Valor JSON vigente de la clave; lanza `ConfiguracionAusente` si no existe."""
        cached = self._cache.get(key)
        now = _time.monotonic()
        if cached is not None and cached[0] > now:
            return cached[1]

        stmt = (
            sa.select(GameConfig.value)
            .where(
                GameConfig.key == key,
                GameConfig.valid_from <= sa.func.now(),
                sa.or_(GameConfig.valid_to.is_(None), GameConfig.valid_to > sa.func.now()),
            )
            .order_by(GameConfig.version.desc())
            .limit(1)
        )
        value = self._db.execute(stmt).scalar_one_or_none()
        if value is None:
            raise ConfiguracionAusente(key)

        self._cache[key] = (now + self._ttl, value)
        return value

    def muchas(self, keys: Sequence[str]) -> dict[str, Any]:
        """Lee varias claves en **una sola consulta** (el panel las necesita juntas)."""
        now = _time.monotonic()
        pendientes = [k for k in keys if not (self._cache.get(k) and self._cache[k][0] > now)]
        if pendientes:
            stmt = (
                sa.select(GameConfig.key, GameConfig.value, GameConfig.version)
                .where(
                    GameConfig.key.in_(pendientes),
                    GameConfig.valid_from <= sa.func.now(),
                    sa.or_(GameConfig.valid_to.is_(None), GameConfig.valid_to > sa.func.now()),
                )
                .order_by(GameConfig.key, GameConfig.version.desc())
            )
            vistos: set[str] = set()
            for key, value, _version in self._db.execute(stmt):
                if key in vistos:
                    continue
                vistos.add(key)
                self._cache[key] = (now + self._ttl, value)
        faltan = [k for k in keys if k not in self._cache]
        if faltan:
            raise ConfiguracionAusente(faltan[0])
        return {k: self._cache[k][1] for k in keys}

    # -- lecturas tipadas -------------------------------------------------

    def entero(self, key: str) -> int:
        """Valor entero de la clave."""
        return int(self.raw(key))

    def decimal(self, key: str) -> float:
        """Valor decimal de la clave, como `float` (las fórmulas de §6 son reales)."""
        value = self.raw(key)
        return float(value.strip() if isinstance(value, str) else value)

    def booleano(self, key: str) -> bool:
        """Valor booleano de la clave."""
        return bool(self.raw(key))

    def texto(self, key: str) -> str:
        """Valor de texto de la clave."""
        return str(self.raw(key))

    def mapa(self, key: str) -> Mapping[str, Any]:
        """Valor de tipo mapa de la clave."""
        value = self.raw(key)
        if not isinstance(value, Mapping):
            raise ConfiguracionAusente(key)
        return value

    def lista(self, key: str) -> list[Any]:
        """Valor de tipo lista de la clave."""
        value = self.raw(key)
        if not isinstance(value, list):
            raise ConfiguracionAusente(key)
        return list(value)

    # -- versión de configuración ----------------------------------------

    def config_version(self) -> int:
        """Mayor `config_version` vigente: viaja en el `RewardsReceipt` y en `X-Config-Version`."""
        stmt = sa.select(sa.func.coalesce(sa.func.max(GameConfig.config_version), 0)).where(
            GameConfig.valid_from <= sa.func.now(),
            sa.or_(GameConfig.valid_to.is_(None), GameConfig.valid_to > sa.func.now()),
        )
        return int(self._db.execute(stmt).scalar_one())


def a_float(value: Decimal | float | int | None, por_defecto: float = 0.0) -> float:
    """Convierte un `Numeric(5,2)` de la base (o `None`) en `float`."""
    if value is None:
        return por_defecto
    return float(value)


def a_decimal_2(value: float | int | Decimal) -> Decimal:
    """Redondea a la escala `Numeric(5, 2)` que usan las columnas de dominio."""
    return Decimal(str(round(float(value), 2)))


__all__ = [
    "CONFIG_CACHE_TTL_SECONDS",
    "ConfiguracionAusente",
    "LectorConfiguracion",
    "a_decimal_2",
    "a_float",
]
