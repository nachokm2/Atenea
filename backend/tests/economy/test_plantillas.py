"""Los cosméticos de conocimiento tienen que existir como fila.

El catálogo trae tres moldes cuyo nombre lleva un hueco —«Capa del Estudiante de
{short_name}»— y que no son equipables ni comprables: existen para derivar uno por
conocimiento. **Nunca se derivó ninguno.** `template_code` no aparecía escrito en
ninguna parte fuera de su propia definición.

La consecuencia: completar una ruta de SQL prometía una capa que no existía, y
todo cosmético de conocimiento del juego era inalcanzable. Y no había forma de
notarlo desde fuera, porque la tienda, el inventario y el evaluador de requisitos
filtran los moldes con `is_template = false`: no salía ni un molde suelto ni un
derivado, simplemente no había nada.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.content import KnowledgeArea
from app.models.economy import Item, ItemRequirement
from app.models.enums import ItemOrigin, ItemSlot, KnowledgeCategory, RequirementType
from app.modules.economy import plantillas


@pytest.fixture
def molde(db: Session, crear_item) -> Item:
    """Un molde con su condición, como los tres del catálogo."""
    item = crear_item(
        code="tpl_capa_estudiante",
        name="Capa del Estudiante de {short_name}",
        description="Tela teñida con el color de {name}.",
        slot=ItemSlot.CAPE,
        origin=ItemOrigin.KNOWLEDGE,
        auto_grant=True,
        requirement_facts=["path"],
        is_template=True,
    )
    db.add(
        ItemRequirement(
            item_id=item.id,
            group_index=0,
            position=0,
            requirement_type=RequirementType.PATH_COMPLETED,
            # `self` es la gracia del molde: no sabe de qué conocimiento habla.
            area_slug="self",
            target_count=1,
            label_template="Completa una ruta de {area}",
        )
    )
    db.flush()
    return item


@pytest.fixture
def otro_conocimiento(db: Session) -> KnowledgeArea:
    fila = KnowledgeArea(
        slug=f"historia-{uuid.uuid4().hex[:8]}",
        name="Historia de Chile",
        short_name="Historia",
        category=KnowledgeCategory.HUMANITIES,
    )
    db.add(fila)
    db.flush()
    return fila


def _derivados(db: Session) -> list[Item]:
    return list(
        db.execute(sa.select(Item).where(Item.template_code.is_not(None)).order_by(Item.code))
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# Derivar
# ---------------------------------------------------------------------------


def test_un_conocimiento_estrena_sus_cosmeticos(
    db: Session, area: KnowledgeArea, molde: Item
) -> None:
    creados = plantillas.derivar_para_area(db, area)

    assert len(creados) == 1
    derivado = creados[0]
    assert derivado.template_code == "tpl_capa_estudiante"
    assert derivado.knowledge_area_id == area.id
    # Un derivado sí es un objeto de verdad: se puede tener y equipar.
    assert derivado.is_template is False


def test_el_hueco_del_nombre_se_rellena(
    db: Session, area: KnowledgeArea, molde: Item
) -> None:
    derivado = plantillas.derivar_para_area(db, area)[0]

    assert derivado.name == "Capa del Estudiante de SQL"
    assert derivado.description is not None
    assert "{name}" not in derivado.description
    assert "SQL" in derivado.description


def test_el_codigo_lleva_el_conocimiento_y_pierde_el_prefijo(
    db: Session, area: KnowledgeArea, molde: Item
) -> None:
    derivado = plantillas.derivar_para_area(db, area)[0]

    assert derivado.code == f"capa_estudiante_{area.slug}"
    assert not derivado.code.startswith("tpl_")
    assert len(derivado.code) <= plantillas.LARGO_CODIGO


def test_derivar_dos_veces_no_duplica(db: Session, area: KnowledgeArea, molde: Item) -> None:
    """La siembra se repite en cada despliegue: no puede crear un catálogo nuevo."""
    plantillas.derivar_para_area(db, area)

    segunda = plantillas.derivar_para_area(db, area)

    assert segunda == []
    assert len(_derivados(db)) == 1


def test_cada_conocimiento_tiene_el_suyo(
    db: Session, area: KnowledgeArea, otro_conocimiento: KnowledgeArea, molde: Item
) -> None:
    plantillas.derivar_para_area(db, area)
    plantillas.derivar_para_area(db, otro_conocimiento)

    derivados = _derivados(db)
    assert len(derivados) == 2
    assert {d.name for d in derivados} == {
        "Capa del Estudiante de SQL",
        "Capa del Estudiante de Historia",
    }
    # Códigos distintos, o el segundo chocaría con el primero.
    assert len({d.code for d in derivados}) == 2


# ---------------------------------------------------------------------------
# Lo que se hereda
# ---------------------------------------------------------------------------


def test_la_condicion_viaja_con_su_self_intacto(
    db: Session, area: KnowledgeArea, molde: Item
) -> None:
    """`self` lo resuelve el evaluador contra el conocimiento del derivado (§6.9).

    Si se resolviera aquí, al derivar, el molde dejaría de servir para otros.
    """
    derivado = plantillas.derivar_para_area(db, area)[0]

    condiciones = list(
        db.execute(sa.select(ItemRequirement).where(ItemRequirement.item_id == derivado.id))
        .scalars()
        .all()
    )
    assert len(condiciones) == 1
    assert condiciones[0].area_slug == "self"
    assert condiciones[0].requirement_type == RequirementType.PATH_COMPLETED
    assert condiciones[0].target_count == 1
    assert condiciones[0].label_template == "Completa una ruta de {area}"


def test_el_derivado_hereda_lo_que_lo_define(
    db: Session, area: KnowledgeArea, molde: Item
) -> None:
    derivado = plantillas.derivar_para_area(db, area)[0]

    assert derivado.slot == molde.slot
    assert derivado.rarity == molde.rarity
    assert derivado.origin == molde.origin
    assert derivado.auto_grant == molde.auto_grant
    assert derivado.requirement_facts == molde.requirement_facts
    # El arte es el del molde: lo que cambia de un conocimiento a otro es el tinte.
    assert derivado.render_manifest == molde.render_manifest
    assert derivado.icon_key == molde.icon_key


def test_un_molde_apagado_no_se_deriva(
    db: Session, area: KnowledgeArea, molde: Item
) -> None:
    """Retirar un molde del catálogo tiene que dejar de producir derivados."""
    molde.is_active = False
    db.flush()

    assert plantillas.derivar_para_area(db, area) == []


# ---------------------------------------------------------------------------
# El relleno
# ---------------------------------------------------------------------------


def test_rellenar_no_se_rompe_con_llaves_que_no_son_huecos(area: KnowledgeArea) -> None:
    """Por eso no se usa `str.format`: un `{current}` suelto lo haría estallar."""
    texto = "Dominio de {short_name}: {current} / {target} %"

    resultado = plantillas.rellenar(texto, area)

    assert resultado == "Dominio de SQL: {current} / {target} %"


def test_rellenar_deja_en_paz_lo_que_no_tiene_huecos(area: KnowledgeArea) -> None:
    assert plantillas.rellenar("Capa de lana gris", area) == "Capa de lana gris"
    assert plantillas.rellenar(None, area) is None
