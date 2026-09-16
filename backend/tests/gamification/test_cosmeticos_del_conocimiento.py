"""Crear un conocimiento propio estrena sus cosméticos.

Los siete conocimientos canónicos reciben sus derivados al sembrar. Los que crea
el aprendiz no pasan por ahí: llegan por `KNOWLEDGE_AREA_CREATED`, que el módulo
de contenido ya emitía y que nadie escuchaba.

Sin esto, alguien que subiera su material de Derecho Romano y completara la ruta
entera no recibía nada: el desbloqueo automático no tenía ninguna fila que
otorgar, porque la Capa del Estudiante de Derecho Romano no existía.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.content import KnowledgeArea
from app.models.economy import Item
from app.models.enums import (
    EventType,
    ItemOrigin,
    ItemRarity,
    ItemSlot,
    KnowledgeCategory,
)
from app.models.identity import User
from app.modules.gamification import eventos


@pytest.fixture
def molde(db: Session) -> Item:
    """Un molde del catálogo, de los que llevan hueco en el nombre."""
    item = Item(
        code="tpl_capa_estudiante",
        name="Capa del Estudiante de {short_name}",
        description="Tela teñida con el color de la disciplina.",
        slot=ItemSlot.CAPE,
        rarity=ItemRarity.RARE,
        origin=ItemOrigin.KNOWLEDGE,
        requirements={},
        requirement_facts=["path"],
        auto_grant=True,
        render_manifest={},
        icon_key="tpl_capa_estudiante",
        is_template=True,
    )
    db.add(item)
    db.flush()
    return item


@pytest.fixture
def conocimiento_propio(db: Session) -> KnowledgeArea:
    """Un conocimiento creado por el aprendiz: no canónico, no sembrado."""
    fila = KnowledgeArea(
        slug=f"derecho-romano-{uuid.uuid4().hex[:8]}",
        name="Derecho Romano",
        short_name="Derecho",
        category=KnowledgeCategory.HUMANITIES,
        is_canonical=False,
    )
    db.add(fila)
    db.flush()
    return fila


def _crear_conocimiento(db: Session, usuario: User, area_id: uuid.UUID | None, clave: str):
    return eventos.registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=EventType.KNOWLEDGE_AREA_CREATED,
        payload={"knowledge_area_id": str(area_id) if area_id else None},
        idempotency_key=clave,
        source_module="content",
    )


def _derivados(db: Session, area_id: uuid.UUID) -> list[Item]:
    return list(
        db.execute(
            sa.select(Item).where(
                Item.knowledge_area_id == area_id, Item.template_code.is_not(None)
            )
        )
        .scalars()
        .all()
    )


def test_un_conocimiento_propio_estrena_su_capa(
    db: Session, usuario: User, molde: Item, conocimiento_propio: KnowledgeArea
) -> None:
    _crear_conocimiento(db, usuario, conocimiento_propio.id, clave=f"ka:{uuid.uuid4()}")

    derivados = _derivados(db, conocimiento_propio.id)
    assert len(derivados) == 1
    assert derivados[0].name == "Capa del Estudiante de Derecho"
    assert derivados[0].template_code == "tpl_capa_estudiante"


def test_crearlo_dos_veces_no_duplica(
    db: Session, usuario: User, molde: Item, conocimiento_propio: KnowledgeArea
) -> None:
    _crear_conocimiento(db, usuario, conocimiento_propio.id, clave=f"ka:{uuid.uuid4()}")
    _crear_conocimiento(db, usuario, conocimiento_propio.id, clave=f"ka:{uuid.uuid4()}")

    assert len(_derivados(db, conocimiento_propio.id)) == 1


def test_un_evento_sin_conocimiento_no_rompe_el_motor(
    db: Session, usuario: User, molde: Item
) -> None:
    _crear_conocimiento(db, usuario, None, clave=f"ka-sin-id:{uuid.uuid4()}")

    assert db.execute(
        sa.select(sa.func.count(Item.id)).where(Item.template_code.is_not(None))
    ).scalar_one() == 0


def test_un_conocimiento_que_ya_no_existe_no_rompe_el_motor(
    db: Session, usuario: User, molde: Item
) -> None:
    """El evento puede llegar tarde; el motor no puede caerse por eso."""
    _crear_conocimiento(db, usuario, uuid.uuid4(), clave=f"ka-fantasma:{uuid.uuid4()}")

    assert db.execute(
        sa.select(sa.func.count(Item.id)).where(Item.template_code.is_not(None))
    ).scalar_one() == 0
