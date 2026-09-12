"""Esquemas Pydantic v2 del módulo `economy` (entradas `In`, salidas `Out`, §8.8).

Reglas aplicadas:

- Un esquema de salida **nunca** hereda de un modelo SQLAlchemy: se construye con
  `model_config = ConfigDict(from_attributes=True)` o desde las dataclases del módulo.
- Los enums se serializan por su **valor** (`"epic"`, `"cape"`), que es lo que espera la
  app; los nombres en MAYÚSCULAS son solo la representación en la base de datos.
- Ninguna respuesta expone identificadores de otros usuarios ni valores internos de
  `game_configs` marcados como privados.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    Currency,
    GoldSink,
    GoldSource,
    ItemOrigin,
    ItemRarity,
    ItemSlot,
    ItemVisibility,
    LedgerDirection,
    PurchaseStatus,
    RequirementType,
)


class EsquemaBase(BaseModel):
    """Base común: permite construir desde atributos de objetos del dominio."""

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Paginación (§8.2)
# ---------------------------------------------------------------------------


class PageOut(EsquemaBase):
    """Sobre de paginación por cursor opaco."""

    limit: int
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None


# ---------------------------------------------------------------------------
# Ítems y requisitos
# ---------------------------------------------------------------------------


class RequirementProgressOut(EsquemaBase):
    """Una condición de desbloqueo explicada (modo `explain` de §6.13)."""

    type: RequirementType
    met: bool
    current: float
    target: float
    label: str
    cta: str | None = None
    group_index: int = 0
    position: int = 0
    knowledge_area_id: uuid.UUID | None = None
    area_slug: str | None = None


class ItemOut(EsquemaBase):
    """Ficha breve de un ítem del catálogo (sin ningún campo de estadística: D19)."""

    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    slot: ItemSlot
    rarity: ItemRarity
    origin: ItemOrigin
    visibility: ItemVisibility
    icon_key: str | None = None
    render_manifest: dict[str, Any] = Field(default_factory=dict)
    knowledge_area_id: uuid.UUID | None = None
    set_code: str | None = None


class InventoryItemOut(EsquemaBase):
    """Fila de la mochila: el ítem, si se posee, si está equipado y qué le falta."""

    item: ItemOut
    owned: bool
    locked: bool
    is_new: bool
    equipped: bool
    user_item_id: uuid.UUID | None = None
    acquired_at: dt.datetime | None = None
    equipped_slot: ItemSlot | None = None
    requirements: list[RequirementProgressOut] = Field(default_factory=list)


class ItemDetailOut(InventoryItemOut):
    """Ficha completa del ítem (`GET /api/v1/items/{item_id}`)."""

    unlock_reason: str | None = None


class PageInventoryOut(EsquemaBase):
    """`Page<InventoryItemOut>` del contrato."""

    items: list[InventoryItemOut]
    page: PageOut


# ---------------------------------------------------------------------------
# Tienda
# ---------------------------------------------------------------------------


class ShopListingOut(EsquemaBase):
    """Oferta de la tienda con el precio **del servidor**."""

    listing_id: uuid.UUID
    item: ItemOut
    currency: Currency
    price: int
    min_level: int
    is_featured: bool
    owned: bool
    locked: bool
    can_afford: bool
    requirements: list[RequirementProgressOut] = Field(default_factory=list)


class KnowledgeItemOut(EsquemaBase):
    """Ítem de la sección "Se ganan aprendiendo" (nunca está a la venta)."""

    item_id: uuid.UUID
    item_code: str
    name: str
    slot: ItemSlot
    rarity: ItemRarity
    owned: bool
    unlocked: bool
    requirements: list[RequirementProgressOut] = Field(default_factory=list)


class ShopOut(EsquemaBase):
    """Respuesta de `GET /api/v1/shop` (P15)."""

    balance: int
    featured: list[ShopListingOut] = Field(default_factory=list)
    listings: list[ShopListingOut] = Field(default_factory=list)
    knowledge_items: list[KnowledgeItemOut] = Field(default_factory=list)
    shop_unlocked: bool = True
    unlock_level: int = 1


class PurchaseIn(EsquemaBase):
    """Cuerpo de `POST /api/v1/shop/purchase`."""

    listing_id: uuid.UUID
    expected_price: int | None = Field(
        default=None,
        ge=0,
        description="Precio que mostraba la app; si no coincide con el del servidor la compra falla.",
    )


class PurchaseRecordOut(EsquemaBase):
    """Orden de compra tal como queda auditada en `purchases`."""

    id: uuid.UUID
    listing_id: uuid.UUID
    item_id: uuid.UUID
    currency: Currency
    price: int
    status: PurchaseStatus
    created_at: dt.datetime
    reversed_at: dt.datetime | None = None


class UserItemOut(EsquemaBase):
    """Instancia entregada al inventario."""

    id: uuid.UUID
    item_id: uuid.UUID
    origin: ItemOrigin
    acquired_at: dt.datetime
    is_new: bool
    revoked_at: dt.datetime | None = None


class PurchaseOut(EsquemaBase):
    """Respuesta de la compra y del "deshacer"."""

    purchase: PurchaseRecordOut
    user_item: UserItemOut | None = None
    item: ItemOut | None = None
    balance_after: int
    avatar_layers: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Billetera
# ---------------------------------------------------------------------------


class GoldTransactionOut(EsquemaBase):
    """Movimiento del ledger de oro (append-only)."""

    id: uuid.UUID
    direction: LedgerDirection
    amount: int
    balance_after: int
    source: GoldSource | None = None
    sink: GoldSink | None = None
    reason_code: str
    local_date: dt.date
    created_at: dt.datetime


class PageGoldTransactionOut(EsquemaBase):
    """`Page<GoldTransactionOut>` del contrato."""

    items: list[GoldTransactionOut]
    page: PageOut


class WalletOut(EsquemaBase):
    """Respuesta de `GET /api/v1/wallet`."""

    balance: int
    lifetime_earned: int
    lifetime_spent: int
    currency: Currency = Currency.GOLD
    transactions: PageGoldTransactionOut


# ---------------------------------------------------------------------------
# Avatar y equipamiento
# ---------------------------------------------------------------------------


class AvatarLayerOut(EsquemaBase):
    """Capa del avatar ya resuelta y ordenada por z."""

    slot: str
    item_code: str
    key: str
    z: int
    offset: Any | None = None
    tint: str | None = None


class AvatarOut(EsquemaBase):
    """Rasgos, arquetipo, equipo y capas (`GET /api/v1/avatar`)."""

    traits: dict[str, Any] = Field(default_factory=dict)
    archetype: str
    equipment: dict[str, Any] = Field(default_factory=dict)
    layers: list[AvatarLayerOut] = Field(default_factory=list)
    etag: str


class AvatarEquipmentIn(EsquemaBase):
    """Cuerpo de `PUT /api/v1/avatar/equipment`: mapa atómico de ranuras."""

    equipment: dict[str, uuid.UUID | None] = Field(
        default_factory=dict,
        description='Mapa `{"weapon": "<user_item_id>", "cape": null}`; `null` desequipa.',
    )


EstadoInventario = Literal["owned", "locked", "equipped", "new", "unlocked"]


__all__ = [
    "AvatarEquipmentIn",
    "AvatarLayerOut",
    "AvatarOut",
    "EstadoInventario",
    "GoldTransactionOut",
    "InventoryItemOut",
    "ItemDetailOut",
    "ItemOut",
    "KnowledgeItemOut",
    "PageGoldTransactionOut",
    "PageInventoryOut",
    "PageOut",
    "PurchaseIn",
    "PurchaseOut",
    "PurchaseRecordOut",
    "RequirementProgressOut",
    "ShopListingOut",
    "ShopOut",
    "UserItemOut",
    "WalletOut",
]
