"""Pruebas del evaluador de requisitos de desbloqueo (contrato §6.13)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.models.economy import UserItem
from app.models.enums import (
    EventType,
    ItemOrigin,
    ItemRarity,
    ItemSlot,
    KnowledgeAreaStatus,
    RequirementType,
)
from app.modules.economy import requisitos

pytestmark = pytest.mark.db


def _item_de_dominio(crear_item, crear_requisito, area, *, umbral: float = 80):
    """Ítem de conocimiento que se otorga solo al alcanzar cierto dominio del área."""
    item = crear_item(
        name="Cetro de BigQuery",
        slot=ItemSlot.WEAPON,
        rarity=ItemRarity.EPIC,
        origin=ItemOrigin.KNOWLEDGE,
        auto_grant=True,
        requirement_facts=["mastery"],
        knowledge_area_id=area.id,
    )
    crear_requisito(
        item,
        requirement_type=RequirementType.MASTERY_GTE,
        knowledge_area_id=area.id,
        target_value=umbral,
        label_template="Dominio de {area}: {current} / {target} %",
    )
    return item


def test_dominio_insuficiente_no_desbloquea(
    db, configuracion, usuario, area, crear_item, crear_requisito, fijar_dominio
):
    """Con 62 % de dominio y un umbral de 80 % el ítem sigue bloqueado y se explica."""
    item = _item_de_dominio(crear_item, crear_requisito, area)
    fijar_dominio(usuario, area, 62)

    evaluacion = requisitos.evaluar_item(db, usuario.id, item)

    assert evaluacion.desbloqueado is False
    condicion = evaluacion.condiciones_visibles[0]
    assert condicion.met is False
    assert condicion.current == 62.0
    assert condicion.target == 80.0
    assert condicion.label == "Dominio de SQL: 62 / 80 %"

    otorgados = requisitos.evaluar_desbloqueos(
        db, usuario.id, {"event_type": EventType.MASTERY_UPDATED}
    )
    assert otorgados == []
    assert db.execute(
        sa.select(sa.func.count()).select_from(UserItem).where(UserItem.user_id == usuario.id)
    ).scalar_one() == 0


def test_dominio_suficiente_desbloquea_y_otorga(
    db, configuracion, usuario, area, crear_item, crear_requisito, fijar_dominio
):
    """Al alcanzar el umbral el ítem se desbloquea y `auto_grant` lo entrega."""
    item = _item_de_dominio(crear_item, crear_requisito, area)
    fijar_dominio(usuario, area, 82, status=KnowledgeAreaStatus.MASTERED)

    evaluacion = requisitos.evaluar_item(db, usuario.id, item)
    assert evaluacion.desbloqueado is True
    assert evaluacion.condiciones_visibles[0].met is True

    otorgados = requisitos.evaluar_desbloqueos(
        db, usuario.id, {"event_type": EventType.MASTERY_UPDATED}
    )

    assert [i.code for i in otorgados] == [item.code]
    user_item = db.execute(
        sa.select(UserItem).where(
            UserItem.user_id == usuario.id, UserItem.item_id == item.id
        )
    ).scalar_one()
    assert user_item.origin is ItemOrigin.KNOWLEDGE
    assert user_item.source_ref["requirements_snapshot"]["conditions"][0]["met"] is True


def test_el_desbloqueo_es_idempotente(
    db, configuracion, usuario, area, crear_item, crear_requisito, fijar_dominio
):
    """Reevaluar el mismo evento no duplica la instancia ni vuelve a "otorgar"."""
    item = _item_de_dominio(crear_item, crear_requisito, area)
    fijar_dominio(usuario, area, 90, status=KnowledgeAreaStatus.MASTERED)

    contexto = {"event_type": EventType.MASTERY_UPDATED}
    primera = requisitos.evaluar_desbloqueos(db, usuario.id, contexto)
    segunda = requisitos.evaluar_desbloqueos(db, usuario.id, contexto)
    tercera = requisitos.evaluar_desbloqueos(db, usuario.id, {"todos": True})

    assert [i.code for i in primera] == [item.code]
    assert segunda == []
    assert tercera == []

    instancias = db.execute(
        sa.select(sa.func.count()).select_from(UserItem).where(
            UserItem.user_id == usuario.id, UserItem.item_id == item.id
        )
    ).scalar_one()
    assert instancias == 1


def test_combinacion_y_o_entre_grupos(
    db, configuracion, usuario, personaje, area, crear_item, crear_requisito, fijar_dominio
):
    """OR de ANDs: basta con que un grupo se cumpla entero (§6.13)."""
    item = crear_item(
        name="Capa de las dos vías",
        origin=ItemOrigin.ACHIEVEMENT,
        requirement_facts=["mastery", "level"],
    )
    # Grupo 0: dominio 95 Y nivel 30 (no se cumple).
    crear_requisito(
        item,
        requirement_type=RequirementType.MASTERY_GTE,
        knowledge_area_id=area.id,
        target_value=95,
        group_index=0,
        position=0,
    )
    crear_requisito(
        item,
        requirement_type=RequirementType.LEVEL_GTE,
        target_count=30,
        group_index=0,
        position=1,
    )
    # Grupo 1: nivel 10 (sí se cumple: el personaje es de nivel 10).
    crear_requisito(
        item,
        requirement_type=RequirementType.LEVEL_GTE,
        target_count=10,
        group_index=1,
        position=0,
    )
    fijar_dominio(usuario, area, 50)

    evaluacion = requisitos.evaluar_item(db, usuario.id, item)

    assert evaluacion.desbloqueado is True
    assert evaluacion.grupo_mas_cercano == 1


def test_requisito_de_racha_usa_la_mejor_marca(
    db, configuracion, usuario, crear_item, crear_requisito
):
    """`streak_kind = best` mira la mejor racha histórica, no la actual."""
    from app.models.enums import StreakKind
    from app.models.gamification import Streak

    db.add(Streak(user_id=usuario.id, current_length=2, best_length=14))
    db.flush()

    item = crear_item(name="Botas del caminante", origin=ItemOrigin.STREAK)
    fila = crear_requisito(
        item,
        requirement_type=RequirementType.STREAK_GTE,
        target_count=14,
    )
    fila.streak_kind = StreakKind.BEST
    db.flush()

    assert requisitos.evaluar_item(db, usuario.id, item).desbloqueado is True

    fila.streak_kind = StreakKind.CURRENT
    db.flush()
    assert requisitos.evaluar_item(db, usuario.id, item).desbloqueado is False


def test_integridad_educativa_de_los_items_de_conocimiento(
    db, configuracion, usuario, crear_item, crear_requisito
):
    """Un ítem `origin = knowledge` exige una condición de desempeño; si no, no se otorga."""
    item = crear_item(
        name="Insignia sospechosa",
        origin=ItemOrigin.KNOWLEDGE,
        auto_grant=True,
        requirement_facts=["lessons"],
    )
    crear_requisito(
        item,
        requirement_type=RequirementType.LESSONS_COMPLETED_GTE,
        target_count=1,
    )
    filas = requisitos.requisitos_de(db, item.id)

    assert requisitos.validar_integridad_educativa(item, filas) is False
    assert requisitos.evaluar_desbloqueos(db, usuario.id, {"todos": True}) == []
