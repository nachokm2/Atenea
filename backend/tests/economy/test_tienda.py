"""Pruebas de la tienda: compra atómica, saldo, duplicados y requisitos."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.economy import GoldTransaction, Purchase, UserItem
from app.models.enums import (
    EventType,
    GoldSink,
    GoldSource,
    ItemOrigin,
    ItemRarity,
    LedgerDirection,
    PurchaseStatus,
    RequirementType,
)
from app.models.gamification import DomainEvent
from app.modules.economy import monedero, tienda

pytestmark = pytest.mark.db


@pytest.fixture
def con_oro(db, usuario):
    """Acredita oro al usuario para poder comprar."""

    def _acreditar(cantidad: int) -> None:
        monedero.otorgar_oro(
            db,
            usuario.id,
            amount=cantidad,
            source=GoldSource.WELCOME,
            reason_code="welcome_bag",
            idempotency_key=f"welcome:{uuid.uuid4()}",
        )

    return _acreditar


def test_compra_correcta_descuenta_oro_y_crea_el_item(
    db, configuracion, usuario, personaje, crear_item, crear_listing, con_oro
):
    """La compra debita el ledger, entrega la instancia y audita la orden."""
    con_oro(500)
    item = crear_item(name="Capa del aprendiz", rarity=ItemRarity.COMMON)
    listing = crear_listing(item, price=150)

    resultado = tienda.comprar(
        db,
        usuario.id,
        listing_id=listing.id,
        expected_price=150,
        idempotency_key=str(uuid.uuid4()),
    )

    assert resultado.balance_after == 350
    assert monedero.saldo(db, usuario.id) == 350
    assert monedero.saldo_ledger(db, usuario.id) == 350

    user_item = db.execute(
        sa.select(UserItem).where(
            UserItem.user_id == usuario.id, UserItem.item_id == item.id
        )
    ).scalar_one()
    assert user_item.origin is ItemOrigin.SHOP
    assert user_item.source_ref["purchase_id"] == str(resultado.purchase.id)

    compra = db.get(Purchase, resultado.purchase.id)
    assert compra.status is PurchaseStatus.COMPLETED
    assert compra.price == 150
    assert compra.user_item_id == user_item.id

    debito = db.get(GoldTransaction, compra.gold_transaction_id)
    assert debito.direction is LedgerDirection.DEBIT
    assert debito.sink is GoldSink.PURCHASE
    assert debito.reason_code == "purchase"
    assert debito.balance_after == 350

    tipos = set(
        db.execute(
            sa.select(DomainEvent.event_type).where(DomainEvent.user_id == usuario.id)
        ).scalars()
    )
    assert EventType.GOLD_SPENT in tipos
    assert EventType.ITEM_ACQUIRED in tipos


def test_compra_sin_saldo_falla_sin_efectos(
    db, configuracion, usuario, personaje, crear_item, crear_listing, con_oro
):
    """Sin saldo se lanza `INSUFFICIENT_GOLD` y no queda ni ítem ni orden ni débito."""
    con_oro(100)
    item = crear_item(name="Capa cara", rarity=ItemRarity.RARE)
    listing = crear_listing(item, price=1200, min_level=8)

    with pytest.raises(Exception) as excinfo:
        tienda.comprar(
            db,
            usuario.id,
            listing_id=listing.id,
            expected_price=1200,
            idempotency_key=str(uuid.uuid4()),
        )
    assert getattr(excinfo.value, "code", None) == "INSUFFICIENT_GOLD"
    assert excinfo.value.details["missing"] == 1100

    assert monedero.saldo(db, usuario.id) == 100
    assert monedero.saldo_ledger(db, usuario.id) == 100
    assert db.execute(
        sa.select(sa.func.count()).select_from(Purchase).where(Purchase.user_id == usuario.id)
    ).scalar_one() == 0
    assert db.execute(
        sa.select(sa.func.count()).select_from(UserItem).where(UserItem.user_id == usuario.id)
    ).scalar_one() == 0
    assert db.execute(
        sa.select(sa.func.count()).select_from(GoldTransaction).where(
            GoldTransaction.user_id == usuario.id,
            GoldTransaction.direction == LedgerDirection.DEBIT,
        )
    ).scalar_one() == 0


def test_comprar_dos_veces_el_mismo_item_falla(
    db, configuracion, usuario, personaje, crear_item, crear_listing, con_oro
):
    """Los cosméticos no se acumulan: la segunda compra da 409 `ALREADY_OWNED`."""
    con_oro(1000)
    item = crear_item(name="Capa única")
    listing = crear_listing(item, price=150)

    tienda.comprar(
        db,
        usuario.id,
        listing_id=listing.id,
        idempotency_key=str(uuid.uuid4()),
    )

    with pytest.raises(tienda.YaPoseido) as excinfo:
        tienda.comprar(
            db,
            usuario.id,
            listing_id=listing.id,
            idempotency_key=str(uuid.uuid4()),
        )

    assert excinfo.value.code == "ALREADY_OWNED"
    assert monedero.saldo(db, usuario.id) == 850
    assert db.execute(
        sa.select(sa.func.count()).select_from(UserItem).where(UserItem.user_id == usuario.id)
    ).scalar_one() == 1


def test_compra_repetida_con_la_misma_clave_es_idempotente(
    db, configuracion, usuario, personaje, crear_item, crear_listing, con_oro
):
    """Un reintento con la misma `Idempotency-Key` devuelve la misma compra (§8.3)."""
    con_oro(1000)
    item = crear_item(name="Capa reintentada")
    listing = crear_listing(item, price=150)
    clave = str(uuid.uuid4())

    primera = tienda.comprar(db, usuario.id, listing_id=listing.id, idempotency_key=clave)
    segunda = tienda.comprar(db, usuario.id, listing_id=listing.id, idempotency_key=clave)

    assert primera.purchase.id == segunda.purchase.id
    assert segunda.repetida is True
    assert monedero.saldo(db, usuario.id) == 850
    assert db.execute(
        sa.select(sa.func.count()).select_from(Purchase).where(Purchase.user_id == usuario.id)
    ).scalar_one() == 1


def test_precio_distinto_al_esperado_falla(
    db, configuracion, usuario, personaje, crear_item, crear_listing, con_oro
):
    """`expected_price` obsoleto da 409 `PRICE_CHANGED` y no cobra nada."""
    con_oro(1000)
    listing = crear_listing(crear_item(), price=150)

    with pytest.raises(tienda.PrecioCambiado) as excinfo:
        tienda.comprar(
            db,
            usuario.id,
            listing_id=listing.id,
            expected_price=40,
            idempotency_key=str(uuid.uuid4()),
        )

    assert excinfo.value.details == {"expected_price": 40, "price": 150}
    assert monedero.saldo(db, usuario.id) == 1000


def test_no_se_puede_comprar_un_item_bloqueado_por_requisitos(
    db,
    configuracion,
    usuario,
    personaje,
    area,
    crear_item,
    crear_listing,
    crear_requisito,
    fijar_dominio,
    con_oro,
):
    """Con requisitos sin cumplir la tienda responde 409 `REQUIREMENTS_NOT_MET`."""
    con_oro(5000)
    item = crear_item(name="Capa de maestro", rarity=ItemRarity.EPIC)
    crear_requisito(
        item,
        requirement_type=RequirementType.MASTERY_GTE,
        knowledge_area_id=area.id,
        target_value=80,
    )
    listing = crear_listing(item, price=3000, min_level=1)
    fijar_dominio(usuario, area, 40)

    with pytest.raises(tienda.RequisitosNoCumplidos):
        tienda.comprar(
            db, usuario.id, listing_id=listing.id, idempotency_key=str(uuid.uuid4())
        )

    fijar_dominio(usuario, area, 85)
    resultado = tienda.comprar(
        db, usuario.id, listing_id=listing.id, idempotency_key=str(uuid.uuid4())
    )
    assert resultado.balance_after == 2000


def test_un_item_con_ventaja_de_juego_no_se_vende(
    db, configuracion, usuario, personaje, crear_item, crear_listing, con_oro
):
    """Regla D19: si el manifiesto declara un efecto de juego, el ítem no es vendible."""
    con_oro(1000)
    item = crear_item(
        name="Capa tramposa",
        render_manifest={"layers": [{"key": "capa", "z": 10}], "xp_multiplier": 1.2},
    )
    listing = crear_listing(item, price=150)

    assert tienda.es_cosmetico(item) is False
    with pytest.raises(tienda.NoDisponible):
        tienda.comprar(
            db, usuario.id, listing_id=listing.id, idempotency_key=str(uuid.uuid4())
        )
    assert monedero.saldo(db, usuario.id) == 1000
    assert item.id not in {oferta.item.id for oferta in tienda.catalogo(db, usuario.id).listings}


def test_los_items_de_conocimiento_no_estan_a_la_venta(
    db, configuracion, usuario, personaje, area, crear_item, crear_listing, crear_requisito, con_oro
):
    """"Se ganan aprendiendo": un ítem `origin = knowledge` nunca se cobra en oro."""
    con_oro(5000)
    item = crear_item(
        name="Cetro del saber",
        origin=ItemOrigin.KNOWLEDGE,
        rarity=ItemRarity.EPIC,
        knowledge_area_id=area.id,
        requirement_facts=["mastery"],
    )
    crear_requisito(
        item,
        requirement_type=RequirementType.MASTERY_GTE,
        knowledge_area_id=area.id,
        target_value=80,
    )
    listing = crear_listing(item, price=3000)

    with pytest.raises(tienda.NoDisponible):
        tienda.comprar(
            db, usuario.id, listing_id=listing.id, idempotency_key=str(uuid.uuid4())
        )

    catalogo = tienda.catalogo(db, usuario.id)
    assert [dato["item_code"] for dato in catalogo.knowledge_items] == [item.code]


def test_deshacer_una_compra_devuelve_el_oro_y_revoca_la_instancia(
    db, configuracion, usuario, personaje, crear_item, crear_listing, con_oro
):
    """El "deshacer" no borra: revierte la orden, acredita y revoca el cosmético."""
    con_oro(1000)
    listing = crear_listing(crear_item(name="Capa arrepentida"), price=150)
    compra = tienda.comprar(
        db, usuario.id, listing_id=listing.id, idempotency_key=str(uuid.uuid4())
    )
    assert monedero.saldo(db, usuario.id) == 850

    resultado = tienda.revertir_compra(db, usuario.id, compra.purchase.id)

    assert resultado.purchase.status is PurchaseStatus.REVERSED
    assert resultado.balance_after == 1000
    assert monedero.saldo_ledger(db, usuario.id) == 1000
    assert resultado.user_item.revoked_at is not None

    credito = db.get(GoldTransaction, resultado.purchase.reversal_transaction_id)
    assert credito.source is GoldSource.PURCHASE_REVERSAL
    assert credito.reason_code == "reversal"


def test_catalogo_muestra_precio_saldo_y_destacados(
    db, configuracion, usuario, personaje, crear_item, crear_listing, con_oro
):
    """El catálogo trae saldo, destacados y si cada oferta es asequible."""
    con_oro(200)
    barato = crear_listing(crear_item(name="Capa barata"), price=150, is_featured=True)
    caro = crear_listing(
        crear_item(name="Capa cara", rarity=ItemRarity.RARE), price=1200, min_level=8
    )

    catalogo = tienda.catalogo(db, usuario.id)

    assert catalogo.balance == 200
    assert catalogo.shop_unlocked is True
    assert catalogo.unlock_level == 3
    por_listado = {oferta.listing.id: oferta for oferta in catalogo.listings}
    assert por_listado[barato.id].can_afford is True
    assert por_listado[caro.id].can_afford is False
    assert [oferta.listing.id for oferta in catalogo.featured] == [barato.id]
