"""El catálogo de ítems: forma, integridad educativa y evaluación de requisitos.

Comprobaciones exigidas:

- Los 46 ítems tienen `slot` y `rarity` válidos, y el reparto por rareza y origen es
  el de 06c §8.6.
- **Regla de integridad educativa** (contrato §6.13): todo ítem con
  `origin = knowledge` tiene al menos una condición de desempeño. Se verifica con el
  validador real, `app.modules.economy.requisitos.validar_integridad_educativa`.
- El evaluador declarativo de `app.modules.economy.requisitos` procesa **todas** las
  filas de `item_requirements` sin lanzar ninguna excepción, y también las explica.
- Los precios y niveles mínimos de la tienda salen de `game_configs`, no del código.
"""

from __future__ import annotations

from collections import Counter

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.economy import Item, ItemRequirement, ShopListing
from app.models.enums import Currency, ItemOrigin, ItemRarity, ItemSlot, RequirementType
from app.models.identity import User
from app.modules.economy import requisitos
from app.modules.gamification.servicio_config import ServicioConfig
from app.seeds.items import ITEMS, KITS_INICIALES, listados_tienda

pytestmark = pytest.mark.db

#: Reparto por rareza del resumen de 06c §8.6.
RAREZAS_ESPERADAS: dict[ItemRarity, int] = {
    ItemRarity.COMMON: 15,
    ItemRarity.UNCOMMON: 10,
    ItemRarity.RARE: 8,
    ItemRarity.EPIC: 7,
    ItemRarity.LEGENDARY: 5,
    ItemRarity.MYTHIC: 1,
}

#: Reparto por origen del catálogo inicial (contrato §9).
ORIGENES_ESPERADOS: dict[ItemOrigin, int] = {
    ItemOrigin.STARTER: 9,
    ItemOrigin.SHOP: 21,
    ItemOrigin.KNOWLEDGE: 9,
    ItemOrigin.STREAK: 4,
    ItemOrigin.ACHIEVEMENT: 3,
}


def _items(db: Session) -> list[Item]:
    """Los ítems del catálogo semilla, leídos de la base."""
    codigos = [semilla.code for semilla in ITEMS]
    return list(db.execute(sa.select(Item).where(Item.code.in_(codigos))).scalars())


def test_el_catalogo_tiene_46_items_con_el_reparto_del_documento(db: Session) -> None:
    """9 iniciales + 21 de tienda + 9 de conocimiento + 4 de racha + 3 de logro."""
    filas = _items(db)
    assert len(filas) == 46
    assert Counter(fila.rarity for fila in filas) == RAREZAS_ESPERADAS
    assert Counter(fila.origin for fila in filas) == ORIGENES_ESPERADOS


def test_todos_los_items_tienen_slot_y_rareza_validos(db: Session) -> None:
    """`slot` y `rarity` son miembros del enum, y ninguna ranura es reservada."""
    reservadas = {ItemSlot.PET, ItemSlot.MOUNT}
    for fila in _items(db):
        assert isinstance(fila.slot, ItemSlot), fila.code
        assert isinstance(fila.rarity, ItemRarity), fila.code
        assert fila.slot not in reservadas, fila.code
        assert fila.name and fila.description, fila.code
        assert fila.render_manifest.get("layers"), fila.code


def test_ningun_item_de_conocimiento_es_premium(db: Session) -> None:
    """El check de tabla `knowledge_not_premium` y la regla de 06c §7.5."""
    for fila in _items(db):
        if fila.origin is ItemOrigin.KNOWLEDGE:
            assert fila.tier_required is None, fila.code


def test_los_items_de_conocimiento_cumplen_la_integridad_educativa(db: Session) -> None:
    """Contrato §6.13: exigen una condición de desempeño, no solo tiempo o lecciones."""
    for fila in _items(db):
        filas = requisitos.requisitos_de(db, fila.id)
        assert requisitos.validar_integridad_educativa(fila, filas) is True, fila.code
        if fila.origin is ItemOrigin.KNOWLEDGE:
            tipos = {requisito.requirement_type for requisito in filas}
            assert tipos & requisitos.REQUISITOS_DE_DESEMPENO, fila.code


def test_los_items_de_tienda_no_llevan_requisitos_declarativos(db: Session) -> None:
    """§6.13: un ítem de tienda se gatea con el listado (precio y nivel), no con el DSL."""
    for fila in _items(db):
        if fila.origin is ItemOrigin.SHOP:
            assert requisitos.requisitos_de(db, fila.id) == [], fila.code


def test_el_evaluador_procesa_todas_las_condiciones_sin_error(db: Session, usuario: User) -> None:
    """Las 18 filas de `item_requirements` las evalúa el motor real sin reventar."""
    hechos = requisitos.HechosUsuario(db, usuario.id)
    evaluados = 0
    for fila in _items(db):
        evaluacion = requisitos.evaluar_item(db, usuario.id, fila, hechos=hechos)
        assert evaluacion.item_code == fila.code
        for condicion in evaluacion.condiciones:
            assert isinstance(condicion.requirement_type, RequirementType)
            assert condicion.met is False  # el usuario nuevo no cumple nada todavía
            assert condicion.target > 0
            assert condicion.label
            evaluados += 1
    assert evaluados == 18


def test_el_modo_explain_produce_texto_para_cada_item_bloqueado(db: Session, usuario: User) -> None:
    """Cada condición se explica con `{met, current, target, label, cta}` (§6.13)."""
    hechos = requisitos.HechosUsuario(db, usuario.id)
    for fila in _items(db):
        if not requisitos.requisitos_de(db, fila.id):
            continue
        explicacion = requisitos.explicar_requisitos(db, usuario.id, fila, hechos=hechos)
        assert explicacion, fila.code
        for condicion in explicacion:
            assert set(condicion) >= {"type", "met", "current", "target", "label", "cta"}
            assert condicion["label"].strip()


def test_las_familias_de_hechos_coinciden_con_los_requisitos(db: Session) -> None:
    """`requirement_facts` filtra candidatos por evento: debe cubrir cada condición."""
    for fila in _items(db):
        filas = requisitos.requisitos_de(db, fila.id)
        if not filas:
            continue
        esperadas = {requisitos.FAMILIA_POR_REQUISITO[requisito.requirement_type] for requisito in filas}
        assert esperadas <= set(fila.requirement_facts), fila.code


def test_las_plantillas_derivadas_apuntan_al_area_del_propio_usuario(db: Session) -> None:
    """Las tres plantillas de 06c §5.6 usan `AreaRef.self` y no son equipables."""
    plantillas = [fila for fila in _items(db) if fila.is_template]
    assert {fila.code for fila in plantillas} == {
        "tpl_capa_estudiante",
        "tpl_capa_maestro",
        "tpl_insignia_perfeccion",
    }
    for fila in plantillas:
        filas = requisitos.requisitos_de(db, fila.id)
        assert filas
        for requisito in filas:
            assert requisito.area_slug == "self"
            assert requisito.knowledge_area_id is None
        assert fila.render_manifest["tint"] == {
            "channel": "category_color",
            "mode": "modulate",
        }


def test_los_items_de_racha_usan_la_mejor_racha(db: Session) -> None:
    """06c §8.4: la constancia demostrada no se pierde por un día perdido."""
    from app.models.enums import StreakKind

    codigos = {"antorcha_constancia", "botas_caminante", "capa_llamas_persistentes", "corona_fuego_eterno"}
    for fila in _items(db):
        if fila.code not in codigos:
            continue
        filas = requisitos.requisitos_de(db, fila.id)
        assert len(filas) == 1
        assert filas[0].requirement_type is RequirementType.STREAK_GTE
        assert filas[0].streak_kind is StreakKind.BEST


def test_los_precios_de_la_tienda_salen_de_game_configs(db: Session, cfg: ServicioConfig) -> None:
    """§5.9 D6 y D7: precio y nivel mínimo se derivan de la rareza, nunca del código."""
    precios = cfg.obtener_json("shop.price_by_rarity")
    minimos = cfg.obtener_json("shop.min_level_by_rarity")

    filas = list(db.execute(sa.select(ShopListing, Item).join(Item, Item.id == ShopListing.item_id)).all())
    ofertas = [(listado, item) for listado, item in filas if item.origin is ItemOrigin.SHOP]
    assert len(ofertas) == 21

    for listado, item in ofertas:
        rareza = item.rarity.value
        assert listado.currency is Currency.GOLD
        assert listado.price == precios[rareza], item.code
        assert listado.min_level == minimos[rareza], item.code
        assert listado.is_active is True


def test_solo_se_ofertan_rarezas_vendibles(db: Session, cfg: ServicioConfig) -> None:
    """`shop.sellable_rarities`: legendario y mítico no se venden en el MVP."""
    vendibles = {str(r) for r in cfg.obtener_lista("shop.sellable_rarities")}
    for listado in listados_tienda(cfg):
        semilla = next(item for item in ITEMS if item.code == listado.item_code)
        assert semilla.rarity.value in vendibles


def test_los_destacados_respetan_el_tope_del_escaparate(cfg: ServicioConfig) -> None:
    """No pueden destacarse más ítems de los que permite `shop.featured_max`."""
    tope = cfg.obtener_int("shop.featured_max")
    destacados = [listado for listado in listados_tienda(cfg) if listado.is_featured]
    assert 0 < len(destacados) <= tope
    assert sorted(listado.featured_order for listado in destacados) == list(range(1, len(destacados) + 1))


def test_los_kits_iniciales_referencian_items_que_existen(db: Session) -> None:
    """Los cuatro arquetipos del MVP (06c §3.2) reparten ítems del catálogo."""
    codigos = {fila.code for fila in _items(db)}
    assert set(KITS_INICIALES) == {"acero", "arcano", "bosque", "muro"}
    for arquetipo, piezas in KITS_INICIALES.items():
        assert piezas, arquetipo
        for pieza in piezas:
            assert pieza in codigos, f"{arquetipo}: {pieza}"


def test_las_condiciones_apuntan_a_areas_canonicas_existentes(db: Session) -> None:
    """Cada `area_slug` que no sea `self` está resuelto contra un conocimiento real."""
    filas = list(db.execute(sa.select(ItemRequirement)).scalars())
    for requisito in filas:
        if requisito.area_slug in (None, "self"):
            continue
        assert requisito.knowledge_area_id is not None, requisito.area_slug
