"""Servicio de configuración de juego: lectura cacheada y tipada de `game_configs`.

Contrato §3.5 y §5: **ningún número de juego se escribe en el código**. Todo valor
(XP, oro, hitos de racha, topes anti-abuso, unidades del objetivo diario…) se lee
de la tabla `game_configs` a través de este servicio.

Resolución del valor vigente (§3.5):

    fila con `valid_from <= now() < coalesce(valid_to, 'infinity')` y mayor `version`

La caché es de proceso, con TTL corto (60 s, §3.5) e invalidación explícita. Se
comparte entre sesiones porque `game_configs` es global: quien escriba una clave
nueva debe llamar a `invalidar_cache()`.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import AteneaError
from app.core.time import utcnow
from app.models.gamification import GameConfig

#: TTL de la caché en memoria del backend (CONTRACT.md §3.5).
TTL_CACHE_SEGUNDOS = 60

#: Centinela para distinguir "sin valor por defecto" de "por defecto = None".
_AUSENTE: Any = object()


class ConfiguracionAusenteError(AteneaError):
    """La clave de `game_configs` no existe y no se dio un valor por defecto."""

    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, clave: str) -> None:
        super().__init__(
            "No pudimos cargar la configuración del juego. Inténtalo de nuevo en un momento.",
            details={"missing_config_key": clave},
        )


@dataclass(frozen=True, slots=True)
class ValorConfig:
    """Valor vigente de una clave, con la versión global con la que se resolvió."""

    clave: str
    valor: Any
    value_type: str
    config_version: int
    is_public: bool


@dataclass(slots=True)
class _Entrada:
    """Entrada de la caché: valor resuelto y momento de caducidad (epoch en segundos)."""

    valor: ValorConfig | None
    expira_en: float


_CACHE: dict[str, _Entrada] = {}
_CACHE_VERSION: _Entrada | None = None
_CANDADO = threading.RLock()


def invalidar_cache(clave: str | None = None) -> None:
    """Invalida la caché completa o solo una clave (tras sembrar o cambiar un valor)."""
    global _CACHE_VERSION
    with _CANDADO:
        if clave is None:
            _CACHE.clear()
            _CACHE_VERSION = None
        else:
            _CACHE.pop(clave, None)
            _CACHE_VERSION = None


def _ahora_monotono() -> float:
    """Reloj monótono para el TTL (no se ve afectado por cambios de hora del sistema)."""
    return time.monotonic()


class ServicioConfig:
    """Lectura tipada y cacheada de `game_configs` para una sesión de base de datos.

    Uso::

        cfg = ServicioConfig(db)
        xp_leccion = cfg.obtener_int("xp.lesson_completed")
        hitos = cfg.obtener_lista("streak.milestones")
    """

    __slots__ = ("db", "ttl_segundos")

    def __init__(self, db: Session, *, ttl_segundos: int = TTL_CACHE_SEGUNDOS) -> None:
        self.db = db
        self.ttl_segundos = ttl_segundos

    # -- Lectura cruda ------------------------------------------------------

    def _consultar(self, clave: str) -> ValorConfig | None:
        """Lee de la base la fila vigente de la clave (mayor `version` en ventana)."""
        ahora = utcnow()
        fila = self.db.execute(
            sa.select(GameConfig)
            .where(
                GameConfig.key == clave,
                GameConfig.valid_from <= ahora,
                sa.or_(GameConfig.valid_to.is_(None), GameConfig.valid_to > ahora),
            )
            .order_by(GameConfig.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        if fila is None:
            return None
        return ValorConfig(
            clave=clave,
            valor=fila.value,
            value_type=fila.value_type,
            config_version=int(fila.config_version),
            is_public=bool(fila.is_public),
        )

    def resolver(self, clave: str) -> ValorConfig | None:
        """Devuelve el valor vigente de la clave (con caché) o `None` si no existe."""
        ahora = _ahora_monotono()
        with _CANDADO:
            entrada = _CACHE.get(clave)
            if entrada is not None and entrada.expira_en > ahora:
                return entrada.valor
        resuelto = self._consultar(clave)
        with _CANDADO:
            _CACHE[clave] = _Entrada(valor=resuelto, expira_en=ahora + self.ttl_segundos)
        return resuelto

    # -- Accesores tipados --------------------------------------------------

    def obtener(self, clave: str, por_defecto: Any = _AUSENTE) -> Any:
        """Valor vigente de la clave. Sin fila y sin `por_defecto` → error interno."""
        resuelto = self.resolver(clave)
        if resuelto is None:
            if por_defecto is _AUSENTE:
                raise ConfiguracionAusenteError(clave)
            return por_defecto
        return resuelto.valor

    def obtener_int(self, clave: str, por_defecto: Any = _AUSENTE) -> int:
        """Valor entero de la clave."""
        valor = self.obtener(clave, por_defecto)
        return int(valor)

    def obtener_decimal(self, clave: str, por_defecto: Any = _AUSENTE) -> Decimal:
        """Valor decimal exacto (se construye desde su representación textual)."""
        valor = self.obtener(clave, por_defecto)
        if isinstance(valor, Decimal):
            return valor
        return Decimal(str(valor))

    def obtener_bool(self, clave: str, por_defecto: Any = _AUSENTE) -> bool:
        """Valor booleano de la clave."""
        valor = self.obtener(clave, por_defecto)
        if isinstance(valor, str):
            return valor.strip().lower() in {"true", "1", "si", "sí"}
        return bool(valor)

    def obtener_str(self, clave: str, por_defecto: Any = _AUSENTE) -> str:
        """Valor de texto de la clave."""
        return str(self.obtener(clave, por_defecto))

    def obtener_lista(self, clave: str, por_defecto: Any = _AUSENTE) -> list[Any]:
        """Valor de lista de la clave (`value_type = list`)."""
        valor = self.obtener(clave, por_defecto)
        if valor is None:
            return []
        if not isinstance(valor, list):
            raise ConfiguracionAusenteError(clave)
        return list(valor)

    def obtener_json(self, clave: str, por_defecto: Any = _AUSENTE) -> dict[str, Any]:
        """Valor de mapa de la clave (`value_type = map`)."""
        valor = self.obtener(clave, por_defecto)
        if valor is None:
            return {}
        if not isinstance(valor, dict):
            raise ConfiguracionAusenteError(clave)
        return dict(valor)

    # Alias de conveniencia: los mapas del contrato se leen igual que un JSON.
    obtener_mapa = obtener_json

    # -- Metadatos ----------------------------------------------------------

    def config_version(self) -> int:
        """Versión global vigente de `game_configs` (se copia a cada ledger).

        Es el mayor `config_version` de las filas vigentes; 0 si la tabla está vacía.
        """
        global _CACHE_VERSION
        ahora_mono = _ahora_monotono()
        with _CANDADO:
            if _CACHE_VERSION is not None and _CACHE_VERSION.expira_en > ahora_mono:
                return int(_CACHE_VERSION.valor or 0)
        ahora = utcnow()
        version = self.db.execute(
            sa.select(sa.func.max(GameConfig.config_version)).where(
                GameConfig.valid_from <= ahora,
                sa.or_(GameConfig.valid_to.is_(None), GameConfig.valid_to > ahora),
            )
        ).scalar()
        version = int(version or 0)
        with _CANDADO:
            _CACHE_VERSION = _Entrada(valor=version, expira_en=ahora_mono + self.ttl_segundos)
        return version

    def publicas(self) -> dict[str, Any]:
        """Claves con `is_public = true` para `GET /api/v1/config/public` (§7.9)."""
        ahora = utcnow()
        filas = (
            self.db.execute(
                sa.select(GameConfig)
                .where(
                    GameConfig.is_public.is_(True),
                    GameConfig.valid_from <= ahora,
                    sa.or_(GameConfig.valid_to.is_(None), GameConfig.valid_to > ahora),
                )
                .order_by(GameConfig.key, GameConfig.version.desc())
            )
            .scalars()
            .all()
        )
        vigentes: dict[str, Any] = {}
        for fila in filas:
            vigentes.setdefault(fila.key, fila.value)
        return vigentes


def obtener_servicio_config(db: Session) -> ServicioConfig:
    """Fábrica del servicio de configuración (uso como dependencia de FastAPI)."""
    return ServicioConfig(db)


__all__ = [
    "TTL_CACHE_SEGUNDOS",
    "ConfiguracionAusenteError",
    "ServicioConfig",
    "ValorConfig",
    "invalidar_cache",
    "obtener_servicio_config",
]
