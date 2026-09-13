"""Tienda: catálogo, precios por rareza y compra atómica (contrato §6.3, §7.3).

Invariantes que este archivo hace cumplir:

- **El oro nunca compra ventaja educativa.** Los ítems son 100 % cosméticos: antes de
  cobrar se comprueba que el ítem no declare ningún efecto de juego
  (:func:`validar_solo_cosmetico`) y que su origen no sea de conocimiento (esos se ganan
  aprendiendo, no se venden).
- **El precio lo pone el servidor.** `shop_listings.price` manda; `expected_price` del
  cliente solo sirve para detectar que la app mostraba un precio viejo
  (409 `PRICE_CHANGED`).
- **La compra es una sola transacción** con la billetera bloqueada: debita el ledger,
  crea la instancia en `user_items`, escribe la orden en `purchases` y emite
  `GOLD_SPENT` e `ITEM_ACQUIRED`. Si algo falla, no queda nada a medias.
- **No se compra dos veces el mismo cosmético** (409 `ALREADY_OWNED`) ni se compra lo que
  no se ha desbloqueado (409 `REQUIREMENTS_NOT_MET`).
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import AteneaError, Conflict, NotFound
from app.core.time import utcnow
from app.models.economy import Item, Purchase, ShopListing, UserItem
from app.models.enums import (
    Currency,
    GoldSink,
    GoldSource,
    ItemOrigin,
    ItemRarity,
    ItemSlot,
    ItemVisibility,
    PurchaseStatus,
)
from app.models.identity import Character
from app.modules.economy import inventario as inv
from app.modules.economy.equipamiento import desequipar, equipados, personaje_de
from app.modules.economy.monedero import (
    gastar_oro,
    obtener_billetera,
    otorgar_oro,
    saldo,
    valor_config,
)
from app.modules.economy.requisitos import evaluar_item, otorgar_item, requisitos_de

# --- Claves de configuración usadas por la tienda (§5.4) -------------------
CLAVE_PRECIO_POR_RAREZA = "shop.price_by_rarity"
CLAVE_NIVEL_MIN_POR_RAREZA = "shop.min_level_by_rarity"
CLAVE_NIVEL_DESBLOQUEO = "shop.unlock_level"
CLAVE_DESTACADOS_MAX = "shop.featured_max"
CLAVE_RAREZAS_VENDIBLES = "shop.sellable_rarities"
CLAVE_SEGUNDOS_REVERSION = "shop.purchase_reversal_seconds"

#: Motivos (`reason_code`) del ledger que produce la tienda (§3.6).
MOTIVO_COMPRA = "purchase"
MOTIVO_REVERSION = "reversal"

#: Claves que delatarían un efecto de juego en el manifiesto de un ítem.
#: Ningún ítem puede otorgar ventaja educativa (D19): son solo apariencia.
CLAVES_DE_VENTAJA: frozenset[str] = frozenset(
    {
        "stats",
        "stat",
        "bonus",
        "bonuses",
        "buff",
        "buffs",
        "boost",
        "multiplier",
        "xp_multiplier",
        "gold_multiplier",
        "mastery_bonus",
        "xp_bonus",
        "gold_bonus",
        "advantage",
        "power",
        "effects",
        "modifiers",
    }
)


# ---------------------------------------------------------------------------
# Errores de la tienda
# ---------------------------------------------------------------------------


class YaPoseido(Conflict):
    """409 `ALREADY_OWNED` · el usuario ya tiene ese cosmético."""

    code = "ALREADY_OWNED"


class RequisitosNoCumplidos(Conflict):
    """409 `REQUIREMENTS_NOT_MET` · faltan requisitos de desbloqueo o nivel mínimo."""

    code = "REQUIREMENTS_NOT_MET"


class PrecioCambiado(Conflict):
    """409 `PRICE_CHANGED` · el precio del servidor no coincide con `expected_price`."""

    code = "PRICE_CHANGED"


class NoDisponible(Conflict):
    """409 `UNAVAILABLE` · el listado no está activo, está fuera de ventana o no es vendible."""

    code = "UNAVAILABLE"


class ClaveIdempotenciaEnConflicto(Conflict):
    """409 `IDEMPOTENCY_KEY_CONFLICT` · la misma clave se usó con otro cuerpo (§8.3)."""

    code = "IDEMPOTENCY_KEY_CONFLICT"


# ---------------------------------------------------------------------------
# Precios y niveles por rareza
# ---------------------------------------------------------------------------


def precio_por_rareza(db: Session, rarity: ItemRarity) -> int | None:
    """Precio de catálogo de una rareza (`shop.price_by_rarity`).

    `None` significa "no se vende" (es el caso de `mythic` en el MVP).
    """
    mapa = valor_config(db, CLAVE_PRECIO_POR_RAREZA) or {}
    valor = mapa.get(rarity.value)
    return None if valor is None else int(valor)


def nivel_minimo_por_rareza(db: Session, rarity: ItemRarity) -> int:
    """Nivel mínimo sugerido por rareza (`shop.min_level_by_rarity`)."""
    mapa = valor_config(db, CLAVE_NIVEL_MIN_POR_RAREZA) or {}
    valor = mapa.get(rarity.value)
    return int(valor) if valor is not None else 1


def rarezas_vendibles(db: Session) -> tuple[ItemRarity, ...]:
    """Rarezas que se pueden comprar con oro (`shop.sellable_rarities`)."""
    crudo = valor_config(db, CLAVE_RAREZAS_VENDIBLES) or []
    vendibles: list[ItemRarity] = []
    for nombre in crudo:
        try:
            vendibles.append(ItemRarity(str(nombre)))
        except ValueError:  # pragma: no cover - configuración mal sembrada
            continue
    return tuple(vendibles)


def precio_vigente(db: Session, listing: ShopListing) -> int:  # noqa: ARG001 - firma fijada por quien llama
    """Precio que cobra el servidor: el del listado (que la semilla fija por rareza)."""
    return int(listing.price)


# ---------------------------------------------------------------------------
# Integridad: solo cosmética
# ---------------------------------------------------------------------------


def _tiene_ventaja(valor: Any, profundidad: int = 0) -> bool:
    """Busca recursivamente claves de efecto de juego dentro de un JSON del ítem."""
    if profundidad > 4:
        return False
    if isinstance(valor, dict):
        for clave, anidado in valor.items():
            if str(clave).lower() in CLAVES_DE_VENTAJA:
                return True
            if _tiene_ventaja(anidado, profundidad + 1):
                return True
    elif isinstance(valor, list):
        return any(_tiene_ventaja(elemento, profundidad + 1) for elemento in valor)
    return False


def es_cosmetico(item: Item) -> bool:
    """`True` si el ítem es puramente cosmético (decisión D19 del contrato).

    `items` no tiene columnas de estadística, así que la única vía de contrabando sería
    colar un efecto dentro de `render_manifest`: eso es lo que se audita aquí.
    """
    return not _tiene_ventaja(item.render_manifest)


def validar_solo_cosmetico(item: Item) -> None:
    """Rechaza con 409 `UNAVAILABLE` cualquier ítem que declare un efecto de juego."""
    if not es_cosmetico(item):
        raise NoDisponible(
            "Este objeto no está disponible en la tienda.",
            details={"item_code": item.code, "reason": "non_cosmetic_item"},
        )


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------


@dataclass
class OfertaTienda:
    """Un listado de la tienda con todo lo que la app necesita para pintarlo."""

    listing: ShopListing
    item: Item
    price: int
    min_level: int
    owned: bool
    locked: bool
    can_afford: bool
    is_featured: bool
    requirements: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CatalogoTienda:
    """Respuesta de `GET /api/v1/shop` (§7.3)."""

    balance: int
    featured: list[OfertaTienda]
    listings: list[OfertaTienda]
    knowledge_items: list[dict[str, Any]]
    shop_unlocked: bool
    unlock_level: int


def _listado_disponible(momento: dt.datetime):
    """Cláusula de listado activo y dentro de su ventana temporal."""
    return sa.and_(
        ShopListing.is_active.is_(True),
        sa.or_(ShopListing.available_from.is_(None), ShopListing.available_from <= momento),
        sa.or_(ShopListing.available_to.is_(None), ShopListing.available_to >= momento),
        Item.is_active.is_(True),
        Item.is_template.is_(False),
        Item.visibility != ItemVisibility.HIDDEN,
        sa.or_(Item.available_from.is_(None), Item.available_from <= momento),
        sa.or_(Item.available_to.is_(None), Item.available_to >= momento),
    )


def catalogo(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    slot: ItemSlot | None = None,
    rarity: ItemRarity | None = None,
    solo_asequibles: bool = False,
    momento: dt.datetime | None = None,
) -> CatalogoTienda:
    """Catálogo activo, destacados, saldo y sección "Se ganan aprendiendo" (P15)."""
    instante = momento or utcnow()
    balance = saldo(db, usuario_id)
    vendibles = rarezas_vendibles(db)
    nivel_desbloqueo = int(valor_config(db, CLAVE_NIVEL_DESBLOQUEO))
    maximo_destacados = int(valor_config(db, CLAVE_DESTACADOS_MAX))

    nivel = int(
        db.execute(
            sa.select(Character.level).where(Character.user_id == usuario_id)
        ).scalar_one_or_none()
        or 0
    )

    consulta = (
        sa.select(ShopListing, Item)
        .join(Item, Item.id == ShopListing.item_id)
        .where(_listado_disponible(instante), ShopListing.currency == Currency.GOLD)
    )
    if slot is not None:
        consulta = consulta.where(Item.slot == slot)
    if rarity is not None:
        consulta = consulta.where(Item.rarity == rarity)
    if vendibles:
        consulta = consulta.where(Item.rarity.in_(vendibles))
    consulta = consulta.order_by(
        ShopListing.is_featured.desc(), ShopListing.featured_order, Item.code
    )

    poseidos = set(db.execute(
            sa.select(UserItem.item_id).where(
                UserItem.user_id == usuario_id, UserItem.revoked_at.is_(None)
            )
        ).scalars())

    ofertas: list[OfertaTienda] = []
    for listing, item in db.execute(consulta).all():
        if not es_cosmetico(item):
            continue
        precio = precio_vigente(db, listing)
        if solo_asequibles and precio > balance:
            continue
        evaluacion = evaluar_item(db, usuario_id, item)
        ofertas.append(
            OfertaTienda(
                listing=listing,
                item=item,
                price=precio,
                min_level=int(listing.min_level),
                owned=item.id in poseidos,
                locked=not evaluacion.desbloqueado or nivel < int(listing.min_level),
                can_afford=balance >= precio,
                is_featured=bool(listing.is_featured),
                requirements=[c.as_dict() for c in evaluacion.condiciones_visibles],
            )
        )

    destacados = [oferta for oferta in ofertas if oferta.is_featured][:maximo_destacados]

    # "Se ganan aprendiendo": ítems de conocimiento, que jamás están a la venta.
    del_conocimiento: list[dict[str, Any]] = []
    consulta_conocimiento = sa.select(Item).where(
        Item.is_active.is_(True),
        Item.is_template.is_(False),
        Item.origin == ItemOrigin.KNOWLEDGE,
        Item.visibility != ItemVisibility.HIDDEN,
        sa.or_(Item.owner_user_id.is_(None), Item.owner_user_id == usuario_id),
    )
    for item in db.execute(consulta_conocimiento.order_by(Item.code)).scalars():
        evaluacion = evaluar_item(db, usuario_id, item)
        del_conocimiento.append(
            {
                "item_id": str(item.id),
                "item_code": item.code,
                "name": item.name,
                "slot": item.slot.value,
                "rarity": item.rarity.value,
                "owned": item.id in poseidos,
                "unlocked": evaluacion.desbloqueado,
                "requirements": [c.as_dict() for c in evaluacion.condiciones_visibles],
            }
        )

    return CatalogoTienda(
        balance=balance,
        featured=destacados,
        listings=ofertas,
        knowledge_items=del_conocimiento,
        shop_unlocked=nivel >= nivel_desbloqueo,
        unlock_level=nivel_desbloqueo,
    )


# ---------------------------------------------------------------------------
# Compra
# ---------------------------------------------------------------------------


@dataclass
class ResultadoCompra:
    """Resultado de `POST /api/v1/shop/purchase`."""

    purchase: Purchase
    user_item: UserItem
    item: Item
    balance_after: int
    repetida: bool = False


def _listado(db: Session, listing_id: uuid.UUID, momento: dt.datetime) -> tuple[ShopListing, Item]:
    """Carga el listado y su ítem, validando actividad y ventana temporal."""
    fila = db.execute(
        sa.select(ShopListing, Item)
        .join(Item, Item.id == ShopListing.item_id)
        .where(ShopListing.id == listing_id)
    ).one_or_none()
    if fila is None:
        raise NotFound(details={"listing_id": str(listing_id)})

    listing, item = fila
    if not listing.is_active or not item.is_active or item.is_template:
        raise NoDisponible(details={"listing_id": str(listing_id)})
    if listing.available_from is not None and listing.available_from > momento:
        raise NoDisponible(details={"listing_id": str(listing_id), "reason": "not_yet"})
    if listing.available_to is not None and listing.available_to < momento:
        raise NoDisponible(details={"listing_id": str(listing_id), "reason": "expired"})
    if item.available_from is not None and item.available_from > momento:
        raise NoDisponible(details={"item_code": item.code, "reason": "not_yet"})
    if item.available_to is not None and item.available_to < momento:
        raise NoDisponible(details={"item_code": item.code, "reason": "expired"})
    if listing.currency is not Currency.GOLD:
        raise NoDisponible(details={"currency": listing.currency.value})
    return listing, item


def comprar(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    listing_id: uuid.UUID,
    idempotency_key: str,
    expected_price: int | None = None,
    momento: dt.datetime | None = None,
) -> ResultadoCompra:
    """Compra atómica de un cosmético (contrato §6.3).

    Orden de validación: idempotencia → listado disponible → solo cosmético → rareza
    vendible → tienda desbloqueada y nivel mínimo → requisitos de desbloqueo → no
    poseído → precio esperado → saldo suficiente. Recién entonces se mueve el oro.
    """
    instante = momento or utcnow()

    # 1. Idempotencia (§8.3): la misma clave devuelve la misma compra, sin efectos.
    previa = db.execute(
        sa.select(Purchase).where(
            Purchase.user_id == usuario_id, Purchase.idempotency_key == idempotency_key
        )
    ).scalar_one_or_none()
    if previa is not None:
        if previa.listing_id != listing_id:
            raise ClaveIdempotenciaEnConflicto(
                details={"idempotency_key": idempotency_key}
            )
        item_previo = db.get(Item, previa.item_id)
        user_item_previo = db.execute(
            sa.select(UserItem).where(UserItem.id == previa.user_item_id)
        ).scalar_one_or_none()
        return ResultadoCompra(
            purchase=previa,
            user_item=user_item_previo,
            item=item_previo,
            balance_after=saldo(db, usuario_id),
            repetida=True,
        )

    listing, item = _listado(db, listing_id, instante)
    validar_solo_cosmetico(item)

    if item.origin is ItemOrigin.KNOWLEDGE:
        raise NoDisponible(
            "Este objeto se gana aprendiendo, no se compra.",
            details={"item_code": item.code, "reason": "knowledge_item"},
        )

    vendibles = rarezas_vendibles(db)
    if vendibles and item.rarity not in vendibles:
        raise NoDisponible(
            details={"item_code": item.code, "rarity": item.rarity.value},
        )
    if precio_por_rareza(db, item.rarity) is None:
        raise NoDisponible(
            details={"item_code": item.code, "rarity": item.rarity.value},
        )

    personaje = personaje_de(db, usuario_id)
    nivel = int(personaje.level)
    nivel_desbloqueo = int(valor_config(db, CLAVE_NIVEL_DESBLOQUEO))
    if nivel < nivel_desbloqueo:
        raise RequisitosNoCumplidos(
            "La tienda se abre un poco más adelante en tu aventura.",
            details={"level": nivel, "required_level": nivel_desbloqueo},
        )
    if nivel < int(listing.min_level):
        raise RequisitosNoCumplidos(
            "Todavía te falta nivel para llevarte esto.",
            details={"level": nivel, "required_level": int(listing.min_level)},
        )

    filas_requisito = requisitos_de(db, item.id)
    evaluacion = evaluar_item(db, usuario_id, item, requisitos=filas_requisito)
    if not evaluacion.desbloqueado:
        raise RequisitosNoCumplidos(
            details={
                "item_code": item.code,
                "requirements": [c.as_dict() for c in evaluacion.condiciones_visibles],
            }
        )

    if inv.posee(db, usuario_id, item.id):
        raise YaPoseido(details={"item_code": item.code})

    precio = precio_vigente(db, listing)
    if expected_price is not None and int(expected_price) != precio:
        raise PrecioCambiado(
            details={"expected_price": int(expected_price), "price": precio}
        )

    disponible = obtener_billetera(db, usuario_id, bloquear=True).balance
    if disponible < precio:
        raise AteneaError(
            code="INSUFFICIENT_GOLD",
            details={
                "required": precio,
                "balance": int(disponible),
                "missing": precio - int(disponible),
            },
        )

    purchase_id = uuid.uuid4()

    with db.begin_nested():
        transaccion = gastar_oro(
            db,
            usuario_id,
            amount=precio,
            sink=GoldSink.PURCHASE,
            reason_code=MOTIVO_COMPRA,
            idempotency_key=f"purchase:{idempotency_key}",
            source_id=purchase_id,
            momento=instante,
            payload_extra={"purchase_id": str(purchase_id)},
        )

        otorgamiento = otorgar_item(
            db,
            usuario_id,
            item,
            origin=ItemOrigin.SHOP,
            source_ref={"purchase_id": str(purchase_id)},
            unlock_reason=None,
            momento=instante,
        )

        compra = Purchase(
            id=purchase_id,
            user_id=usuario_id,
            listing_id=listing.id,
            item_id=item.id,
            currency=Currency.GOLD,
            price=precio,
            status=PurchaseStatus.COMPLETED,
            gold_transaction_id=transaccion.id,
            user_item_id=otorgamiento.user_item.id,
            idempotency_key=idempotency_key,
        )
        db.add(compra)
        db.flush()

    return ResultadoCompra(
        purchase=compra,
        user_item=otorgamiento.user_item,
        item=item,
        balance_after=int(transaccion.balance_after),
    )


# ---------------------------------------------------------------------------
# Deshacer una compra
# ---------------------------------------------------------------------------


def revertir_compra(
    db: Session,
    usuario_id: uuid.UUID,
    purchase_id: uuid.UUID,
    *,
    momento: dt.datetime | None = None,
) -> ResultadoCompra:
    """"Deshacer" dentro de `shop.purchase_reversal_seconds` (60 s por defecto).

    No borra nada: la orden pasa a `reversed`, se emite un crédito compensatorio
    (`source = purchase_reversal`) y la instancia se marca revocada y se desequipa.
    """
    instante = momento or utcnow()
    compra = db.execute(
        sa.select(Purchase).where(
            Purchase.id == purchase_id, Purchase.user_id == usuario_id
        )
    ).scalar_one_or_none()
    if compra is None:
        raise NotFound(details={"purchase_id": str(purchase_id)})

    item = db.get(Item, compra.item_id)

    if compra.status is PurchaseStatus.REVERSED:
        user_item = db.execute(
            sa.select(UserItem).where(UserItem.id == compra.user_item_id)
        ).scalar_one_or_none()
        return ResultadoCompra(
            purchase=compra,
            user_item=user_item,
            item=item,
            balance_after=saldo(db, usuario_id),
            repetida=True,
        )

    ventana = int(valor_config(db, CLAVE_SEGUNDOS_REVERSION))
    transcurrido = (instante - compra.created_at).total_seconds()
    if transcurrido > ventana:
        raise NoDisponible(
            "Ya pasó el tiempo para deshacer esta compra.",
            details={"elapsed_seconds": int(transcurrido), "window_seconds": ventana},
        )

    with db.begin_nested():
        credito = otorgar_oro(
            db,
            usuario_id,
            amount=int(compra.price),
            source=GoldSource.PURCHASE_REVERSAL,
            reason_code=MOTIVO_REVERSION,
            idempotency_key=f"purchase-reversal:{compra.id}",
            source_id=compra.id,
            momento=instante,
        )

        user_item = db.execute(
            sa.select(UserItem).where(UserItem.id == compra.user_item_id)
        ).scalar_one_or_none()
        if user_item is not None:
            for slot, fila in equipados(db, personaje_de(db, usuario_id).id).items():
                if fila.user_item_id == user_item.id:
                    desequipar(db, usuario_id, slot, momento=instante)
            user_item.revoked_at = instante
            user_item.revoke_reason = "Compra deshecha por el usuario"

        compra.status = PurchaseStatus.REVERSED
        compra.reversal_transaction_id = credito.id
        compra.reversed_at = instante
        db.flush()

    return ResultadoCompra(
        purchase=compra,
        user_item=user_item,
        item=item,
        balance_after=int(credito.balance_after),
    )


__all__ = [
    "CLAVES_DE_VENTAJA",
    "CLAVE_DESTACADOS_MAX",
    "CLAVE_NIVEL_DESBLOQUEO",
    "CLAVE_NIVEL_MIN_POR_RAREZA",
    "CLAVE_PRECIO_POR_RAREZA",
    "CLAVE_RAREZAS_VENDIBLES",
    "CLAVE_SEGUNDOS_REVERSION",
    "MOTIVO_COMPRA",
    "MOTIVO_REVERSION",
    "CatalogoTienda",
    "ClaveIdempotenciaEnConflicto",
    "NoDisponible",
    "OfertaTienda",
    "PrecioCambiado",
    "RequisitosNoCumplidos",
    "ResultadoCompra",
    "YaPoseido",
    "catalogo",
    "comprar",
    "es_cosmetico",
    "nivel_minimo_por_rareza",
    "precio_por_rareza",
    "precio_vigente",
    "rarezas_vendibles",
    "revertir_compra",
    "validar_solo_cosmetico",
]
