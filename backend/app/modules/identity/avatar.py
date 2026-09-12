"""Avatar: rasgos gratuitos y manifiesto de capas resuelto que consume el cliente.

Reparto de responsabilidades (§1.3 y §7.2):

- Los **rasgos** (`avatar_configs`: piel, rostro, orejas, cabello, trato) son de
  `identity` y se cambian aquí. No son ítems ni cuestan oro.
- El **equipamiento** (`equipped_items`) lo escribe `economy` por delegación:
  este archivo llama a `app.modules.economy.equipamiento`, que valida propiedad,
  ranura y compatibilidad, y emite `ITEM_EQUIPPED` / `ITEM_UNEQUIPPED`.
- El **manifiesto de capas** (`layers[]`) lo resuelve y ordena por `z` el
  servidor —aplicando `suppresses_layers` y `two_handed`—: el cliente solo pinta.

Cambiar un rasgo emite `AVATAR_UPDATED` con la lista de campos cambiados (§4.2).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.enums import EventType
from app.models.identity import AvatarConfig, User
from app.modules.economy import equipamiento
from app.modules.identity import personaje as servicio_personaje
from app.modules.identity import servicio_usuario

#: Campos de `avatar_configs` que el usuario puede cambiar desde la API.
CAMPOS_RASGOS: tuple[str, ...] = (
    "body_type",
    "skin_tone",
    "face_id",
    "ear_style",
    "hair_style_id",
    "hair_color",
    "address_form",
    "accent_color",
)


def obtener_o_crear_rasgos(db: Session, personaje_id: uuid.UUID) -> AvatarConfig:
    """Fila de `avatar_configs` del personaje, creada con los valores por defecto."""
    rasgos = servicio_personaje.rasgos_de(db, personaje_id)
    if rasgos is None:
        rasgos = AvatarConfig(character_id=personaje_id)
        db.add(rasgos)
        db.flush()
        db.refresh(rasgos)
    return rasgos


def vista_avatar(db: Session, usuario_id: uuid.UUID) -> dict[str, Any]:
    """Rasgos, arquetipo, equipo, capas ordenadas por `z` y `etag` (`GET /avatar`).

    Lo resuelve `economy`, que es quien conoce `items.render_manifest`; si el
    personaje aún no tiene rasgos se crean antes para que `traits` nunca vaya
    vacío.
    """
    personaje = servicio_personaje.obtener_personaje(db, usuario_id)
    obtener_o_crear_rasgos(db, personaje.id)
    return equipamiento.configuracion_avatar(db, usuario_id)


def actualizar_rasgos(
    db: Session,
    usuario: User,
    cambios: dict[str, Any],
    *,
    momento: dt.datetime | None = None,
) -> dict[str, Any]:
    """Cambia piel, rostro, orejas, cabello, color y trato (`PUT /avatar/traits`).

    `cambios` es el `model_dump(exclude_unset=True)` de `AvatarTraitsIn`: solo se
    aplica lo que el cliente envió. Emite `AVATAR_UPDATED` con `changed`.
    """
    instante = momento or utcnow()
    personaje = servicio_personaje.obtener_personaje(db, usuario.id)
    rasgos = obtener_o_crear_rasgos(db, personaje.id)

    cambiados: list[str] = []
    for campo in CAMPOS_RASGOS:
        if campo not in cambios:
            continue
        valor = cambios[campo]
        if valor is None and campo != "accent_color":
            continue
        if getattr(rasgos, campo) != valor:
            setattr(rasgos, campo, valor)
            cambiados.append(campo)
    db.flush()

    if cambiados:
        servicio_usuario.emitir_evento(
            db,
            usuario=usuario,
            tipo=EventType.AVATAR_UPDATED,
            payload={"changed": cambiados},
            sufijo=instante.isoformat(),
            momento=instante,
        )
        db.flush()

    return equipamiento.configuracion_avatar(db, usuario.id)


def actualizar_equipamiento(
    db: Session,
    usuario: User,
    mapa: dict[str, uuid.UUID | None],
    *,
    momento: dt.datetime | None = None,
) -> dict[str, Any]:
    """Aplica el mapa atómico de `PUT /avatar/equipment` delegando en `economy`.

    O se aplica entero o no se aplica nada: cualquier validación fallida (ranura
    desconocida, instancia ajena, ranura reservada) aborta la operación completa.
    """
    servicio_personaje.obtener_personaje(db, usuario.id)
    return equipamiento.aplicar_equipamiento(db, usuario.id, mapa, momento=momento)


__all__ = [
    "CAMPOS_RASGOS",
    "actualizar_equipamiento",
    "actualizar_rasgos",
    "obtener_o_crear_rasgos",
    "vista_avatar",
]
