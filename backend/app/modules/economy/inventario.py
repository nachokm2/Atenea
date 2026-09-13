"""Inventario del usuario: listado con filtros, ficha del ítem y ítems bloqueados.

La mochila (P16) muestra **lo poseído y lo bloqueado visible**: un ítem que aún no se
tiene aparece con su requisito explicado ("Dominio de BigQuery: 62 / 80 %"), porque el
inventario es el "currículum visual" del jugador y enseñar la meta es parte del diseño.

Visibilidad de un ítem no poseído (`items.visibility`):

- `public` → se ve bloqueado en la mochila y en la tienda.
- `owner`  → solo lo ve quien ya lo posee (sorpresa).
- `hidden` → nunca se lista mientras no se posea.

La paginación sigue §8.2: cursor opaco `base64(json)` con la última clave de orden,
nunca `OFFSET`.

TODO(A1): cuando exista `app/core/pagination.py`, sustituir `codificar_cursor` /
`decodificar_cursor` por el sobre `Page` común del núcleo.
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import json
import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.core.time import isoformat_z, user_local_date, utcnow
from app.models.economy import Item, UserItem
from app.models.enums import EventType, ItemOrigin, ItemRarity, ItemSlot, ItemVisibility
from app.models.identity import Character, EquippedItem
from app.modules.economy.monedero import recortar_clave, registrar_evento
from app.modules.economy.requisitos import (
    HechosUsuario,
    evaluar_item,
    requisitos_de,
)

#: Estados por los que puede filtrar la mochila (`state` de §7.2).
ESTADOS_INVENTARIO: tuple[str, ...] = ("owned", "locked", "equipped", "new", "unlocked")

#: Tamaño de página por defecto y máximo (§8.2).
LIMITE_POR_DEFECTO = 20
LIMITE_MAXIMO = 100


# ---------------------------------------------------------------------------
# Cursor opaco (§8.2)
# ---------------------------------------------------------------------------


def codificar_cursor(clave: dict[str, Any]) -> str:
    """Codifica la última clave de orden como cursor opaco `base64(json)`."""
    crudo = json.dumps(clave, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(crudo).decode("ascii")


def decodificar_cursor(cursor: str | None) -> dict[str, Any] | None:
    """Decodifica un cursor; un cursor corrupto es un error de validación, no un 500."""
    if not cursor:
        return None
    try:
        relleno = "=" * (-len(cursor) % 4)
        crudo = base64.urlsafe_b64decode(cursor + relleno)
        clave = json.loads(crudo.decode("utf-8"))
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValidationFailed(
            "El cursor de paginación no es válido.",
            field_errors=[{"field": "cursor", "message": "Cursor ilegible."}],
        ) from exc
    if not isinstance(clave, dict):
        raise ValidationFailed(
            "El cursor de paginación no es válido.",
            field_errors=[{"field": "cursor", "message": "Cursor ilegible."}],
        )
    return clave


def normalizar_limite(limit: int | None) -> int:
    """Aplica el límite por defecto (20) y el máximo (100) del contrato."""
    if limit is None:
        return LIMITE_POR_DEFECTO
    return max(1, min(int(limit), LIMITE_MAXIMO))


# ---------------------------------------------------------------------------
# Filas del inventario
# ---------------------------------------------------------------------------


@dataclass
class FilaInventario:
    """Un ítem tal como lo ve la mochila del usuario."""

    item: Item
    owned: bool
    locked: bool
    is_new: bool
    equipped: bool
    user_item_id: uuid.UUID | None
    acquired_at: dt.datetime | None
    equipped_slot: ItemSlot | None
    requirements: list[dict[str, Any]]


@dataclass
class PaginaInventario:
    """Sobre de paginación de §8.2 aplicado al inventario."""

    items: list[FilaInventario]
    limit: int
    next_cursor: str | None
    has_more: bool
    total: int | None


def _visible_sin_poseer(momento: dt.datetime, usuario_id: uuid.UUID):
    """Cláusula de los ítems que se muestran aunque el usuario no los tenga."""
    return sa.and_(
        Item.is_active.is_(True),
        Item.is_template.is_(False),
        Item.visibility != ItemVisibility.HIDDEN,
        sa.or_(Item.owner_user_id.is_(None), Item.owner_user_id == usuario_id),
        sa.or_(Item.available_from.is_(None), Item.available_from <= momento),
        sa.or_(Item.available_to.is_(None), Item.available_to >= momento),
    )


def listar_inventario(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    slot: ItemSlot | None = None,
    rarity: ItemRarity | None = None,
    state: str | None = None,
    origin: ItemOrigin | None = None,
    limit: int | None = None,
    cursor: str | None = None,
    momento: dt.datetime | None = None,
) -> PaginaInventario:
    """Lista la mochila: poseídos + bloqueados visibles, con progreso de requisitos.

    Filtros del contrato: `slot`, `rarity`, `state` y `origin`. El orden es determinista
    y termina en `id` para que la paginación por cursor no duplique ni salte filas.
    """
    if state is not None and state not in ESTADOS_INVENTARIO:
        raise ValidationFailed(
            "El filtro de estado no es válido.",
            field_errors=[
                {"field": "state", "message": f"Valores admitidos: {', '.join(ESTADOS_INVENTARIO)}."}
            ],
        )
    instante = momento or utcnow()
    tope = normalizar_limite(limit)

    equipado = (
        sa.select(EquippedItem.user_item_id, EquippedItem.slot.label("slot_equipado"))
        .join(Character, Character.id == EquippedItem.character_id)
        .where(Character.user_id == usuario_id)
        .subquery()
    )

    consulta = (
        sa.select(Item, UserItem, equipado.c.slot_equipado)
        .select_from(Item)
        .outerjoin(
            UserItem,
            sa.and_(UserItem.item_id == Item.id, UserItem.user_id == usuario_id),
        )
        .outerjoin(equipado, equipado.c.user_item_id == UserItem.id)
        .where(
            sa.or_(
                sa.and_(UserItem.id.is_not(None), UserItem.revoked_at.is_(None)),
                _visible_sin_poseer(instante, usuario_id),
            )
        )
    )

    if slot is not None:
        consulta = consulta.where(Item.slot == slot)
    if rarity is not None:
        consulta = consulta.where(Item.rarity == rarity)
    if origin is not None:
        consulta = consulta.where(Item.origin == origin)
    if state == "owned":
        consulta = consulta.where(UserItem.id.is_not(None))
    elif state == "locked":
        consulta = consulta.where(UserItem.id.is_(None))
    elif state == "new":
        consulta = consulta.where(UserItem.id.is_not(None), UserItem.is_new.is_(True))
    elif state == "equipped":
        consulta = consulta.where(equipado.c.slot_equipado.is_not(None))

    total = int(
        db.execute(
            sa.select(sa.func.count()).select_from(consulta.subquery())
        ).scalar_one()
    )

    clave = decodificar_cursor(cursor)
    if clave:
        try:
            desde = dt.datetime.fromisoformat(str(clave["created_at"]))
            desde_id = uuid.UUID(str(clave["id"]))
        except (KeyError, ValueError) as exc:
            raise ValidationFailed(
                "El cursor de paginación no es válido.",
                field_errors=[{"field": "cursor", "message": "Cursor ilegible."}],
            ) from exc
        consulta = consulta.where(
            sa.tuple_(Item.created_at, Item.id) > sa.tuple_(desde, desde_id)
        )

    consulta = consulta.order_by(Item.created_at, Item.id).limit(tope + 1)
    filas = db.execute(consulta).all()

    hay_mas = len(filas) > tope
    filas = filas[:tope]

    hechos = HechosUsuario(db, usuario_id, ahora=instante)
    resultado: list[FilaInventario] = []
    for item, user_item, slot_equipado in filas:
        poseido = user_item is not None
        requisitos: list[dict[str, Any]] = []
        bloqueado = False
        if not poseido:
            evaluacion = evaluar_item(db, usuario_id, item, hechos=hechos)
            bloqueado = not evaluacion.desbloqueado
            requisitos = [c.as_dict() for c in evaluacion.condiciones_visibles]
        if state == "unlocked" and bloqueado:
            continue
        resultado.append(
            FilaInventario(
                item=item,
                owned=poseido,
                locked=bloqueado,
                is_new=bool(user_item.is_new) if poseido else False,
                equipped=slot_equipado is not None,
                user_item_id=user_item.id if poseido else None,
                acquired_at=user_item.acquired_at if poseido else None,
                equipped_slot=slot_equipado,
                requirements=requisitos,
            )
        )

    siguiente = None
    if hay_mas and resultado:
        ultimo = resultado[-1].item
        siguiente = codificar_cursor(
            {"created_at": isoformat_z(ultimo.created_at), "id": str(ultimo.id)}
        )

    return PaginaInventario(
        items=resultado,
        limit=tope,
        next_cursor=siguiente,
        has_more=hay_mas,
        total=total,
    )


# ---------------------------------------------------------------------------
# Ficha de un ítem
# ---------------------------------------------------------------------------


def obtener_item(db: Session, usuario_id: uuid.UUID, item_id: uuid.UUID) -> Item:
    """Carga un ítem visible para este usuario o lanza 404 (nunca 403, §8.7)."""
    item = db.get(Item, item_id)
    if item is None:
        raise NotFound(details={"item_id": str(item_id)})
    if item.owner_user_id is not None and item.owner_user_id != usuario_id:
        raise NotFound(details={"item_id": str(item_id)})
    if item.visibility is ItemVisibility.HIDDEN and not posee(db, usuario_id, item_id):
        raise NotFound(details={"item_id": str(item_id)})
    return item


def posee(db: Session, usuario_id: uuid.UUID, item_id: uuid.UUID) -> bool:
    """Indica si el usuario tiene una instancia vigente (no revocada) del ítem."""
    return (
        db.execute(
            sa.select(sa.func.count())
            .select_from(UserItem)
            .where(
                UserItem.user_id == usuario_id,
                UserItem.item_id == item_id,
                UserItem.revoked_at.is_(None),
            )
        ).scalar_one()
        > 0
    )


def instancia(db: Session, usuario_id: uuid.UUID, item_id: uuid.UUID) -> UserItem | None:
    """Instancia poseída del ítem, si existe (incluye las revocadas)."""
    return db.execute(
        sa.select(UserItem).where(
            UserItem.user_id == usuario_id, UserItem.item_id == item_id
        )
    ).scalar_one_or_none()


def detalle_item(
    db: Session,
    usuario_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    marcar_visto: bool = True,
) -> FilaInventario:
    """Ficha del ítem con `explain` de requisitos; al abrirla se apaga la insignia "nuevo"."""
    item = obtener_item(db, usuario_id, item_id)
    user_item = instancia(db, usuario_id, item_id)
    poseido = user_item is not None and user_item.revoked_at is None

    slot_equipado = db.execute(
        sa.select(EquippedItem.slot)
        .join(Character, Character.id == EquippedItem.character_id)
        .where(
            Character.user_id == usuario_id,
            EquippedItem.user_item_id == (user_item.id if user_item else None),
        )
    ).scalar_one_or_none()

    era_nuevo = bool(user_item.is_new) if poseido else False
    if poseido and marcar_visto and user_item.is_new:
        user_item.is_new = False
        db.flush()

    requisitos: list[dict[str, Any]] = []
    bloqueado = False
    if not poseido:
        evaluacion = evaluar_item(db, usuario_id, item)
        bloqueado = not evaluacion.desbloqueado
        requisitos = [c.as_dict() for c in evaluacion.condiciones_visibles]

    return FilaInventario(
        item=item,
        owned=poseido,
        locked=bloqueado,
        is_new=era_nuevo,
        equipped=slot_equipado is not None,
        user_item_id=user_item.id if poseido else None,
        acquired_at=user_item.acquired_at if poseido else None,
        equipped_slot=slot_equipado,
        requirements=requisitos,
    )


def registrar_previsualizacion(
    db: Session,
    usuario_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    momento: dt.datetime | None = None,
) -> None:
    """Registra `ITEM_PREVIEWED` (analítica del botón "Probar" de la tienda)."""
    from app.models.identity import (  # noqa: PLC0415 - cruce perezoso entre módulos (§1.3)
        User,  # import local: evita un ciclo con `identity`
    )

    item = obtener_item(db, usuario_id, item_id)
    usuario = db.get(User, usuario_id)
    if usuario is None:
        raise NotFound(details={"user_id": str(usuario_id)})

    instante = momento or utcnow()
    bloqueado = not posee(db, usuario_id, item_id) and not evaluar_item(
        db, usuario_id, item
    ).desbloqueado

    registrar_evento(
        db,
        event_type=EventType.ITEM_PREVIEWED,
        usuario=usuario,
        payload={"item_code": item.code, "locked": bloqueado},
        clave=recortar_clave(
            f"item-previewed:{usuario_id}:{item_id}:{instante.isoformat()}"
        ),
        local_date=user_local_date(instante, usuario.timezone),
        momento=instante,
    )
    db.flush()


def requisitos_visibles(
    db: Session, usuario_id: uuid.UUID, item: Item
) -> list[dict[str, Any]]:
    """Atajo para la tienda: requisitos explicados del ítem (modo `explain`)."""
    filas = requisitos_de(db, item.id)
    evaluacion = evaluar_item(db, usuario_id, item, requisitos=filas)
    return [c.as_dict() for c in evaluacion.condiciones_visibles]


__all__ = [
    "ESTADOS_INVENTARIO",
    "LIMITE_MAXIMO",
    "LIMITE_POR_DEFECTO",
    "FilaInventario",
    "PaginaInventario",
    "codificar_cursor",
    "decodificar_cursor",
    "detalle_item",
    "instancia",
    "listar_inventario",
    "normalizar_limite",
    "obtener_item",
    "posee",
    "registrar_previsualizacion",
    "requisitos_visibles",
]
