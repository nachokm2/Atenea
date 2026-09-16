"""El manifiesto de capas, resuelto sobre ítems del catálogo de verdad.

Esta es la prueba que faltaba, y su ausencia tenía forma de hueco: las pruebas de
equipamiento fabricaban el manifiesto a mano, ya con la forma que el normalizador
esperaba, y las de la semilla solo comprobaban que la clave `layers` existiera.
Ninguna de las dos pasaba por el sitio donde el desajuste vivía.

Lo que se resolvía mal, en silencio y a la vez:

- `key` caía siempre al código del ítem, así que una capa —que aporta dos, la que
  cae por la espalda y el broche de delante— emitía **dos filas idénticas**.
- Todos los `z` valían cero, de modo que la pila acababa ordenada alfabéticamente
  por ranura: el arma detrás del cuerpo, la capa delante de la cara.
- `src` se perdía por el camino y el cliente nunca supo qué archivo pintar.
- `suppresses_layers` nombra capas y se comparaba contra códigos de ítem, así que
  un yelmo cerrado jamás tapaba el pelo.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.economy import Item, UserItem
from app.models.enums import ItemSlot
from app.models.identity import Character, User
from app.modules.economy import equipamiento
from app.modules.economy.equipamiento import PILA_DE_CAPAS, Z_DESCONOCIDO
from app.seeds.items import ItemSemilla, por_codigo


@pytest.fixture
def del_catalogo(db: Session, crear_item):
    """Crea en la base un ítem **tal como lo define la semilla**, por su código."""
    catalogo = por_codigo()

    def _crear(codigo: str) -> Item:
        semilla: ItemSemilla = catalogo[codigo]
        return crear_item(
            code=semilla.code,
            name=semilla.name,
            slot=semilla.slot,
            rarity=semilla.rarity,
            render_manifest=semilla.render_manifest,
        )

    return _crear


@pytest.fixture
def equipar(db: Session, personaje: Character, usuario: User, configuracion: dict):
    """Mete el ítem en el inventario del aprendiz y se lo pone."""

    def _equipar(item: Item) -> UserItem:
        propio = UserItem(user_id=usuario.id, item_id=item.id, origin=item.origin)
        db.add(propio)
        db.flush()
        equipamiento.equipar(db, usuario.id, propio.id, slot=item.slot)
        return propio

    return _equipar


def _capas(db: Session, usuario: User) -> list[dict]:
    return equipamiento.configuracion_avatar(db, usuario.id)["layers"]


# ---------------------------------------------------------------------------
# Una capa aporta dos capas distintas
# ---------------------------------------------------------------------------


def test_una_capa_aporta_su_espalda_y_su_broche(
    db: Session, usuario: User, del_catalogo, equipar
) -> None:
    """Dos filas DISTINTAS, una detrás del cuerpo y otra delante."""
    equipar(del_catalogo("capa_carmesi"))

    capas = _capas(db, usuario)

    nombres = [c["key"] for c in capas]
    assert nombres == ["cape_back", "cape_front"]
    assert [c["z"] for c in capas] == [20, 140]
    # Y el cuerpo va en medio de las dos: esa es toda la gracia de una capa.
    assert PILA_DE_CAPAS["cape_back"] < PILA_DE_CAPAS["body_base"] < PILA_DE_CAPAS["cape_front"]


def test_cada_capa_dice_que_archivo_pintar(
    db: Session, usuario: User, del_catalogo, equipar
) -> None:
    """`src` se perdía por el camino: el cliente recibía capas sin dibujo."""
    equipar(del_catalogo("capa_carmesi"))

    for capa in _capas(db, usuario):
        assert capa["src"], f"la capa {capa['key']} llegó sin archivo"
        assert capa["src"].endswith(".webp")
        assert capa["key"] in capa["src"]


def test_cada_capa_trae_su_rectangulo_del_lienzo(
    db: Session, usuario: User, del_catalogo, equipar
) -> None:
    """Sin el rectángulo no se puede colocar una pieza que no llene el lienzo."""
    equipar(del_catalogo("capa_carmesi"))

    for capa in _capas(db, usuario):
        assert capa["w"] == 1024
        assert capa["h"] == 1024
        assert capa["x"] == 0
        assert capa["y"] == 0


# ---------------------------------------------------------------------------
# El orden
# ---------------------------------------------------------------------------


def test_la_pila_se_ordena_por_z_y_no_alfabeticamente(
    db: Session, usuario: User, del_catalogo, equipar
) -> None:
    """Con todos los z en cero, el desempate era el nombre de la ranura.

    Y ordenado así, `weapon` (arma) caía antes que `head` (cabeza) solo porque la
    «b» de body va antes que la «w»: el arma se dibujaba detrás del cuerpo.
    """
    equipar(del_catalogo("capa_carmesi"))
    equipar(del_catalogo("yelmo_guardia"))
    equipar(del_catalogo("espada_del_sql"))

    capas = _capas(db, usuario)
    zetas = [c["z"] for c in capas]

    assert zetas == sorted(zetas)
    assert len(set(zetas)) == len(zetas), "dos capas distintas no pueden compartir z"
    orden = [c["key"] for c in capas]
    assert orden.index("cape_back") < orden.index("head") < orden.index("weapon")
    assert orden.index("weapon") < orden.index("cape_front")


def test_todas_las_capas_de_la_semilla_estan_en_la_pila() -> None:
    """Una capa que no esté en la pila se dibuja flotando sobre la cara.

    Es a propósito —un fallo visible se arregla; uno escondido detrás del cuerpo
    dura meses—, pero ninguna capa del catálogo debería llegar a ese caso.
    """
    from app.seeds.items import CAPAS_POR_RANURA, OCULTA_CABELLO

    declaradas = {capa for capas in CAPAS_POR_RANURA.values() for capa in capas}
    declaradas.update(OCULTA_CABELLO)

    assert declaradas <= set(PILA_DE_CAPAS), declaradas - set(PILA_DE_CAPAS)


def test_una_capa_inventada_se_ve_en_vez_de_esconderse(
    db: Session, usuario: User, crear_item, equipar
) -> None:
    equipar(
        crear_item(
            code="item_con_capa_rara",
            slot=ItemSlot.CAPE,
            render_manifest={
                "layers": [{"layer": "una_capa_que_nadie_declaro", "src": "x.webp"}]
            },
        )
    )

    assert _capas(db, usuario)[0]["z"] == Z_DESCONOCIDO


# ---------------------------------------------------------------------------
# Las supresiones, que nombran capas
# ---------------------------------------------------------------------------


def test_un_yelmo_cerrado_tapa_el_pelo(
    db: Session, usuario: User, del_catalogo, equipar
) -> None:
    """`suppresses_layers` nombra capas; antes se comparaba contra códigos."""
    yelmo = del_catalogo("yelmo_guardia")
    assert "hair_front" in yelmo.render_manifest["suppresses_layers"], (
        "este ítem debe declarar que tapa el pelo, o la prueba no prueba nada"
    )
    equipar(yelmo)

    capas = _capas(db, usuario)

    assert "head" in [c["key"] for c in capas]
    assert not {"hair_front", "hair_back"} & {c["key"] for c in capas}


def test_lo_que_no_se_suprime_sigue_ahi(
    db: Session, usuario: User, del_catalogo, equipar
) -> None:
    """La supresión tiene que morder solo lo que nombra."""
    equipar(del_catalogo("yelmo_guardia"))
    equipar(del_catalogo("capa_carmesi"))

    nombres = {c["key"] for c in _capas(db, usuario)}

    assert {"head", "cape_back", "cape_front"} <= nombres


# ---------------------------------------------------------------------------
# De dónde viene cada capa
# ---------------------------------------------------------------------------


def test_cada_capa_sabe_de_que_item_y_ranura_viene(
    db: Session, usuario: User, del_catalogo, equipar
) -> None:
    equipar(del_catalogo("capa_carmesi"))

    for capa in _capas(db, usuario):
        assert capa["item_code"] == "capa_carmesi"
        assert capa["slot"] == ItemSlot.CAPE.value


def test_un_item_sin_manifiesto_no_rompe_el_avatar(
    db: Session, usuario: User, crear_item, equipar
) -> None:
    """Aporta una capa con el nombre de su ranura, que es lo que le habría dado la semilla."""
    equipar(crear_item(code=f"pelado_{uuid.uuid4().hex[:8]}", slot=ItemSlot.BOOTS, render_manifest={}))

    capas = _capas(db, usuario)

    assert len(capas) == 1
    assert capas[0]["key"] == "boots"
    assert capas[0]["z"] == PILA_DE_CAPAS["boots"]
