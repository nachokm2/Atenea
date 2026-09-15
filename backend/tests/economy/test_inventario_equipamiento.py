"""Pruebas del inventario y del equipamiento (mochila, ranuras y avatar)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.models.enums import (
    EventType,
    ItemOrigin,
    ItemRarity,
    ItemSlot,
    ItemVisibility,
    RequirementType,
)
from app.models.gamification import DomainEvent
from app.models.identity import EquippedItem
from app.modules.economy import equipamiento, inventario, requisitos

pytestmark = pytest.mark.db


def _otorgar(db, usuario, item, origin=ItemOrigin.SHOP):
    """Entrega un ítem al usuario sin pasar por la tienda."""
    return requisitos.otorgar_item(db, usuario.id, item, origin=origin).user_item


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------


def test_inventario_lista_poseidos_y_bloqueados_con_su_requisito(
    db, configuracion, usuario, area, crear_item, crear_requisito, fijar_dominio
):
    """La mochila muestra lo poseído y lo bloqueado visible con su explicación."""
    poseido = crear_item(name="Capa poseída", slot=ItemSlot.CAPE)
    bloqueado = crear_item(
        name="Yelmo del sabio",
        slot=ItemSlot.HEAD,
        rarity=ItemRarity.RARE,
        origin=ItemOrigin.KNOWLEDGE,
        knowledge_area_id=area.id,
    )
    crear_requisito(
        bloqueado,
        requirement_type=RequirementType.MASTERY_GTE,
        knowledge_area_id=area.id,
        target_value=80,
        label_template="Dominio de {area}: {current} / {target} %",
    )
    oculto = crear_item(name="Secreto")
    oculto.visibility = ItemVisibility.HIDDEN
    db.flush()

    _otorgar(db, usuario, poseido)
    fijar_dominio(usuario, area, 20)

    pagina = inventario.listar_inventario(db, usuario.id)
    por_codigo = {fila.item.code: fila for fila in pagina.items}

    assert por_codigo[poseido.code].owned is True
    assert por_codigo[poseido.code].locked is False
    assert por_codigo[bloqueado.code].owned is False
    assert por_codigo[bloqueado.code].locked is True
    assert por_codigo[bloqueado.code].requirements[0]["label"] == "Dominio de SQL: 20 / 80 %"
    assert oculto.code not in por_codigo
    assert pagina.total == 2


def test_inventario_filtra_por_slot_rareza_y_estado(
    db, configuracion, usuario, crear_item
):
    """Los filtros `slot`, `rarity` y `state` del contrato acotan la mochila."""
    capa = crear_item(name="Capa", slot=ItemSlot.CAPE, rarity=ItemRarity.COMMON)
    espada = crear_item(name="Espada", slot=ItemSlot.WEAPON, rarity=ItemRarity.RARE)
    _otorgar(db, usuario, capa)

    solo_capas = inventario.listar_inventario(db, usuario.id, slot=ItemSlot.CAPE)
    assert [fila.item.code for fila in solo_capas.items] == [capa.code]

    solo_raros = inventario.listar_inventario(db, usuario.id, rarity=ItemRarity.RARE)
    assert [fila.item.code for fila in solo_raros.items] == [espada.code]

    poseidos = inventario.listar_inventario(db, usuario.id, state="owned")
    assert [fila.item.code for fila in poseidos.items] == [capa.code]

    bloqueados = inventario.listar_inventario(db, usuario.id, state="locked")
    assert [fila.item.code for fila in bloqueados.items] == [espada.code]


def test_la_ficha_apaga_la_insignia_de_nuevo(db, configuracion, usuario, crear_item):
    """Abrir la ficha marca la instancia como vista (`is_new = false`)."""
    item = crear_item(name="Capa nueva")
    user_item = _otorgar(db, usuario, item)
    assert user_item.is_new is True

    ficha = inventario.detalle_item(db, usuario.id, item.id)
    assert ficha.owned is True
    assert ficha.is_new is True  # la respuesta aún la muestra como nueva

    db.refresh(user_item)
    assert user_item.is_new is False


def test_previsualizar_emite_el_evento_de_analitica(db, configuracion, usuario, crear_item):
    """`POST /items/{id}/preview` registra `ITEM_PREVIEWED` con `locked`."""
    item = crear_item(name="Capa mirada")
    inventario.registrar_previsualizacion(db, usuario.id, item.id)

    evento = db.execute(
        sa.select(DomainEvent).where(
            DomainEvent.user_id == usuario.id,
            DomainEvent.event_type == EventType.ITEM_PREVIEWED,
        )
    ).scalar_one()
    assert evento.payload == {"item_code": item.code, "locked": False}


# ---------------------------------------------------------------------------
# Equipamiento
# ---------------------------------------------------------------------------


def test_equipar_en_slot_incorrecto_falla(
    db, configuracion, usuario, personaje, crear_item
):
    """Pedir una ranura que no es la del ítem es un 422 y no equipa nada."""
    capa = crear_item(name="Capa", slot=ItemSlot.CAPE)
    user_item = _otorgar(db, usuario, capa)

    with pytest.raises(equipamiento.RanuraInvalida) as excinfo:
        equipamiento.equipar(db, usuario.id, user_item.id, slot=ItemSlot.HEAD)

    assert excinfo.value.code == "VALIDATION_ERROR"
    assert excinfo.value.details["item_slot"] == "cape"
    assert db.execute(
        sa.select(sa.func.count()).select_from(EquippedItem).where(
            EquippedItem.character_id == personaje.id
        )
    ).scalar_one() == 0


def test_equipar_en_una_ranura_reservada_falla(
    db, configuracion, usuario, personaje, crear_item
):
    """`pet` y `mount` están reservadas: no aparecen en `items.slots_active`."""
    mascota = crear_item(name="Mascota", slot=ItemSlot.PET)
    user_item = _otorgar(db, usuario, mascota)

    with pytest.raises(equipamiento.RanuraInvalida):
        equipamiento.equipar(db, usuario.id, user_item.id)


def test_equipar_y_desequipar_actualiza_el_avatar(
    db, configuracion, usuario, personaje, crear_item
):
    """Equipar reemplaza lo anterior, emite los eventos y recalcula las capas."""
    primera = crear_item(
        name="Capa vieja",
        slot=ItemSlot.CAPE,
        render_manifest={"layers": [{"key": "capa_vieja", "z": 20}]},
    )
    segunda = crear_item(
        name="Capa nueva",
        slot=ItemSlot.CAPE,
        render_manifest={"layers": [{"key": "capa_nueva", "z": 20}]},
    )
    ui_primera = _otorgar(db, usuario, primera)
    ui_segunda = _otorgar(db, usuario, segunda)

    cambio = equipamiento.equipar(db, usuario.id, ui_primera.id)
    assert cambio.slot is ItemSlot.CAPE
    assert cambio.slots_filled == 1
    assert cambio.slots_total == 8

    avatar = equipamiento.configuracion_avatar(db, usuario.id)
    assert avatar["equipment"]["cape"]["item_code"] == primera.code
    assert [capa["key"] for capa in avatar["layers"]] == ["capa_vieja"]

    reemplazo = equipamiento.equipar(db, usuario.id, ui_segunda.id)
    assert reemplazo.replaced_user_item_id == ui_primera.id
    avatar = equipamiento.configuracion_avatar(db, usuario.id)
    assert [capa["key"] for capa in avatar["layers"]] == ["capa_nueva"]

    equipamiento.desequipar(db, usuario.id, ItemSlot.CAPE)
    avatar = equipamiento.configuracion_avatar(db, usuario.id)
    assert avatar["equipment"] == {}
    assert avatar["layers"] == []

    tipos = list(
        db.execute(
            sa.select(DomainEvent.event_type).where(DomainEvent.user_id == usuario.id)
        ).scalars()
    )
    assert tipos.count(EventType.ITEM_EQUIPPED) == 2
    assert tipos.count(EventType.ITEM_UNEQUIPPED) == 1


def test_no_se_puede_equipar_un_item_ajeno(
    db, configuracion, usuario, personaje, crear_item
):
    """La instancia debe pertenecer al usuario; si no, 404 (nunca 403, §8.7)."""
    from app.core.errors import NotFound
    from app.models.identity import User

    otro = User(email="otro-economia@atenea.test")
    db.add(otro)
    db.flush()
    item = crear_item(name="Capa ajena")
    ajena = requisitos.otorgar_item(db, otro.id, item, origin=ItemOrigin.SHOP).user_item

    with pytest.raises(NotFound):
        equipamiento.equipar(db, usuario.id, ajena.id)


def test_aplicar_equipamiento_atomico(db, configuracion, usuario, personaje, crear_item):
    """`PUT /avatar/equipment` aplica el mapa completo: equipa y desequipa a la vez."""
    yelmo = crear_item(
        name="Yelmo",
        slot=ItemSlot.HEAD,
        render_manifest={"layers": [{"key": "yelmo", "z": 40}], "suppresses_layers": ["pelo"]},
    )
    capa = crear_item(
        name="Capa",
        slot=ItemSlot.CAPE,
        render_manifest={"layers": [{"key": "capa", "z": 10}]},
    )
    ui_yelmo = _otorgar(db, usuario, yelmo)
    ui_capa = _otorgar(db, usuario, capa)
    equipamiento.equipar(db, usuario.id, ui_capa.id)

    avatar = equipamiento.aplicar_equipamiento(
        db, usuario.id, {"head": ui_yelmo.id, "cape": None}
    )

    assert set(avatar["equipment"]) == {"head"}
    assert [capa["key"] for capa in avatar["layers"]] == ["yelmo"]
    assert avatar["etag"]


def test_un_arma_a_dos_manos_libera_la_mano_secundaria(
    db, configuracion, usuario, personaje, crear_item
):
    """`two_handed` quita la capa de `offhand` del manifiesto resultante."""
    espada = crear_item(
        name="Espadón",
        slot=ItemSlot.WEAPON,
        render_manifest={"layers": [{"key": "espadon", "z": 50}], "two_handed": True},
    )
    escudo = crear_item(
        name="Escudo",
        slot=ItemSlot.OFFHAND,
        render_manifest={"layers": [{"key": "escudo", "z": 45}]},
    )
    equipamiento.equipar(db, usuario.id, _otorgar(db, usuario, escudo).id)
    equipamiento.equipar(db, usuario.id, _otorgar(db, usuario, espada).id)

    avatar = equipamiento.configuracion_avatar(db, usuario.id)

    assert [capa["key"] for capa in avatar["layers"]] == ["espadon"]
    assert set(avatar["equipment"]) == {"weapon", "offhand"}


def test_equipar_llama_al_motor(
    db, configuracion, usuario, personaje, crear_item, monkeypatch
):
    """Equipar tiene que llegar al motor, no quedarse en la tabla.

    Los eventos de `economy` se escribían con `processing_status = PENDING` y
    nadie los drenaba nunca: en la base de desarrollo había ochenta
    `ITEM_ACQUIRED` y cuarenta y cuatro `ITEM_EQUIPPED` sin procesar. Cinco
    logros del catálogo cuelgan de esos dos eventos y eran inalcanzables.

    Se comprueba la llamada y no el veredicto porque el motor necesita la
    configuración de juego entera, que esta suite no siembra a propósito: aquí
    se prueba economía, no gamificación. Que el premio llegue de verdad lo
    comprueba el recorrido contra la API viva.
    """
    from app.models.enums import EventType
    from app.modules.gamification import motor

    vistos: list[EventType] = []
    original = motor.procesar_evento

    def _espiar(db_, evento, **kwargs):
        vistos.append(evento.event_type)
        return original(db_, evento, **kwargs)

    monkeypatch.setattr(motor, "procesar_evento", _espiar)
    item = crear_item(
        name="Capa de prueba",
        slot=ItemSlot.CAPE,
        render_manifest={"layers": [{"key": "capa_prueba", "z": 20}]},
    )
    propio = _otorgar(db, usuario, item)

    equipamiento.equipar(db, usuario.id, propio.id)

    assert EventType.ITEM_EQUIPPED in vistos, "equipar tiene que pasar por el motor"


def test_si_el_motor_falla_equipar_sigue_funcionando(
    db, configuracion, usuario, personaje, crear_item, monkeypatch
):
    """La acción del aprendiz vale más que el logro que la acompaña.

    Si el motor no puede calcular la recompensa, el objeto se equipa igual y el
    evento queda pendiente para cobrarse después. Lo contrario seria que el
    Vestidor dejara de funcionar por un fallo de gamificación.
    """
    from app.models.enums import EventStatus, EventType
    from app.models.gamification import DomainEvent
    from app.modules.gamification import motor

    def _revienta(*args, **kwargs):
        raise RuntimeError("el motor no esta disponible")

    monkeypatch.setattr(motor, "procesar_evento", _revienta)
    item = crear_item(
        name="Capa tozuda",
        slot=ItemSlot.CAPE,
        render_manifest={"layers": [{"key": "capa_tozuda", "z": 20}]},
    )

    propio = _otorgar(db, usuario, item)
    equipamiento.equipar(db, usuario.id, propio.id)

    evento = db.execute(
        sa.select(DomainEvent)
        .where(DomainEvent.event_type == EventType.ITEM_EQUIPPED)
        .order_by(DomainEvent.occurred_at.desc())
    ).scalars().first()
    assert evento is not None
    assert evento.processing_status == EventStatus.PENDING
