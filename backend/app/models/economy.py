"""Modelos del módulo `economy`: catálogo de ítems, inventario, billetera, tienda y compras.

Cubre las siete tablas del contrato §3.6: `items`, `item_requirements`, `user_items`,
`wallets`, `gold_transactions`, `shop_listings` y `purchases`.

Invariantes de dominio que este archivo materializa:

- Los ítems son **100 % cosméticos**: no existe ninguna columna de estadística de juego.
  El oro jamás compra XP, dominio ni contenido educativo.
- `gold_transactions` es un **ledger append-only** (solo `created_at`): nunca se hace
  `UPDATE` ni `DELETE`. `wallets.balance` es un saldo cacheado que se reconcilia de noche
  contra `SUM(créditos) - SUM(débitos)`.
- Toda operación que nace de una petición del cliente (crédito/débito de oro y compra)
  lleva `idempotency_key` con único por usuario: un reintento de red nunca duplica nada.
- `item_requirements` es el espejo normalizado del DSL guardado en `items.requirements`:
  el ítem se desbloquea si **algún** `group_index` tiene **todas** sus filas cumplidas
  (OR de ANDs, profundidad máxima 2).

Reglas de convención aplicadas (contrato §1.4):

- Claves foráneas siempre por texto (`"users.id"`); `relationship()` solo entre clases de
  este mismo archivo. No se importa ningún otro archivo de `app/models/` salvo `enums`.
- Los enums se persisten con el **nombre del miembro en MAYÚSCULAS**; por eso todo
  `server_default` y todo `CheckConstraint` se escribe con el nombre (`"GOLD"`,
  `origin <> 'KNOWLEDGE'`), nunca con el valor en minúsculas.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
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
    StreakKind,
)

__all__ = [
    "GoldTransaction",
    "Item",
    "ItemRequirement",
    "Purchase",
    "ShopListing",
    "UserItem",
    "Wallet",
]


# ---------------------------------------------------------------------------
# Catálogo de ítems
# ---------------------------------------------------------------------------


class Item(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ítem del catálogo: global, plantilla derivable o derivado de un usuario/área.

    Los ítems son el "currículum visual" del jugador: solo apariencia, exclusividad,
    requisitos y precio. **Ningún campo otorga bonificadores de juego** (decisión D19).
    Un ítem derivado (`template_code` no nulo) pertenece a un usuario concreto
    (`owner_user_id`) y está tematizado por un conocimiento (`knowledge_area_id`).
    """

    __tablename__ = "items"

    code: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    """Slug estable (`espada_del_sql`); en derivados `tpl_capa_maestro__<area_slug>`."""

    name: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    """Lore de 1–2 frases mostrado en la ficha del ítem."""

    slot: Mapped[ItemSlot] = mapped_column(
        sa.Enum(ItemSlot, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    rarity: Mapped[ItemRarity] = mapped_column(
        sa.Enum(ItemRarity, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    origin: Mapped[ItemOrigin] = mapped_column(
        sa.Enum(ItemOrigin, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    """Origen principal del ítem en el catálogo (etiqueta del currículum visual)."""

    requirements: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    """Árbol DSL `all`/`any` (profundidad máx. 2). Espejo normalizado en `item_requirements`."""

    requirement_facts: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    """Familias que referencia (`path`, `mastery`, `streak`…): filtra candidatos por evento.

    Se indexa con GIN `jsonb_path_ops` desde la migración de Alembic.
    """

    auto_grant: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    """`true`: al cumplirse los requisitos se otorga solo. `false`: solo habilita la compra."""

    render_manifest: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    """Capas, offsets, `suppresses_layers`, `two_handed`, `tint`, `icon` para el avatar."""

    icon_key: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    """Icono dedicado cuando el recorte automático de la capa no lee bien."""

    is_template: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    """Plantilla derivable por área; una plantilla no es equipable en sí misma."""

    template_code: Mapped[str | None] = mapped_column(sa.String(48), nullable=True)
    """Código de la plantilla de la que deriva este ítem (nulo si no es derivado)."""

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    """Dueño del derivado. Nulo en los ítems globales del catálogo."""

    knowledge_area_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("knowledge_areas.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Conocimiento que tematiza el derivado."""

    set_code: Mapped[str | None] = mapped_column(sa.String(48), nullable=True)
    """Conjunto al que pertenece (reservado, fase 2)."""

    visibility: Mapped[ItemVisibility] = mapped_column(
        sa.Enum(ItemVisibility, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ItemVisibility.PUBLIC,
        server_default=ItemVisibility.PUBLIC.name,
    )
    """Quién ve el ítem aunque siga bloqueado."""

    tier_required: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    """`premium` reservado; **prohibido** en ítems de origen `knowledge` (check de tabla)."""

    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    """Permite retirar un ítem del catálogo sin borrarlo ni romper inventarios."""

    available_from: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    available_to: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    catalog_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1")
    )
    """Versión del catálogo con la que se sembró o actualizó la fila."""

    # Relaciones internas del archivo (permitidas: misma unidad de compilación).
    requirement_rows: Mapped[list[ItemRequirement]] = relationship(
        "ItemRequirement",
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="(ItemRequirement.group_index, ItemRequirement.position)",
    )
    listings: Mapped[list[ShopListing]] = relationship(
        "ShopListing",
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        sa.UniqueConstraint("code"),
        sa.Index("ix_items_owner_user_id", "owner_user_id"),
        sa.Index("ix_items_is_active_visibility", "is_active", "visibility"),
        sa.Index("ix_items_origin_rarity", "origin", "rarity"),
        sa.CheckConstraint(
            "tier_required IS NULL OR origin <> 'KNOWLEDGE'",
            name="knowledge_not_premium",
        ),
    )


class ItemRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Una condición de desbloqueo de un ítem, normalizada desde `items.requirements`.

    Semántica de evaluación: el ítem está desbloqueado si existe algún `group_index`
    cuyas filas se cumplan **todas** (OR de ANDs). Tener el DSL también en filas permite
    evaluar por SQL y **explicar** el progreso ("Dominio de BigQuery: 62 / 80 %") sin
    recorrer JSON en Python.
    """

    __tablename__ = "item_requirements"

    item_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_index: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    """Grupo OR: las filas del mismo grupo se combinan con AND."""

    position: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    """Orden de la condición dentro de su grupo (estabiliza la explicación mostrada)."""

    requirement_type: Mapped[RequirementType] = mapped_column(
        sa.Enum(RequirementType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    knowledge_area_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("knowledge_areas.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Conocimiento concreto exigido, cuando la condición apunta a un área ya existente."""

    area_slug: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    """`self` en plantillas (se resuelve al derivar) o el slug canónico del área."""

    target_value: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 2), nullable=True)
    """Umbral continuo: dominio o puntaje de evaluación en escala 0.00–100.00."""

    target_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    """Umbral discreto: áreas dominadas, evaluaciones, lecciones o días de racha."""

    achievement_code: Mapped[str | None] = mapped_column(sa.String(48), nullable=True)
    streak_kind: Mapped[StreakKind | None] = mapped_column(
        sa.Enum(StreakKind, native_enum=False, length=48, validate_strings=True),
        nullable=True,
    )
    """`current` o `best`; los ítems de racha usan `best` para no quitarse al romperse."""

    window_from: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    window_to: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    label_template: Mapped[str | None] = mapped_column(sa.String(160), nullable=True)
    """Plantilla del texto explicativo: "Dominio de {area}: {current} / {target} %"."""

    item: Mapped[Item] = relationship("Item", back_populates="requirement_rows")

    __table_args__ = (
        sa.Index("ix_item_requirements_item_id", "item_id"),
        sa.Index("ix_item_requirements_requirement_type", "requirement_type"),
    )


# ---------------------------------------------------------------------------
# Inventario del usuario
# ---------------------------------------------------------------------------


class UserItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Instancia poseída de un ítem. Único por `(user_id, item_id)`: no se acumulan.

    El otorgamiento automático se hace con `INSERT … ON CONFLICT DO NOTHING`, de modo que
    reevaluar los requisitos es idempotente. Nunca se borra físicamente una instancia:
    una revocación por soporte o fraude se marca en `revoked_at`.
    """

    __tablename__ = "user_items"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    """Referencia al catálogo: RESTRICT impide borrar un ítem que alguien posee."""

    acquired_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    """Fecha de adquisición mostrada en la ficha del inventario."""

    origin: Mapped[ItemOrigin] = mapped_column(
        sa.Enum(ItemOrigin, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    """Origen **real** de esta instancia; puede diferir del origen del catálogo."""

    source_ref: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    """Prueba del otorgamiento: `{purchase_id}`, `{achievement_code}`, `{streak_days}`
    o `{trigger_event_id, requirements_snapshot}`."""

    is_new: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    """Insignia "nuevo" en la mochila hasta que el usuario abre la ficha."""

    revoked_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    revoke_reason: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("user_id", "item_id"),
        sa.Index("ix_user_items_user_id_acquired_at", "user_id", "acquired_at"),
    )


# ---------------------------------------------------------------------------
# Billetera y ledger de oro
# ---------------------------------------------------------------------------


class Wallet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Saldo cacheado de una moneda para un usuario.

    No es la fuente de verdad: el ledger `gold_transactions` lo es. Esta fila existe para
    leer el saldo en O(1) y para serializar las compras: toda compra hace
    `SELECT … FOR UPDATE` sobre ella antes de debitar. Un trabajo nocturno reconcilia
    `balance` contra `SUM(créditos) - SUM(débitos)`.
    """

    __tablename__ = "wallets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    currency: Mapped[Currency] = mapped_column(
        sa.Enum(Currency, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=Currency.GOLD,
        server_default=Currency.GOLD.name,
    )
    """Moneda de la billetera; `gems` está reservado y desactivado en el MVP."""

    balance: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    lifetime_earned: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    """Acumulado histórico de créditos; alimenta logros de colección y analítica."""

    lifetime_spent: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    """Contador de versiones para bloqueo optimista además del bloqueo pesimista."""

    __table_args__ = (
        sa.UniqueConstraint("user_id", "currency"),
        sa.CheckConstraint("balance >= 0", name="balance_non_negative"),
    )


class GoldTransaction(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Ledger **append-only** de oro: una fila por crédito o débito. Nunca se modifica.

    Cada fila guarda su dimensión (`source` en créditos, `sink` en débitos), el saldo
    resultante (`balance_after`), la versión de configuración aplicada y la fecha local
    del usuario, que es la que rige los topes diarios. La reversión de una compra no
    borra nada: inserta un crédito con `source = purchase_reversal`.
    """

    __tablename__ = "gold_transactions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    currency: Mapped[Currency] = mapped_column(
        sa.Enum(Currency, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=Currency.GOLD,
        server_default=Currency.GOLD.name,
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("domain_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Evento de dominio que originó la transacción (auditoría, opcional)."""

    direction: Mapped[LedgerDirection] = mapped_column(
        sa.Enum(LedgerDirection, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    source: Mapped[GoldSource | None] = mapped_column(
        sa.Enum(GoldSource, native_enum=False, length=48, validate_strings=True),
        nullable=True,
    )
    """Obligatoria en `credit` y prohibida en `debit` (check `direction_dimension`)."""

    sink: Mapped[GoldSink | None] = mapped_column(
        sa.Enum(GoldSink, native_enum=False, length=48, validate_strings=True),
        nullable=True,
    )
    """Obligatoria en `debit` y prohibida en `credit` (check `direction_dimension`)."""

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True
    )
    """Id del hecho que la generó (lección, misión, compra…). Sin FK: es polimórfico."""

    amount: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    """Importe siempre positivo; el signo lo aporta `direction`."""

    balance_after: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    """Saldo de la billetera justo después de aplicar esta fila."""

    reason_code: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    """`first_completion`, `daily_softcap_50`, `purchase`, `reversal`, `admin_adjustment`…"""

    config_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    """Versión de `game_configs` con la que se calculó la recompensa."""

    local_date: Mapped[dt.date] = mapped_column(sa.Date, nullable=False)
    """Fecha en la zona horaria del usuario: unidad de los topes diarios de oro."""

    idempotency_key: Mapped[str] = mapped_column(sa.String(120), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint("user_id", "idempotency_key"),
        sa.Index("ix_gold_transactions_user_id_created_at", "user_id", "created_at"),
        sa.Index("ix_gold_transactions_user_id_local_date", "user_id", "local_date"),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.CheckConstraint("balance_after >= 0", name="balance_non_negative"),
        sa.CheckConstraint(
            "(direction = 'CREDIT' AND source IS NOT NULL AND sink IS NULL)"
            " OR (direction = 'DEBIT' AND sink IS NOT NULL AND source IS NULL)",
            name="direction_dimension",
        ),
    )


# ---------------------------------------------------------------------------
# Tienda
# ---------------------------------------------------------------------------


class ShopListing(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Oferta de un ítem en la tienda: precio, moneda, nivel mínimo y ventana.

    **El precio no vive en `items`**: un mismo ítem puede ofertarse a distinto precio en
    distintos momentos, y retirarse de la tienda (`is_active = false`) sin tocar el
    catálogo ni los inventarios ya entregados.
    """

    __tablename__ = "shop_listings"

    item_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
    )
    currency: Mapped[Currency] = mapped_column(
        sa.Enum(Currency, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=Currency.GOLD,
        server_default=Currency.GOLD.name,
    )
    price: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    """Precio cobrado por el servidor; por defecto el de la rareza del ítem."""

    min_level: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1")
    )
    """Nivel mínimo del personaje; deriva de la rareza y es sobreescribible por ítem."""

    is_featured: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    """Destacado en el escaparate (2–4 simultáneos)."""

    featured_order: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    available_from: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    available_to: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )

    item: Mapped[Item] = relationship("Item", back_populates="listings")

    __table_args__ = (
        sa.Index("ix_shop_listings_is_active_is_featured", "is_active", "is_featured"),
        sa.CheckConstraint("price > 0", name="price_positive"),
    )


class Purchase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Orden de compra: débito de oro, entrega de la instancia y rastro de auditoría.

    Se resuelve en una sola transacción SQL con la billetera bloqueada
    (`SELECT … FOR UPDATE`). El "deshacer" dentro de la ventana de 60 s no borra la orden:
    la pasa a `reversed`, apunta `reversal_transaction_id` al crédito compensatorio y
    sella `reversed_at`. `item_id` está desnormalizado para que el historial sobreviva a
    cambios del listado.
    """

    __tablename__ = "purchases"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("shop_listings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    """Ítem comprado, desnormalizado desde el listado para conservar el historial."""

    currency: Mapped[Currency] = mapped_column(
        sa.Enum(Currency, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=Currency.GOLD,
        server_default=Currency.GOLD.name,
    )
    price: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    """Precio efectivamente cobrado: el del servidor, jamás el que envíe el cliente."""

    status: Mapped[PurchaseStatus] = mapped_column(
        sa.Enum(PurchaseStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=PurchaseStatus.COMPLETED,
        server_default=PurchaseStatus.COMPLETED.name,
    )
    gold_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("gold_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Débito del ledger que pagó esta compra."""

    user_item_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("user_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Instancia entregada al inventario del comprador."""

    reversal_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("gold_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Crédito compensatorio emitido al deshacer la compra."""

    reversed_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    """Clave enviada por el cliente: un reintento devuelve la misma compra, no otra."""

    __table_args__ = (
        sa.UniqueConstraint("user_id", "idempotency_key"),
        sa.Index("ix_purchases_user_id_created_at", "user_id", "created_at"),
    )
