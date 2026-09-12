"""Personaje: creación (P03), renombrado, cambio de Orden y lectura de nivel.

Puntos vinculantes del contrato:

- §7.2 · `POST /characters` crea el personaje, otorga la **bolsa de bienvenida**
  y el **kit inicial**, y devuelve el `RewardsReceipt` en `rewards`.
- §4.2 · La entrega la dispara el evento `CHARACTER_CREATED`, que se registra con
  `eventos.registrar_evento`: los importes salen de `reward_rules` +
  `game_configs` (`gold.welcome`) y los ítems del evaluador de desbloqueos de
  `economy`. Aquí no se escribe ni una moneda a mano.
- §8.3 · La ruta exige `Idempotency-Key`: reintentar con la misma clave devuelve
  el **mismo** recibo y no vuelve a otorgar nada.
- `characters.level`, `xp_total` y `rank_title` son **cachés**: la fuente de
  verdad es el ledger `xp_transactions` y la curva de niveles de §6.1, así que
  se leen siempre del motor de gamificación y luego se sincroniza la fila.
- El arquetipo es **libre**: ninguna Orden está restringida por género ni por la
  forma de tratamiento (`address_form`) elegida.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.core.time import user_local_date, utcnow
from app.models.enums import CharacterArchetype, EventType, LevelScope
from app.models.identity import AvatarConfig, Character, User
from app.modules.economy import monedero
from app.modules.gamification import eventos as bus
from app.modules.gamification import niveles, rachas
from app.modules.gamification import xp as motor_xp
from app.modules.gamification.recompensas import ReciboRecompensas
from app.modules.gamification.servicio_config import ConfiguracionAusenteError, ServicioConfig

#: Prefijo de la clave de idempotencia del evento de creación (§8.3).
PREFIJO_CLAVE = "character-created"


def clave_de_creacion(usuario_id: uuid.UUID, idempotency_key: str) -> str:
    """Clave determinista del evento `CHARACTER_CREATED` (única global, 120 chars)."""
    return f"{PREFIJO_CLAVE}:{usuario_id}:{idempotency_key}"[:120]


# ---------------------------------------------------------------------------
# Lecturas
# ---------------------------------------------------------------------------


def buscar_personaje(db: Session, usuario_id: uuid.UUID) -> Character | None:
    """Personaje del usuario, o `None` si todavía no lo creó."""
    return db.execute(
        sa.select(Character).where(Character.user_id == usuario_id)
    ).scalar_one_or_none()


def obtener_personaje(db: Session, usuario_id: uuid.UUID) -> Character:
    """Personaje del usuario; `404 NOT_FOUND` si aún no hay personaje."""
    personaje = buscar_personaje(db, usuario_id)
    if personaje is None:
        raise NotFound("Todavía no creaste tu personaje.")
    return personaje


def rasgos_de(db: Session, personaje_id: uuid.UUID) -> AvatarConfig | None:
    """Fila de `avatar_configs` del personaje, si existe."""
    return db.execute(
        sa.select(AvatarConfig).where(AvatarConfig.character_id == personaje_id)
    ).scalar_one_or_none()


def _estado_nivel(db: Session, cfg: ServicioConfig, xp: int) -> niveles.EstadoNivel | None:
    """Estado de nivel global para un XP acumulado, o `None` si falta la curva.

    La curva vive en `game_configs` (`level.*`). Si todavía no está sembrada no
    se inventa ningún número: se devuelve `None` y el llamador usa la caché de
    la fila `characters`.
    """
    try:
        return niveles.estado_nivel(db, cfg, xp, scope=LevelScope.GLOBAL)
    except ConfiguracionAusenteError:  # pragma: no cover - solo sin semillas
        return None


def sincronizar_cache(
    db: Session, personaje: Character, *, cfg: ServicioConfig | None = None
) -> niveles.EstadoNivel | None:
    """Recalcula `level`, `xp_total` y `rank_title` desde el ledger y la curva."""
    configuracion = cfg or ServicioConfig(db)
    xp = motor_xp.xp_total(db, personaje.user_id)
    estado = _estado_nivel(db, configuracion, xp)
    personaje.xp_total = xp
    if estado is not None:
        personaje.level = estado.nivel
        personaje.rank_title = estado.rank_title
    db.flush()
    return estado


def vista_personaje(
    db: Session,
    personaje: Character,
    *,
    cfg: ServicioConfig | None = None,
    rewards: ReciboRecompensas | None = None,
) -> dict[str, Any]:
    """Personaje en la forma de `CharacterOut`, con nivel y rango del motor."""
    configuracion = cfg or ServicioConfig(db)
    estado = sincronizar_cache(db, personaje, cfg=configuracion)
    rasgos = rasgos_de(db, personaje.id)
    return {
        "id": personaje.id,
        "user_id": personaje.user_id,
        "name": personaje.name,
        "archetype": personaje.archetype,
        "level": personaje.level,
        "xp_total": personaje.xp_total,
        "rank_title": personaje.rank_title,
        "xp_to_next": 0 if estado is None else estado.xp_to_next,
        "progress_pct": 0.0 if estado is None else float(estado.progress_pct),
        "total_study_seconds": personaje.total_study_seconds,
        "onboarded_at": personaje.onboarded_at,
        "created_at": personaje.created_at,
        "traits": rasgos,
        "rewards": rewards,
    }


# ---------------------------------------------------------------------------
# Creación (P03)
# ---------------------------------------------------------------------------


def _crear_rasgos(db: Session, personaje: Character, traits: dict[str, Any] | None) -> AvatarConfig:
    """Crea `avatar_configs` con los rasgos elegidos (o los valores por defecto)."""
    fila = AvatarConfig(character_id=personaje.id)
    for campo, valor in (traits or {}).items():
        if valor is not None and hasattr(fila, campo):
            setattr(fila, campo, valor)
    db.add(fila)
    db.flush()
    db.refresh(fila)
    return fila


def _inicializar_estado_de_juego(
    db: Session, cfg: ServicioConfig, usuario: User, momento: dt.datetime
) -> None:
    """Crea monedero, racha y objetivo diario con los servicios de sus dueños.

    `economy` es el único que escribe `wallets`; `gamification`, el único que
    escribe `streaks` y `daily_goals` (§1.3). Aquí solo se les pide que existan.
    """
    monedero.obtener_billetera(db, usuario.id, crear=True)
    rachas.obtener_o_crear_racha(db, usuario.id)
    rachas.obtener_o_crear_objetivo(db, cfg, usuario.id, user_local_date(momento, usuario.timezone))
    db.flush()


def crear_personaje(
    db: Session,
    usuario: User,
    *,
    name: str,
    archetype: CharacterArchetype,
    traits: dict[str, Any] | None = None,
    idempotency_key: str,
    momento: dt.datetime | None = None,
) -> tuple[Character, ReciboRecompensas]:
    """Crea el personaje del usuario y devuelve `(personaje, recibo)` (P03).

    Un reintento con la **misma** `Idempotency-Key` devuelve el personaje que ya
    existe y el recibo reconstruido del evento original (§7.10 regla 4). Con una
    clave distinta y personaje ya creado → `409 CHARACTER_ALREADY_EXISTS`.
    """
    instante = momento or utcnow()
    cfg = ServicioConfig(db)
    clave = clave_de_creacion(usuario.id, idempotency_key)

    existente = buscar_personaje(db, usuario.id)
    if existente is not None:
        evento = bus.buscar_por_clave(db, clave)
        if evento is not None:
            return existente, bus.reconstruir_recibo(db, evento, cfg)
        raise Conflict("Ya creaste tu personaje.", code="CHARACTER_ALREADY_EXISTS")

    personaje = Character(user_id=usuario.id, name=name, archetype=archetype)
    db.add(personaje)
    db.flush()
    _crear_rasgos(db, personaje, traits)

    # Monedero, racha y objetivo diario deben existir antes de otorgar nada.
    _inicializar_estado_de_juego(db, cfg, usuario, instante)

    # La bolsa de bienvenida y el kit inicial los entrega el motor a partir del
    # evento: importes de `game_configs`, ítems del evaluador de `economy`.
    recibo = bus.registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=EventType.CHARACTER_CREATED,
        payload={
            "character_id": str(personaje.id),
            "archetype": archetype.value,
            "name": personaje.name,
        },
        idempotency_key=clave,
        occurred_at=instante,
        source_module="identity",
        timezone=usuario.timezone,
        cfg=cfg,
    )

    personaje.onboarded_at = instante
    sincronizar_cache(db, personaje, cfg=cfg)
    return personaje, recibo


# ---------------------------------------------------------------------------
# Actualización
# ---------------------------------------------------------------------------


def actualizar_personaje(
    db: Session,
    usuario: User,
    *,
    name: str | None = None,
    archetype: CharacterArchetype | None = None,
) -> Character:
    """Renombra el personaje o le cambia la Orden (gratis en el MVP, §7.2).

    TODO(contrato): §4.2 no define un evento para este cambio, así que no se
    emite ninguno; si se añade (`CHARACTER_UPDATED`) hay que emitirlo aquí.
    """
    personaje = obtener_personaje(db, usuario.id)
    if name is not None:
        personaje.name = name
    if archetype is not None:
        personaje.archetype = archetype
    db.flush()
    return personaje


__all__ = [
    "PREFIJO_CLAVE",
    "actualizar_personaje",
    "buscar_personaje",
    "clave_de_creacion",
    "crear_personaje",
    "obtener_personaje",
    "rasgos_de",
    "sincronizar_cache",
    "vista_personaje",
]
