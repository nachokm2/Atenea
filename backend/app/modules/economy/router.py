"""Rutas HTTP del módulo `economy` (contrato §7.2 y §7.3).

| Método | Ruta |
|---|---|
| GET | `/shop` |
| POST | `/shop/purchase` (**Idempotency-Key**) |
| POST | `/shop/purchases/{purchase_id}/reverse` |
| GET | `/wallet` |
| GET | `/inventory` |
| GET | `/items/{item_id}` |
| POST | `/items/{item_id}/preview` |
| GET | `/avatar` |
| PUT | `/avatar/equipment` |

El router se expone como `router = APIRouter()` sin prefijo: el prefijo `/api/v1` y el
montaje los pone el agente de integración en `app/api/v1/__init__.py`.

TODO(A1/A8): aplicar el límite de 10 peticiones por minuto a `POST /shop/purchase`
(`shop.purchase_rate_limit_per_minute`) cuando `slowapi` esté montado en `app/main.py`.
TODO(A2): `PUT /avatar/traits` pertenece a los rasgos del personaje (`identity`); aquí
solo se sirve el equipamiento y el manifiesto de capas resultante.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import CurrentUser, DbSession, IdempotencyDep
from app.core.limites import freno
from app.models.enums import ItemOrigin, ItemRarity, ItemSlot
from app.modules.economy import equipamiento, inventario, monedero, tienda
from app.modules.economy.schemas import (
    GoldTransactionOut,
    InventoryItemOut,
    ItemDetailOut,
    ItemOut,
    KnowledgeItemOut,
    PageGoldTransactionOut,
    PageInventoryOut,
    PageOut,
    PurchaseIn,
    PurchaseOut,
    PurchaseRecordOut,
    RequirementProgressOut,
    ShopListingOut,
    ShopOut,
    UserItemOut,
    WalletOut,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Conversión de dominio a esquema
# ---------------------------------------------------------------------------


def _requisitos(crudos: list[dict[str, Any]]) -> list[RequirementProgressOut]:
    """Convierte las condiciones evaluadas al esquema de salida."""
    return [RequirementProgressOut.model_validate(dato) for dato in crudos]


def _fila_inventario(fila: inventario.FilaInventario) -> InventoryItemOut:
    """Adapta una fila del inventario al esquema del contrato."""
    return InventoryItemOut(
        item=ItemOut.model_validate(fila.item),
        owned=fila.owned,
        locked=fila.locked,
        is_new=fila.is_new,
        equipped=fila.equipped,
        user_item_id=fila.user_item_id,
        acquired_at=fila.acquired_at,
        equipped_slot=fila.equipped_slot,
        requirements=_requisitos(fila.requirements),
    )


def _oferta(oferta: tienda.OfertaTienda) -> ShopListingOut:
    """Adapta un listado de la tienda al esquema del contrato."""
    return ShopListingOut(
        listing_id=oferta.listing.id,
        item=ItemOut.model_validate(oferta.item),
        currency=oferta.listing.currency,
        price=oferta.price,
        min_level=oferta.min_level,
        is_featured=oferta.is_featured,
        owned=oferta.owned,
        locked=oferta.locked,
        can_afford=oferta.can_afford,
        requirements=_requisitos(oferta.requirements),
    )


def _compra(db, usuario_id: uuid.UUID, resultado: tienda.ResultadoCompra) -> PurchaseOut:
    """Adapta el resultado de una compra, incluyendo las capas del avatar."""
    try:
        capas = equipamiento.configuracion_avatar(db, usuario_id)["layers"]
    except Exception:
        capas = []
    return PurchaseOut(
        purchase=PurchaseRecordOut.model_validate(resultado.purchase),
        user_item=(
            UserItemOut.model_validate(resultado.user_item) if resultado.user_item else None
        ),
        item=ItemOut.model_validate(resultado.item) if resultado.item else None,
        balance_after=resultado.balance_after,
        avatar_layers=capas,
    )


# ---------------------------------------------------------------------------
# Tienda
# ---------------------------------------------------------------------------


@router.get("/shop", response_model=ShopOut, tags=["tienda"], summary="Catálogo de la tienda")
def obtener_tienda(
    user: CurrentUser,
    db: DbSession,
    slot: ItemSlot | None = Query(default=None, description="Filtra por ranura."),
    rarity: ItemRarity | None = Query(default=None, description="Filtra por rareza."),
    affordable: bool = Query(default=False, description="Solo lo que alcanza el saldo."),
) -> ShopOut:
    """Catálogo activo, destacados, saldo y sección "Se ganan aprendiendo" (P15)."""
    datos = tienda.catalogo(
        db, user.id, slot=slot, rarity=rarity, solo_asequibles=affordable
    )
    return ShopOut(
        balance=datos.balance,
        featured=[_oferta(oferta) for oferta in datos.featured],
        listings=[_oferta(oferta) for oferta in datos.listings],
        knowledge_items=[
            KnowledgeItemOut.model_validate(
                {**dato, "requirements": _requisitos(dato["requirements"])}
            )
            for dato in datos.knowledge_items
        ],
        shop_unlocked=datos.shop_unlocked,
        unlock_level=datos.unlock_level,
    )


@router.post(
    "/shop/purchase",
    response_model=PurchaseOut,
    tags=["tienda"],
    summary="Compra atómica de un cosmético",
    # 10 por minuto (§8.7): mueve oro, y conviene que no se mueva a ráfagas.
    dependencies=[Depends(freno("10/minute"))],
)
def comprar_item(
    user: CurrentUser,
    db: DbSession,
    idempotency: IdempotencyDep,
    cuerpo: PurchaseIn,
    response: Response,
) -> PurchaseOut:
    """Descuenta el oro, entrega el ítem y audita la orden en una sola transacción."""
    clave = idempotency.require()
    resultado = tienda.comprar(
        db,
        user.id,
        listing_id=cuerpo.listing_id,
        expected_price=cuerpo.expected_price,
        idempotency_key=clave,
    )
    db.commit()
    response.status_code = status.HTTP_200_OK if resultado.repetida else status.HTTP_201_CREATED
    return _compra(db, user.id, resultado)


@router.post(
    "/shop/purchases/{purchase_id}/reverse",
    response_model=PurchaseOut,
    tags=["tienda"],
    summary="Deshacer una compra reciente",
)
def deshacer_compra(user: CurrentUser, db: DbSession, purchase_id: uuid.UUID) -> PurchaseOut:
    """"Deshacer" dentro de `shop.purchase_reversal_seconds`."""
    resultado = tienda.revertir_compra(db, user.id, purchase_id)
    db.commit()
    return _compra(db, user.id, resultado)


# ---------------------------------------------------------------------------
# Billetera
# ---------------------------------------------------------------------------


@router.get("/wallet", response_model=WalletOut, tags=["economía"], summary="Saldo y movimientos")
def obtener_billetera(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> WalletOut:
    """Saldo cacheado, acumulados y últimos movimientos del ledger."""
    billetera = monedero.obtener_billetera(db, user.id)
    db.commit()
    filas = monedero.movimientos(db, user.id, limit=limit)
    return WalletOut(
        balance=int(billetera.balance),
        lifetime_earned=int(billetera.lifetime_earned),
        lifetime_spent=int(billetera.lifetime_spent),
        currency=billetera.currency,
        transactions=PageGoldTransactionOut(
            items=[GoldTransactionOut.model_validate(fila) for fila in filas],
            page=PageOut(limit=limit, next_cursor=None, has_more=False, total=None),
        ),
    )


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------


@router.get(
    "/inventory",
    response_model=PageInventoryOut,
    tags=["inventario"],
    summary="Mochila: poseídos y bloqueados visibles",
)
def listar_inventario(
    user: CurrentUser,
    db: DbSession,
    slot: ItemSlot | None = Query(default=None),
    rarity: ItemRarity | None = Query(default=None),
    state: str | None = Query(default=None, description="owned, locked, equipped, new o unlocked."),
    origin: ItemOrigin | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> PageInventoryOut:
    """Listado paginado por cursor con el progreso de requisitos de lo bloqueado (P16)."""
    pagina = inventario.listar_inventario(
        db,
        user.id,
        slot=slot,
        rarity=rarity,
        state=state,
        origin=origin,
        limit=limit,
        cursor=cursor,
    )
    return PageInventoryOut(
        items=[_fila_inventario(fila) for fila in pagina.items],
        page=PageOut(
            limit=pagina.limit,
            next_cursor=pagina.next_cursor,
            has_more=pagina.has_more,
            total=pagina.total,
        ),
    )


@router.get(
    "/items/{item_id}",
    response_model=ItemDetailOut,
    tags=["inventario"],
    summary="Ficha de un ítem con explicación de requisitos",
)
def obtener_item(user: CurrentUser, db: DbSession, item_id: uuid.UUID) -> ItemDetailOut:
    """Lore, rareza, origen, manifiesto y `explain` de los requisitos."""
    fila = inventario.detalle_item(db, user.id, item_id)
    db.commit()
    base = _fila_inventario(fila)
    etiquetas = [req.label for req in base.requirements if req.label]
    return ItemDetailOut(
        **base.model_dump(),
        unlock_reason=" y ".join(etiquetas) if etiquetas else None,
    )


@router.post(
    "/items/{item_id}/preview",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["inventario"],
    summary="Registra la analítica de «Probar»",
)
def previsualizar_item(user: CurrentUser, db: DbSession, item_id: uuid.UUID) -> Response:
    """Emite `ITEM_PREVIEWED`; no cambia nada del inventario."""
    inventario.registrar_previsualizacion(db, user.id, item_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Nota de límites de módulo (CONTRACT.md §7.2)
# ---------------------------------------------------------------------------
# Las rutas `GET /avatar`, `PUT /avatar/traits` y `PUT /avatar/equipment` las
# publica el módulo `identity`, que es el dueño del personaje y del avatar y
# delega en los servicios de este módulo (`economy.equipamiento`). Aquí solo
# viven el inventario, la ficha de ítem, la tienda y el monedero.

__all__ = ["router"]
