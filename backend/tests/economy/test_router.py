"""Pruebas de las rutas HTTP del módulo `economy` (§7.2 y §7.3).

Se monta una app mínima con el router de economía y se sustituyen las dependencias
`get_db` y `get_current_user`: así se prueba el contrato de la API sin depender de
`app/main.py` ni del router raíz, que pertenecen a otros agentes.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.errors import AteneaError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import register_exception_handlers
from app.models.enums import GoldSource, ItemSlot
from app.modules.economy import equipamiento, monedero, requisitos
from app.modules.economy.router import router

pytestmark = pytest.mark.db


@pytest.fixture
def cliente(db, usuario):
    """Cliente HTTP con la sesión de prueba y el usuario ya autenticado."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: usuario
    with TestClient(app) as cliente_http:
        yield cliente_http


def test_get_shop_devuelve_saldo_y_listados(
    cliente, db, configuracion, usuario, personaje, crear_item, crear_listing
):
    """`GET /api/v1/shop` trae saldo, destacados y listados con precio del servidor."""
    monedero.otorgar_oro(
        db,
        usuario.id,
        amount=500,
        source=GoldSource.WELCOME,
        reason_code="welcome_bag",
        idempotency_key="w1",
    )
    listing = crear_listing(crear_item(name="Capa de la API"), price=150, is_featured=True)

    respuesta = cliente.get("/api/v1/shop")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["balance"] == 500
    assert cuerpo["unlock_level"] == 3
    assert cuerpo["listings"][0]["listing_id"] == str(listing.id)
    assert cuerpo["listings"][0]["price"] == 150
    assert cuerpo["listings"][0]["item"]["rarity"] == "common"
    assert cuerpo["featured"][0]["listing_id"] == str(listing.id)


def test_post_shop_purchase_exige_la_cabecera_de_idempotencia(
    cliente, db, configuracion, usuario, personaje, crear_item, crear_listing
):
    """Sin `Idempotency-Key` la compra responde 400 `IDEMPOTENCY_KEY_REQUIRED` (§8.3)."""
    listing = crear_listing(crear_item(), price=150)

    respuesta = cliente.post(
        "/api/v1/shop/purchase", json={"listing_id": str(listing.id)}
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_post_shop_purchase_compra_y_devuelve_el_saldo(
    cliente, db, configuracion, usuario, personaje, crear_item, crear_listing
):
    """La compra por HTTP devuelve la orden, la instancia y el saldo posterior."""
    monedero.otorgar_oro(
        db,
        usuario.id,
        amount=500,
        source=GoldSource.WELCOME,
        reason_code="welcome_bag",
        idempotency_key="w1",
    )
    listing = crear_listing(crear_item(name="Capa comprada"), price=150)

    respuesta = cliente.post(
        "/api/v1/shop/purchase",
        json={"listing_id": str(listing.id), "expected_price": 150},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["balance_after"] == 350
    assert cuerpo["purchase"]["status"] == "completed"
    assert cuerpo["user_item"]["origin"] == "shop"


def test_post_shop_purchase_sin_saldo_responde_409(
    cliente, db, configuracion, usuario, personaje, crear_item, crear_listing
):
    """El error del contrato viaja con su código y sus detalles en español."""
    listing = crear_listing(crear_item(), price=150)

    respuesta = cliente.post(
        "/api/v1/shop/purchase",
        json={"listing_id": str(listing.id)},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    assert respuesta.status_code == 409
    error = respuesta.json()["error"]
    assert error["code"] == "INSUFFICIENT_GOLD"
    assert error["message"] == "No te alcanza el oro para esta compra."
    assert error["details"] == {"required": 150, "balance": 0, "missing": 150}


def test_get_inventory_y_ficha_de_item(
    cliente, db, configuracion, usuario, personaje, crear_item
):
    """`GET /inventory` pagina con el sobre de §8.2 y `GET /items/{id}` explica."""
    item = crear_item(name="Capa listada")
    requisitos.otorgar_item(db, usuario.id, item, origin=item.origin)

    lista = cliente.get("/api/v1/inventory", params={"limit": 10})
    assert lista.status_code == 200
    cuerpo = lista.json()
    assert cuerpo["page"] == {
        "limit": 10,
        "next_cursor": None,
        "has_more": False,
        "total": 1,
    }
    assert cuerpo["items"][0]["item"]["code"] == item.code
    assert cuerpo["items"][0]["owned"] is True

    ficha = cliente.get(f"/api/v1/items/{item.id}")
    assert ficha.status_code == 200
    assert ficha.json()["item"]["name"] == "Capa listada"


def test_equipar_valida_la_ranura_y_resuelve_las_capas(
    db, configuracion, usuario, personaje, crear_item
):
    """Equipar valida la ranura y recompone el avatar por capas.

    La **ruta** `PUT /avatar/equipment` la publica el módulo `identity`, que es
    el dueño del personaje (CONTRACT.md §7.2) y delega en este servicio; sus
    pruebas de API viven en `tests/identity/test_personaje.py`. Aquí se prueba
    el servicio, que es lo que `economy` posee.
    """
    capa = crear_item(
        name="Capa equipable",
        slot=ItemSlot.CAPE,
        render_manifest={"layers": [{"key": "capa", "z": 20}]},
    )
    user_item = requisitos.otorgar_item(db, usuario.id, capa, origin=capa.origin).user_item

    datos = equipamiento.aplicar_equipamiento(db, usuario.id, {"cape": str(user_item.id)})

    assert datos["equipment"]["cape"]["item_code"] == capa.code
    assert datos["layers"][0]["key"] == "capa"

    # Una capa en la ranura de la cabeza no se acepta, y el mapa entero se aborta.
    with pytest.raises(AteneaError) as fallo:
        equipamiento.aplicar_equipamiento(db, usuario.id, {"head": str(user_item.id)})
    assert fallo.value.code in {"VALIDATION_ERROR", "SLOT_MISMATCH"}


def test_get_wallet_devuelve_saldo_y_movimientos(
    cliente, db, configuracion, usuario
):
    """`GET /wallet` expone saldo, acumulados y los últimos movimientos del ledger."""
    monedero.otorgar_oro(
        db,
        usuario.id,
        amount=100,
        source=GoldSource.WELCOME,
        reason_code="welcome_bag",
        idempotency_key="w1",
    )

    respuesta = cliente.get("/api/v1/wallet")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["balance"] == 100
    assert cuerpo["lifetime_earned"] == 100
    assert cuerpo["transactions"]["items"][0]["source"] == "welcome"
    assert cuerpo["transactions"]["items"][0]["direction"] == "credit"
