"""Ítems de plantilla: un cosmético por conocimiento, derivado de un molde.

El catálogo trae tres moldes —la Capa del Estudiante, la del Maestro y la
Insignia de la Perfección— cuyo nombre lleva un hueco: «Capa del Estudiante de
{short_name}». No son equipables ni comprables; existen para que cada
conocimiento tenga los suyos, con su nombre y su color.

**Nunca se derivó ninguno.** `template_code` no aparecía escrito en ninguna parte
del código fuera de su propia definición, así que completar una ruta de SQL
prometía una capa que no existía como fila. Todos los cosméticos de conocimiento
del juego eran inalcanzables, y no había forma de notarlo desde fuera: la tienda,
el inventario y el evaluador de requisitos filtran los moldes con
`is_template = false`, de modo que no salía ni un molde suelto ni un derivado.
Simplemente no había nada.

## Qué se copia y qué no

El derivado hereda todo lo que define el objeto —ranura, rareza, origen, arte,
requisitos— y cambia solo tres cosas: su código, su nombre con el hueco relleno,
y el conocimiento al que pertenece.

El manifiesto de render se copia **tal cual**, apuntando al arte del molde. Es a
propósito: el dibujo es el mismo y lo que distingue a la capa de SQL de la de
Historia es el tinte, que el manifiesto ya declara como
`{"channel": "category_color"}`. Un arte por conocimiento sería otro encargo.

Los requisitos también se copian tal cual, incluido el `area_slug = "self"`, que
el evaluador resuelve contra el conocimiento del derivado (§6.9). Por eso una
plantilla puede decir «completa una ruta de *este* conocimiento» sin saber de
cuál habla.

## Cuándo se deriva

En dos momentos, y la función es idempotente para que los dos puedan repetirse:

- Al sembrar, para los conocimientos canónicos, que nacen con la base.
- Al crear un conocimiento nuevo el aprendiz, que es un suceso y por tanto llega
  por `KNOWLEDGE_AREA_CREATED`.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.content import KnowledgeArea
from app.models.economy import Item, ItemRequirement

logger = get_logger("atenea.plantillas")

#: Largo máximo de `items.code`.
LARGO_CODIGO = 64

#: Largo máximo de `items.name`.
LARGO_NOMBRE = 80

#: Prefijo que llevan los moldes del catálogo. Se quita al derivar para que el
#: código del derivado se lea como lo que es: un objeto de verdad.
PREFIJO_PLANTILLA = "tpl_"


def rellenar(texto: str | None, area: KnowledgeArea) -> str | None:
    """Sustituye los huecos del molde por los nombres del conocimiento.

    No usa `str.format` a propósito: los textos del catálogo llevan llaves que no
    son marcadores (en los `label_template` de los requisitos, por ejemplo), y
    `format` reventaría con un `KeyError` en cuanto alguien escribiera una.
    """
    if texto is None:
        return None
    return (
        texto.replace("{short_name}", area.short_name)
        .replace("{name}", area.name)
        .replace("{area}", area.name)
    )


def codigo_derivado(plantilla: Item, area: KnowledgeArea) -> str:
    """Código estable del derivado: el del molde sin prefijo, más el conocimiento."""
    base = plantilla.code.removeprefix(PREFIJO_PLANTILLA)
    return f"{base}_{area.slug}"[:LARGO_CODIGO]


def moldes(db: Session) -> list[Item]:
    """Los ítems de plantilla activos del catálogo."""
    return list(
        db.execute(
            sa.select(Item)
            .where(Item.is_template.is_(True), Item.is_active.is_(True))
            .order_by(Item.code)
        )
        .scalars()
        .all()
    )


def derivados_de(db: Session, area_id: uuid.UUID) -> dict[str, Item]:
    """Los derivados que ya tiene un conocimiento, indexados por molde."""
    filas = list(
        db.execute(
            sa.select(Item).where(
                Item.knowledge_area_id == area_id,
                Item.template_code.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    return {str(fila.template_code): fila for fila in filas}


def derivar_para_area(db: Session, area: KnowledgeArea) -> list[Item]:
    """Crea los cosméticos que le faltan a un conocimiento. Idempotente.

    Devuelve solo los que ha creado, para que quien llame pueda contarlos sin
    confundir «ya estaban» con «los acabo de hacer».
    """
    existentes = derivados_de(db, area.id)
    creados: list[Item] = []

    for molde in moldes(db):
        if molde.code in existentes:
            continue
        creados.append(_derivar(db, molde, area))

    if creados:
        db.flush()
        logger.info(
            "plantilla.derivada",
            area=area.slug,
            cuantos=len(creados),
            codigos=[item.code for item in creados],
        )
    return creados


def _derivar(db: Session, molde: Item, area: KnowledgeArea) -> Item:
    """Clona un molde para un conocimiento concreto, con sus requisitos."""
    derivado = Item(
        code=codigo_derivado(molde, area),
        name=(rellenar(molde.name, area) or molde.name)[:LARGO_NOMBRE],
        description=rellenar(molde.description, area),
        slot=molde.slot,
        rarity=molde.rarity,
        origin=molde.origin,
        requirements=dict(molde.requirements or {}),
        requirement_facts=list(molde.requirement_facts or []),
        auto_grant=molde.auto_grant,
        # El arte es el del molde: lo que distingue un conocimiento de otro es el
        # tinte, que el propio manifiesto declara.
        render_manifest=dict(molde.render_manifest or {}),
        icon_key=molde.icon_key,
        is_template=False,
        template_code=molde.code,
        knowledge_area_id=area.id,
        set_code=molde.set_code,
        visibility=molde.visibility,
        tier_required=molde.tier_required,
        is_active=molde.is_active,
        available_from=molde.available_from,
        available_to=molde.available_to,
        catalog_version=molde.catalog_version,
    )
    db.add(derivado)
    db.flush()

    for condicion in _condiciones(db, molde.id):
        db.add(
            ItemRequirement(
                item_id=derivado.id,
                group_index=condicion.group_index,
                position=condicion.position,
                requirement_type=condicion.requirement_type,
                knowledge_area_id=condicion.knowledge_area_id,
                # `self` se queda tal cual: el evaluador lo resuelve contra el
                # conocimiento de este derivado.
                area_slug=condicion.area_slug,
                target_value=condicion.target_value,
                **_extras(condicion),
            )
        )
    return derivado


def _condiciones(db: Session, item_id: uuid.UUID) -> list[ItemRequirement]:
    return list(
        db.execute(
            sa.select(ItemRequirement)
            .where(ItemRequirement.item_id == item_id)
            .order_by(ItemRequirement.group_index, ItemRequirement.position)
        )
        .scalars()
        .all()
    )


#: Columnas de `item_requirements` que se copian sin tocar y que no forman parte
#: de la identidad de la fila. Se resuelven por reflexión para que una columna
#: nueva en el modelo viaje sola al derivado en vez de perderse en silencio.
_NO_COPIABLES = frozenset(
    {
        "id",
        "item_id",
        "group_index",
        "position",
        "requirement_type",
        "knowledge_area_id",
        "area_slug",
        "target_value",
        "created_at",
        "updated_at",
    }
)


def _extras(condicion: ItemRequirement) -> dict[str, Any]:
    """El resto de columnas de la condición, copiadas tal cual."""
    return {
        columna.key: getattr(condicion, columna.key)
        for columna in sa.inspect(ItemRequirement).mapper.column_attrs
        if columna.key not in _NO_COPIABLES
    }


__all__ = [
    "codigo_derivado",
    "derivados_de",
    "derivar_para_area",
    "moldes",
    "rellenar",
]
