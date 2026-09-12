"""Equipar y desequipar cosméticos, y configuración de avatar que consume el cliente.

`equipped_items` pertenece al archivo de modelos de `identity`, pero su escritura está
**delegada en `economy`** por el contrato (§1.3): aquí se valida la propiedad de la
instancia, que la ranura coincida con la del ítem y que la ranura esté activa
(`items.slots_active` de `game_configs`), y se emiten `ITEM_EQUIPPED` / `ITEM_UNEQUIPPED`.

El cliente nunca decide el resultado visual: este módulo devuelve el **manifiesto de
capas ya resuelto y ordenado por z**, aplicando `suppresses_layers` (una capa puede
tapar a otra, p. ej. un casco que oculta el pelo) y `two_handed` (un arma a dos manos
libera la mano secundaria).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.core.time import user_local_date, utcnow
from app.models.economy import Item, UserItem
from app.models.enums import EventType, ItemSlot
from app.models.identity import AvatarConfig, Character, EquippedItem, User
from app.modules.economy.monedero import recortar_clave, registrar_evento, valor_config

#: Clave de configuración con las ranuras activas del avatar (§5.4).
CLAVE_SLOTS_ACTIVOS = "items.slots_active"
CLAVE_SLOTS_RESERVADOS = "items.slots_reserved"


class RanuraInvalida(ValidationFailed):
    """422 · la ranura no existe, está reservada o no corresponde al ítem."""


# ---------------------------------------------------------------------------
# Consultas de apoyo
# ---------------------------------------------------------------------------


def slots_activos(db: Session) -> tuple[ItemSlot, ...]:
    """Ranuras equipables según `game_configs` (nunca una lista escrita en el código)."""
    crudo = valor_config(db, CLAVE_SLOTS_ACTIVOS)
    valores: list[ItemSlot] = []
    for nombre in crudo or []:
        try:
            valores.append(ItemSlot(str(nombre)))
        except ValueError:  # pragma: no cover - configuración mal sembrada
            continue
    return tuple(valores)


def personaje_de(db: Session, usuario_id: uuid.UUID) -> Character:
    """Personaje del usuario; sin personaje no hay avatar que equipar."""
    personaje = db.execute(
        sa.select(Character).where(Character.user_id == usuario_id)
    ).scalar_one_or_none()
    if personaje is None:
        raise NotFound(
            "Todavía no creaste tu personaje.", details={"user_id": str(usuario_id)}
        )
    return personaje


def _usuario(db: Session, usuario_id: uuid.UUID) -> User:
    """Usuario dueño del personaje (para el sobre del evento)."""
    usuario = db.get(User, usuario_id)
    if usuario is None:
        raise NotFound(details={"user_id": str(usuario_id)})
    return usuario


def _instancia_propia(db: Session, usuario_id: uuid.UUID, user_item_id: uuid.UUID) -> UserItem:
    """Instancia del inventario del usuario, vigente y no revocada."""
    user_item = db.execute(
        sa.select(UserItem).where(
            UserItem.id == user_item_id, UserItem.user_id == usuario_id
        )
    ).scalar_one_or_none()
    if user_item is None or user_item.revoked_at is not None:
        raise NotFound(details={"user_item_id": str(user_item_id)})
    return user_item


def equipados(db: Session, personaje_id: uuid.UUID) -> dict[ItemSlot, EquippedItem]:
    """Mapa `ranura -> fila de equipamiento` del personaje."""
    filas = db.execute(
        sa.select(EquippedItem).where(EquippedItem.character_id == personaje_id)
    ).scalars()
    return {fila.slot: fila for fila in filas}


# ---------------------------------------------------------------------------
# Equipar / desequipar
# ---------------------------------------------------------------------------


@dataclass
class CambioEquipamiento:
    """Resultado de equipar o desequipar: qué entró, qué salió y en qué ranura."""

    slot: ItemSlot
    user_item_id: uuid.UUID | None
    replaced_user_item_id: uuid.UUID | None
    slots_filled: int
    slots_total: int


def _validar_ranura(db: Session, item: Item, slot: ItemSlot | None) -> ItemSlot:
    """Comprueba que la ranura pedida es la del ítem y que está activa."""
    activos = slots_activos(db)
    destino = slot or item.slot

    if destino not in activos:
        raise RanuraInvalida(
            "Esa ranura todavía no está disponible.",
            field_errors=[
                {"field": "slot", "message": f"Ranuras activas: {', '.join(s.value for s in activos)}."}
            ],
            details={"slot": destino.value},
        )
    if destino is not item.slot:
        raise RanuraInvalida(
            "Ese objeto no va en esa ranura.",
            field_errors=[
                {"field": "slot", "message": f"«{item.name}» se equipa en «{item.slot.value}»."}
            ],
            details={"slot": destino.value, "item_slot": item.slot.value},
        )
    if item.is_template:
        raise RanuraInvalida(
            "Ese objeto no se puede equipar.",
            details={"item_code": item.code},
        )
    return destino


def equipar(
    db: Session,
    usuario_id: uuid.UUID,
    user_item_id: uuid.UUID,
    *,
    slot: ItemSlot | None = None,
    momento: dt.datetime | None = None,
) -> CambioEquipamiento:
    """Equipa una instancia poseída en su ranura, reemplazando lo que hubiera.

    Valida propiedad (404 si no es del usuario), que la ranura sea la del ítem y que
    esté activa (422 `VALIDATION_ERROR`). Emite `ITEM_EQUIPPED`.
    """
    instante = momento or utcnow()
    personaje = personaje_de(db, usuario_id)
    user_item = _instancia_propia(db, usuario_id, user_item_id)
    item = db.get(Item, user_item.item_id)
    if item is None:  # pragma: no cover - la FK es RESTRICT
        raise NotFound(details={"item_id": str(user_item.item_id)})

    destino = _validar_ranura(db, item, slot)

    ocupadas = equipados(db, personaje.id)
    anterior = ocupadas.get(destino)
    reemplazado: uuid.UUID | None = None

    if anterior is not None:
        if anterior.user_item_id == user_item.id:
            # Ya estaba equipado: la operación es idempotente.
            return CambioEquipamiento(
                slot=destino,
                user_item_id=user_item.id,
                replaced_user_item_id=None,
                slots_filled=len(ocupadas),
                slots_total=len(slots_activos(db)),
            )
        reemplazado = anterior.user_item_id
        db.delete(anterior)
        db.flush()

    db.add(
        EquippedItem(
            character_id=personaje.id,
            slot=destino,
            user_item_id=user_item.id,
            equipped_at=instante,
        )
    )
    db.flush()

    ocupadas = equipados(db, personaje.id)
    activos = slots_activos(db)
    usuario = _usuario(db, usuario_id)
    registrar_evento(
        db,
        event_type=EventType.ITEM_EQUIPPED,
        usuario=usuario,
        payload={
            "slot": destino.value,
            "user_item_id": str(user_item.id),
            "item_code": item.code,
            "replaced_user_item_id": str(reemplazado) if reemplazado else None,
            "slots_filled": len(ocupadas),
            "slots_total": len(activos),
        },
        clave=recortar_clave(
            f"item-equipped:{usuario_id}:{user_item.id}:{instante.isoformat()}"
        ),
        local_date=user_local_date(instante, usuario.timezone),
        momento=instante,
    )
    db.flush()

    return CambioEquipamiento(
        slot=destino,
        user_item_id=user_item.id,
        replaced_user_item_id=reemplazado,
        slots_filled=len(ocupadas),
        slots_total=len(activos),
    )


def desequipar(
    db: Session,
    usuario_id: uuid.UUID,
    slot: ItemSlot,
    *,
    momento: dt.datetime | None = None,
) -> CambioEquipamiento:
    """Deja libre una ranura. Si ya estaba vacía no hace nada (idempotente)."""
    instante = momento or utcnow()
    personaje = personaje_de(db, usuario_id)
    ocupadas = equipados(db, personaje.id)
    fila = ocupadas.get(slot)
    activos = slots_activos(db)

    if fila is None:
        return CambioEquipamiento(
            slot=slot,
            user_item_id=None,
            replaced_user_item_id=None,
            slots_filled=len(ocupadas),
            slots_total=len(activos),
        )

    quitado = fila.user_item_id
    db.delete(fila)
    db.flush()

    usuario = _usuario(db, usuario_id)
    registrar_evento(
        db,
        event_type=EventType.ITEM_UNEQUIPPED,
        usuario=usuario,
        payload={"slot": slot.value, "user_item_id": str(quitado)},
        clave=recortar_clave(
            f"item-unequipped:{usuario_id}:{quitado}:{instante.isoformat()}"
        ),
        local_date=user_local_date(instante, usuario.timezone),
        momento=instante,
    )
    db.flush()

    return CambioEquipamiento(
        slot=slot,
        user_item_id=None,
        replaced_user_item_id=quitado,
        slots_filled=len(equipados(db, personaje.id)),
        slots_total=len(activos),
    )


def aplicar_equipamiento(
    db: Session,
    usuario_id: uuid.UUID,
    mapa: dict[str, uuid.UUID | None],
    *,
    momento: dt.datetime | None = None,
) -> dict[str, Any]:
    """Aplica de forma atómica un mapa `{"weapon": "<user_item_id>", "cape": null}`.

    Es lo que consume `PUT /api/v1/avatar/equipment`: o se aplica entero o no se aplica
    nada (cualquier validación fallida aborta la operación completa).
    """
    instante = momento or utcnow()
    personaje_de(db, usuario_id)  # 404 temprano si no hay personaje

    for nombre, user_item_id in mapa.items():
        try:
            slot = ItemSlot(str(nombre))
        except ValueError as exc:
            raise RanuraInvalida(
                "Esa ranura no existe.",
                field_errors=[{"field": "equipment", "message": f"Ranura desconocida: {nombre}."}],
            ) from exc
        if user_item_id is None:
            desequipar(db, usuario_id, slot, momento=instante)
        else:
            identificador = (
                user_item_id if isinstance(user_item_id, uuid.UUID) else uuid.UUID(str(user_item_id))
            )
            equipar(db, usuario_id, identificador, slot=slot, momento=instante)

    return configuracion_avatar(db, usuario_id)


# ---------------------------------------------------------------------------
# Configuración de avatar
# ---------------------------------------------------------------------------


def _capas_de(item: Item, slot: ItemSlot) -> list[dict[str, Any]]:
    """Normaliza `items.render_manifest` a una lista de capas con `z`."""
    manifiesto = dict(item.render_manifest or {})
    capas = manifiesto.get("layers")
    if not capas:
        clave = manifiesto.get("icon") or item.icon_key or item.code
        capas = [{"key": clave, "z": manifiesto.get("z", 0)}]
    normalizadas: list[dict[str, Any]] = []
    for capa in capas:
        if not isinstance(capa, dict):
            continue
        normalizadas.append(
            {
                "slot": slot.value,
                "item_code": item.code,
                "key": capa.get("key") or item.icon_key or item.code,
                "z": int(capa.get("z", 0)),
                "offset": capa.get("offset"),
                "tint": capa.get("tint") or manifiesto.get("tint"),
            }
        )
    return normalizadas


def configuracion_avatar(db: Session, usuario_id: uuid.UUID) -> dict[str, Any]:
    """Rasgos, arquetipo, equipo y manifiesto de capas resuelto y ordenado por z.

    Aplica `suppresses_layers` (capas que otro ítem tapa) y `two_handed` (un arma a dos
    manos vacía la ranura secundaria en la representación, sin desequiparla).
    """
    personaje = personaje_de(db, usuario_id)
    rasgos = db.execute(
        sa.select(AvatarConfig).where(AvatarConfig.character_id == personaje.id)
    ).scalar_one_or_none()

    filas = db.execute(
        sa.select(EquippedItem, UserItem, Item)
        .join(UserItem, UserItem.id == EquippedItem.user_item_id)
        .join(Item, Item.id == UserItem.item_id)
        .where(EquippedItem.character_id == personaje.id)
    ).all()

    equipo: dict[str, Any] = {}
    capas: list[dict[str, Any]] = []
    suprimidas: set[str] = set()
    dos_manos = False

    for equipado, user_item, item in filas:
        manifiesto = dict(item.render_manifest or {})
        equipo[equipado.slot.value] = {
            "user_item_id": str(user_item.id),
            "item_id": str(item.id),
            "item_code": item.code,
            "name": item.name,
            "rarity": item.rarity.value,
            "icon_key": item.icon_key,
        }
        suprimidas.update(str(c) for c in manifiesto.get("suppresses_layers", []) or [])
        if manifiesto.get("two_handed"):
            dos_manos = True
        capas.extend(_capas_de(item, equipado.slot))

    if dos_manos:
        capas = [capa for capa in capas if capa["slot"] != ItemSlot.OFFHAND.value]
    capas = [capa for capa in capas if capa["key"] not in suprimidas]
    capas.sort(key=lambda capa: (capa["z"], capa["slot"]))

    traits: dict[str, Any] = {}
    if rasgos is not None:
        traits = {
            "body_type": rasgos.body_type.value,
            "skin_tone": rasgos.skin_tone,
            "face_id": rasgos.face_id,
            "ear_style": rasgos.ear_style,
            "hair_style_id": rasgos.hair_style_id,
            "hair_color": rasgos.hair_color,
            "address_form": rasgos.address_form.value,
            "accent_color": rasgos.accent_color,
            "asset_version": rasgos.asset_version,
        }

    huella = json.dumps({"traits": traits, "equipment": equipo}, sort_keys=True)
    etag = hashlib.sha256(huella.encode("utf-8")).hexdigest()[:32]

    return {
        "traits": traits,
        "archetype": personaje.archetype.value,
        "equipment": equipo,
        "layers": capas,
        "etag": etag,
    }


__all__ = [
    "CLAVE_SLOTS_ACTIVOS",
    "CLAVE_SLOTS_RESERVADOS",
    "CambioEquipamiento",
    "RanuraInvalida",
    "aplicar_equipamiento",
    "configuracion_avatar",
    "desequipar",
    "equipados",
    "equipar",
    "personaje_de",
    "slots_activos",
]
