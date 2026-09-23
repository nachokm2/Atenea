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
from app.core.logging import get_logger
from app.core.time import user_local_date, utcnow
from app.models.economy import Item, UserItem
from app.models.enums import EventType, ItemSlot
from app.models.identity import AvatarConfig, Character, EquippedItem, User
from app.modules.economy.monedero import recortar_clave, registrar_evento, valor_config

logger = get_logger("atenea.avatar")

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
        procesar=True,
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
        procesar=True,
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


#: Pila de dibujado del avatar (06c §2.3). La **ranura** decide exclusividad; la
#: **capa** decide dónde se dibuja, y por eso el orden no lo fija la categoría
#: comercial del ítem sino el nombre de la capa. Una capa aporta dos: una por
#: detrás del cuerpo y otra por delante.
PILA_DE_CAPAS: dict[str, int] = {
    "mount_back": 10,
    "cape_back": 20,
    "aura_back": 25,
    "hair_back": 30,
    "body_base": 40,
    "ears": 45,
    "boots": 50,
    "outfit": 60,
    "accessory_body": 65,
    "gloves": 70,
    "offhand": 80,
    "face": 90,
    "hair_front": 100,
    "head": 110,
    "accessory_face": 115,
    "weapon": 130,
    "cape_front": 140,
    "pet": 150,
    "mount_front": 160,
}

#: Dónde va una capa cuyo nombre no está en la pila. Por delante de todo, a
#: propósito: una pieza mal declarada flotando sobre la cara se ve al instante,
#: mientras que una escondida detrás del cuerpo es justo el fallo que estuvo
#: meses sin que nadie lo notara.
Z_DESCONOCIDO = 999


def capas_de(item: Item, slot: ItemSlot) -> list[dict[str, Any]]:
    """Resuelve `items.render_manifest` a las capas que el cliente debe pintar.

    El manifiesto guardado tiene la forma de 06c §2.7: cada entrada trae `layer`
    (el nombre de la capa), `src` (el archivo) y su rectángulo dentro del lienzo
    maestro. La salida añade lo que el cliente no puede deducir: de qué ranura e
    ítem viene, y en qué orden va.

    Lo que había antes leía `key` y `z`, dos claves que ningún manifiesto escribe.
    Tres consecuencias, todas silenciosas: cada capa caía al código del ítem, de
    modo que una capa emitía **dos filas idénticas** en vez de su cara delantera y
    su trasera; todos los `z` valían cero, así que la pila quedaba ordenada
    alfabéticamente por ranura; y `src` se perdía por el camino, con lo que el
    cliente nunca supo qué archivo pintar. De regalo, las supresiones
    (`suppresses_layers`, que nombra capas) se comparaban contra códigos de ítem y
    no casaban jamás: un yelmo cerrado no tapaba el pelo.
    """
    manifiesto = dict(item.render_manifest or {})
    capas = manifiesto.get("layers")
    if not capas:
        # Un ítem sin manifiesto aporta una capa única con el nombre de su ranura,
        # que es lo que la semilla le habría dado (`CAPAS_POR_RANURA`).
        capas = [{"layer": slot.value}]

    tinte_del_item = manifiesto.get("tint")
    clase_mundo = manifiesto.get("world_class")
    normalizadas: list[dict[str, Any]] = []
    for capa in capas:
        if not isinstance(capa, dict):
            continue
        nombre = str(capa.get("layer") or capa.get("key") or slot.value)
        z = PILA_DE_CAPAS.get(nombre)
        if z is None:
            logger.warning(
                "avatar.capa_desconocida", item=item.code, capa=nombre, slot=slot.value
            )
            z = Z_DESCONOCIDO
        normalizadas.append(
            {
                "slot": slot.value,
                "item_code": item.code,
                "key": nombre,
                "z": z,
                "src": capa.get("src"),
                # Rectángulo dentro del lienzo maestro de 1024×1024 (06c §2.4).
                # Sin él, el cliente no puede colocar una pieza que no ocupe el
                # lienzo entero.
                "x": int(capa.get("x", 0)),
                "y": int(capa.get("y", 0)),
                "w": int(capa.get("w", 0)) or None,
                "h": int(capa.get("h", 0)) or None,
                "tint": capa.get("tint") or tinte_del_item,
                "world_class": clase_mundo,
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
            "world_class": manifiesto.get("world_class"),
        }
        suprimidas.update(str(c) for c in manifiesto.get("suppresses_layers", []) or [])
        if manifiesto.get("two_handed"):
            dos_manos = True
        capas.extend(capas_de(item, equipado.slot))

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
    "PILA_DE_CAPAS",
    "Z_DESCONOCIDO",
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
