"""`world_class`: la clase visual de lo empuñado, para la figura simplificada
del mundo caminable (`docs/planes/mundo-caminable.md`, Parte B).

Esa figura no tiene fidelidad por ítem — el arma es un prop estático, no un
fotograma — así que 46 ítems se reducen a seis siluetas (`WorldWeaponClass`).
La regla real: todo ítem `WEAPON`/`OFFHAND` del catálogo trae una clase, o el
cliente no dibuja ningún prop en esa mano. Sin este archivo, un arma nueva sin
clase asignada fallaría en silencio: no hay ninguna otra prueba que la fuerce.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.economy import UserItem
from app.models.enums import ItemSlot, WorldWeaponClass
from app.models.identity import Character, User
from app.modules.economy import equipamiento
from app.seeds.items import ItemSemilla, por_codigo


def test_todo_item_de_arma_u_offhand_trae_clase_de_mundo() -> None:
    """Sin esto, un arma nueva del catálogo camina sin nada en la mano y nadie
    se entera hasta que alguien la ve en el dispositivo."""
    catalogo = por_codigo()
    sin_clase = [
        item.code
        for item in catalogo.values()
        if item.slot in (ItemSlot.WEAPON, ItemSlot.OFFHAND)
        and not item.render_manifest.get("world_class")
    ]
    assert not sin_clase, f"ítems de arma/escudo sin clase de mundo: {sin_clase}"


def test_la_clase_declarada_es_una_del_enum_real() -> None:
    """Un valor inventado a mano (typo) pasaría la prueba anterior y fallaría
    solo en el cliente, mucho más tarde."""
    catalogo = por_codigo()
    valores_validos = {c.value for c in WorldWeaponClass}
    for item in catalogo.values():
        clase = item.render_manifest.get("world_class")
        if clase is not None:
            assert clase in valores_validos, f"{item.code}: clase inválida {clase!r}"


def test_un_item_sin_clase_no_inventa_una(
    db: Session, usuario: User, personaje: Character, configuracion: dict, crear_item
) -> None:
    """`pluma_primer_paso` es del catálogo real y no lleva clase a propósito
    (a 8dp es invisible) — el equipo resuelto debe decirlo con `None`, no con
    una clase por defecto que nadie pidió."""
    semilla: ItemSemilla = por_codigo()["pluma_primer_paso"]
    assert not semilla.render_manifest.get("world_class"), (
        "esta prueba asume que pluma_primer_paso sigue sin clase; si eso cambió, "
        "ajusta el ítem de ejemplo"
    )
    item = crear_item(
        code=semilla.code,
        slot=semilla.slot,
        rarity=semilla.rarity,
        render_manifest=semilla.render_manifest,
    )
    propio = UserItem(user_id=usuario.id, item_id=item.id, origin=item.origin)
    db.add(propio)
    db.flush()
    equipamiento.equipar(db, usuario.id, propio.id, slot=item.slot)

    equipo = equipamiento.configuracion_avatar(db, usuario.id)["equipment"]
    assert equipo[ItemSlot.ACCESSORY.value]["world_class"] is None


def test_la_clase_de_mundo_se_emite_en_el_equipo_resuelto(
    db: Session, usuario: User, personaje: Character, configuracion: dict, crear_item
) -> None:
    """La ida completa: semilla -> `render_manifest` -> `configuracion_avatar`.

    `espada_del_sql` es una espada real del catálogo (origin=knowledge) — se
    prueba con ella y no con un ítem inventado para que un cambio futuro de
    su clase real rompa esta prueba, no la deje mintiendo en verde.
    """
    semilla: ItemSemilla = por_codigo()["espada_del_sql"]
    assert semilla.render_manifest.get("world_class") == WorldWeaponClass.BLADE.value

    item = crear_item(
        code=semilla.code,
        slot=semilla.slot,
        rarity=semilla.rarity,
        render_manifest=semilla.render_manifest,
    )
    propio = UserItem(user_id=usuario.id, item_id=item.id, origin=item.origin)
    db.add(propio)
    db.flush()
    equipamiento.equipar(db, usuario.id, propio.id, slot=item.slot)

    equipo = equipamiento.configuracion_avatar(db, usuario.id)["equipment"]
    assert equipo[ItemSlot.WEAPON.value]["world_class"] == "blade"


def test_la_clase_de_mundo_tambien_viaja_por_capa(
    db: Session, usuario: User, personaje: Character, configuracion: dict, crear_item
) -> None:
    """`capas_de()` alimenta `layers[]`, el otro camino real hacia el cliente
    (y la ficha de `GET /items/{item_id}`, que ni equipa nada). Si solo se
    emitiera en `equipment[slot]`, una futura `figura_del_mundo.dart` que lea
    `CapaAvatar.worldClass` en vez del mapa de equipo se quedaría sin nada."""
    semilla: ItemSemilla = por_codigo()["escudo_roble"]
    assert semilla.render_manifest.get("world_class") == WorldWeaponClass.SHIELD.value

    item = crear_item(
        code=semilla.code,
        slot=semilla.slot,
        rarity=semilla.rarity,
        render_manifest=semilla.render_manifest,
    )
    propio = UserItem(user_id=usuario.id, item_id=item.id, origin=item.origin)
    db.add(propio)
    db.flush()
    equipamiento.equipar(db, usuario.id, propio.id, slot=item.slot)

    capas = equipamiento.configuracion_avatar(db, usuario.id)["layers"]
    capa_offhand = next(c for c in capas if c["slot"] == ItemSlot.OFFHAND.value)
    assert capa_offhand["world_class"] == "shield"
