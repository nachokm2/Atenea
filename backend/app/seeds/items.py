"""Semilla de `items`, `item_requirements` y `shop_listings`: los 46 ítems del MVP.

Fuente normativa (contrato §9): `docs/auditoria/06c-inventario-equipamiento-tienda.md`
§8 «Catálogo inicial del MVP» — 9 iniciales, 21 de tienda, 9 de conocimiento, 4 de
racha y 3 de logro. El contrato manda en la **forma** (nombres de columna, enums,
claves de configuración); el documento aporta el **contenido**.

Decisiones que resuelven discrepancias documentadas, para que nadie las revierta:

- **Precio** (§5.9 D6): los precios por ítem de 06c se reescalan a las bandas por
  rareza de `shop.price_by_rarity`; ningún precio se escribe aquí a mano.
- **Nivel mínimo** (§5.9 D7): manda `shop.min_level_by_rarity` (común 1, poco común 3,
  raro 8, épico 15). Los "nivel ≥ 5" y "nivel ≥ 10" de 06c quedan absorbidos por esas
  bandas, que son más exigentes; el gateo vive en `shop_listings.min_level`, que es
  justo donde el contrato §6.13 dice que debe vivir el acceso de un ítem de tienda.
- **Ítems cosméticos** (§5.9 D19): ninguna fila lleva estadísticas de juego. No existe
  tal columna y no debe inventarse.
- **Integridad educativa** (§6.13): todo ítem con `origin = knowledge` lleva al menos
  una condición de desempeño (`path_completed`, `mastery_gte`, `areas_mastered_gte`,
  `assessment_score_gte`). El tiempo de estudio y el número de lecciones no bastan.
  La prueba `tests/seeds` lo verifica con `economy.requisitos.validar_integridad_educativa`.

Los ítems de tienda **no** llevan filas en `item_requirements`: un ítem sin requisitos
está desbloqueado por definición y su acceso lo gobierna el listado (precio y nivel
mínimo), tal como fija el contrato §6.13.

El `render_manifest` sigue el formato de 06c §2.7 (lienzo 1024×1024, capas con su
`layer_key` de la pila de §2.3 y recorte propio). El `src` de cada capa es el
nombre de su archivo dentro del juego de piezas de una familia —`<code>_<capa>.webp`,
plano y sin versión—, y el cliente le antepone la carpeta de la familia que
corresponda a la figura elegida. De qué familia es el cuerpo no se decide aquí a
propósito: el mismo objeto lo llevan las seis figuras.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.models.enums import (
    CharacterArchetype,
    ItemOrigin,
    ItemRarity,
    ItemSlot,
    ItemVisibility,
    RequirementType,
    StreakKind,
)
from app.modules.gamification.servicio_config import ServicioConfig

__all__ = [
    "ITEMS",
    "KITS_INICIALES",
    "ItemSemilla",
    "ListadoTienda",
    "RequisitoSemilla",
    "listados_tienda",
    "por_codigo",
]

#: Lienzo maestro compartido por todo el arte del avatar (06c §2.4).
LIENZO: dict[str, int] = {"w": 1024, "h": 1024}

#: Capas de la pila de dibujado (06c §2.3) que usa cada ranura por defecto.
CAPAS_POR_RANURA: dict[ItemSlot, tuple[str, ...]] = {
    ItemSlot.HEAD: ("head",),
    ItemSlot.BODY: ("outfit",),
    ItemSlot.CAPE: ("cape_back", "cape_front"),
    ItemSlot.GLOVES: ("gloves",),
    ItemSlot.BOOTS: ("boots",),
    ItemSlot.WEAPON: ("weapon",),
    ItemSlot.OFFHAND: ("offhand",),
    ItemSlot.ACCESSORY: ("accessory_body",),
}

#: Capas que oculta un yelmo cerrado mientras está equipado (06c §2.5).
OCULTA_CABELLO: tuple[str, ...] = ("hair_front", "hair_back")


def manifiesto(
    code: str,
    capas: tuple[str, ...],
    *,
    oculta: tuple[str, ...] = (),
    dos_manos: bool = False,
    tinte: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Construye el manifiesto de render de un ítem con la forma de 06c §2.7."""
    return {
        "item_id": code,
        "asset_version": 1,
        "canvas": dict(LIENZO),
        # `src` es el nombre del archivo de la capa dentro del juego de su
        # familia, plano y sin versión. Antes era `items/{code}/{capa}.v1.webp`,
        # una ruta que no correspondía a ningún archivo del repositorio: el
        # servidor la emitía, el cliente la leía en `CapaAvatar.assetKey` y ahí
        # se acababa, porque nadie la usaba para pintar nada.
        #
        # Plano y no en carpeta por ítem porque las entradas de directorio de
        # Flutter no son recursivas: treinta y un ítems serían treinta y una
        # líneas en `pubspec.yaml`. Sin versión porque el arte viaja dentro del
        # binario, así que la versión de la aplicación ya es la clave de caché;
        # `asset_version` sigue en el manifiesto para quien la necesite.
        #
        # De qué familia es el cuerpo no va aquí a propósito: el mismo objeto lo
        # llevan las seis figuras, y quien sabe cuál se eligió es el cliente.
        "layers": [
            {"layer": capa, "src": f"{code}_{capa}.webp", "x": 0, "y": 0, "w": 1024, "h": 1024}
            for capa in capas
        ],
        "suppresses_layers": list(oculta),
        "two_handed": dos_manos,
        "tint": tinte,
        "icon": f"items/{code}/icon.v1.webp",
    }


@dataclass(frozen=True, slots=True)
class RequisitoSemilla:
    """Una fila de `item_requirements`: una condición del DSL ya normalizada."""

    requirement_type: RequirementType
    group_index: int = 0
    """Grupo OR; las filas del mismo grupo se combinan con AND."""

    position: int = 0
    area_slug: str | None = None
    """Slug canónico, o `"self"` en una plantilla (se resuelve al derivar)."""

    target_value: Decimal | None = None
    """Umbral continuo: dominio o puntaje, en escala 0.00–100.00."""

    target_count: int | None = None
    """Umbral discreto: áreas, evaluaciones, lecciones, días de racha o nivel."""

    achievement_code: str | None = None
    streak_kind: StreakKind | None = None
    label_template: str | None = None
    """Plantilla del texto explicativo (06c §5.5); admite {area}, {current}, {target}."""


@dataclass(frozen=True, slots=True)
class ItemSemilla:
    """Un ítem del catálogo inicial con su DSL de requisitos y su presencia en tienda."""

    code: str
    name: str
    description: str
    slot: ItemSlot
    rarity: ItemRarity
    origin: ItemOrigin
    requirements: dict[str, Any] = field(default_factory=dict)
    """Árbol DSL `all`/`any` (06c §5.2); espejo normalizado en `requisitos`."""

    requirement_facts: tuple[str, ...] = ()
    """Familias de hechos que filtran los candidatos por evento (§6.13)."""

    auto_grant: bool = False
    render_manifest: dict[str, Any] = field(default_factory=dict)
    icon_key: str | None = None
    is_template: bool = False
    visibility: ItemVisibility = ItemVisibility.PUBLIC
    requisitos: tuple[RequisitoSemilla, ...] = ()
    en_tienda: bool = False
    destacado: int | None = None
    """Orden en el escaparate (1 = primero); `None` si no se destaca."""


def _condicion(tipo: str, **campos: Any) -> dict[str, Any]:
    """Nodo hoja del DSL de requisitos (06c §5.2)."""
    return {"type": tipo, **campos}


def _area(slug: str) -> dict[str, Any]:
    """`AreaRef` del DSL: área canónica o `self` en las plantillas."""
    return {"self": True} if slug == "self" else {"canonical": slug}


# ---------------------------------------------------------------------------
# 8.1 Kits iniciales (`starter`, 9 ítems, comunes)
# ---------------------------------------------------------------------------

_INICIALES: tuple[ItemSemilla, ...] = (
    ItemSemilla(
        code="jubon_recluta",
        name="Jubón de recluta",
        description="Cuero endurecido y remaches de hierro. No detiene una lanza, pero recuerda cada día de instrucción.",
        slot=ItemSlot.BODY,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.STARTER,
        render_manifest=manifiesto("jubon_recluta", CAPAS_POR_RANURA[ItemSlot.BODY]),
        icon_key="jubon_recluta",
    ),
    ItemSemilla(
        code="espada_entrenamiento",
        name="Espada de entrenamiento",
        description="Filo romo y peso honesto. Con ella se aprende la postura; con otra, más tarde, se defiende una idea.",
        slot=ItemSlot.WEAPON,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.STARTER,
        render_manifest=manifiesto("espada_entrenamiento", CAPAS_POR_RANURA[ItemSlot.WEAPON]),
        icon_key="espada_entrenamiento",
    ),
    ItemSemilla(
        code="tunica_iniciacion",
        name="Túnica de iniciación",
        description="Lino sencillo con el cordón del Círculo. Quien la viste acaba de admitir que no sabe, que es donde empieza todo.",
        slot=ItemSlot.BODY,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.STARTER,
        render_manifest=manifiesto("tunica_iniciacion", CAPAS_POR_RANURA[ItemSlot.BODY]),
        icon_key="tunica_iniciacion",
    ),
    ItemSemilla(
        code="baston_aprendiz",
        name="Bastón de aprendiz",
        description="Fresno sin tallar y una muesca por cada lección entendida de verdad. Todavía quedan muchas maderas lisas.",
        slot=ItemSlot.WEAPON,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.STARTER,
        render_manifest=manifiesto("baston_aprendiz", CAPAS_POR_RANURA[ItemSlot.WEAPON]),
        icon_key="baston_aprendiz",
    ),
    ItemSemilla(
        code="chaleco_explorador",
        name="Chaleco de explorador",
        description="Bolsillos para carbón, cuerda y mapas a medio dibujar. La Hermandad del Bosque viaja ligera y anota todo.",
        slot=ItemSlot.BODY,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.STARTER,
        render_manifest=manifiesto("chaleco_explorador", CAPAS_POR_RANURA[ItemSlot.BODY]),
        icon_key="chaleco_explorador",
    ),
    ItemSemilla(
        code="arco_fresno",
        name="Arco de fresno",
        description="Curvado a mano y encordado con tendón. Enseña la virtud que más falta hace al estudiar: apuntar antes de soltar.",
        slot=ItemSlot.WEAPON,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.STARTER,
        render_manifest=manifiesto("arco_fresno", CAPAS_POR_RANURA[ItemSlot.WEAPON]),
        icon_key="arco_fresno",
    ),
    ItemSemilla(
        code="sobreveste_vigia",
        name="Sobreveste de vigía",
        description="Paño gris sobre malla ligera, con el emblema del Muro al pecho. Quien vigila aprende mirando lo mismo mil veces.",
        slot=ItemSlot.BODY,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.STARTER,
        render_manifest=manifiesto("sobreveste_vigia", CAPAS_POR_RANURA[ItemSlot.BODY]),
        icon_key="sobreveste_vigia",
    ),
    ItemSemilla(
        code="escudo_madera",
        name="Escudo de madera",
        description="Tablas de roble y un umbo abollado. Cada abolladura es una pregunta que alguna vez te derribó.",
        slot=ItemSlot.OFFHAND,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.STARTER,
        render_manifest=manifiesto("escudo_madera", CAPAS_POR_RANURA[ItemSlot.OFFHAND]),
        icon_key="escudo_madera",
    ),
    ItemSemilla(
        code="botas_camino",
        name="Botas de camino",
        description="Suela gastada y cordones nuevos. Las lleva todo el mundo el primer día, y casi nadie las olvida después.",
        slot=ItemSlot.BOOTS,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.STARTER,
        render_manifest=manifiesto("botas_camino", CAPAS_POR_RANURA[ItemSlot.BOOTS]),
        icon_key="botas_camino",
    ),
)

#: Kits iniciales por Orden (06c §3.2). Los entrega `economy` al evaluar
#: `CHARACTER_CREATED`, de modo que las piezas salen también en el recibo.
#:
#: Las claves son el **valor del enum**, no el nombre castellano de la Orden.
#: Estuvieron escritas como "acero", "arcano", "bosque" y "muro", que no son
#: ninguno de los valores de `CharacterArchetype`, así que ninguna búsqueda
#: acertaba nunca y el personaje nacía sin nada que ponerse.
KITS_INICIALES: dict[str, tuple[str, ...]] = {
    CharacterArchetype.STEEL.value: (
        "jubon_recluta",
        "espada_entrenamiento",
        "botas_camino",
    ),
    CharacterArchetype.ARCANE.value: (
        "tunica_iniciacion",
        "baston_aprendiz",
        "botas_camino",
    ),
    CharacterArchetype.FOREST.value: (
        "chaleco_explorador",
        "arco_fresno",
        "botas_camino",
    ),
    CharacterArchetype.WALL.value: (
        "sobreveste_vigia",
        "escudo_madera",
        "espada_entrenamiento",
        "botas_camino",
    ),
}


# ---------------------------------------------------------------------------
# 8.2 Tienda (`shop`, 21 ítems)
# ---------------------------------------------------------------------------

_TIENDA: tuple[ItemSemilla, ...] = (
    ItemSemilla(
        code="capucha_viajero",
        name="Capucha de viajero",
        description="Lana basta contra la lluvia. La primera compra de casi todo el mundo, y por eso la más recordada.",
        slot=ItemSlot.HEAD,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("capucha_viajero", CAPAS_POR_RANURA[ItemSlot.HEAD]),
        icon_key="capucha_viajero",
        en_tienda=True,
        destacado=1,
    ),
    ItemSemilla(
        code="guantes_cuero",
        name="Guantes de cuero",
        description="Curtidos y sin adornos. Protegen la palma de la tinta y del filo, en ese orden de frecuencia.",
        slot=ItemSlot.GLOVES,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("guantes_cuero", CAPAS_POR_RANURA[ItemSlot.GLOVES]),
        icon_key="guantes_cuero",
        en_tienda=True,
    ),
    ItemSemilla(
        code="capa_lana_gris",
        name="Capa de lana gris",
        description="Abriga sin llamar la atención. Ideal para cruzar una plaza sin que nadie te pregunte qué estudias.",
        slot=ItemSlot.CAPE,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("capa_lana_gris", CAPAS_POR_RANURA[ItemSlot.CAPE]),
        icon_key="capa_lana_gris",
        en_tienda=True,
    ),
    ItemSemilla(
        code="morral_estudiante",
        name="Morral de estudiante",
        description="Correa remendada y más pergaminos de los que caben. Siempre pesa justo lo que falta por leer.",
        slot=ItemSlot.ACCESSORY,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("morral_estudiante", ("accessory_body",)),
        icon_key="morral_estudiante",
        en_tienda=True,
    ),
    ItemSemilla(
        code="sandalias_erudito",
        name="Sandalias del erudito",
        description="Cuero blando para suelos de biblioteca. Nadie corre con ellas, que es exactamente la idea.",
        slot=ItemSlot.BOOTS,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("sandalias_erudito", CAPAS_POR_RANURA[ItemSlot.BOOTS]),
        icon_key="sandalias_erudito",
        en_tienda=True,
    ),
    ItemSemilla(
        code="yelmo_guardia",
        name="Yelmo de la guardia",
        description="Acero pulido con nasal recto. Cierra el campo de visión a lo que importa y a nada más.",
        slot=ItemSlot.HEAD,
        rarity=ItemRarity.UNCOMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("yelmo_guardia", CAPAS_POR_RANURA[ItemSlot.HEAD], oculta=OCULTA_CABELLO),
        icon_key="yelmo_guardia",
        en_tienda=True,
    ),
    ItemSemilla(
        code="cota_escamas_cobre",
        name="Cota de escamas de cobre",
        description="Mil escamas cosidas una a una. Quien la forjó entendió antes que nadie el valor de repetir bien lo pequeño.",
        slot=ItemSlot.BODY,
        rarity=ItemRarity.UNCOMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("cota_escamas_cobre", CAPAS_POR_RANURA[ItemSlot.BODY]),
        icon_key="cota_escamas_cobre",
        en_tienda=True,
    ),
    ItemSemilla(
        code="capa_carmesi",
        name="Capa carmesí",
        description="Tinte caro y caída impecable. Se nota a cien pasos que ya no eres de los que acaban de llegar.",
        slot=ItemSlot.CAPE,
        rarity=ItemRarity.UNCOMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("capa_carmesi", CAPAS_POR_RANURA[ItemSlot.CAPE]),
        icon_key="capa_carmesi",
        en_tienda=True,
        destacado=2,
    ),
    ItemSemilla(
        code="guanteletes_acero",
        name="Guanteletes de acero",
        description="Articulados placa sobre placa. Pesados al principio; a la semana ya no los sientes.",
        slot=ItemSlot.GLOVES,
        rarity=ItemRarity.UNCOMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("guanteletes_acero", CAPAS_POR_RANURA[ItemSlot.GLOVES]),
        icon_key="guanteletes_acero",
        en_tienda=True,
    ),
    ItemSemilla(
        code="botas_reforzadas",
        name="Botas reforzadas",
        description="Puntera de hierro y suela doble. Hechas para jornadas largas y para no mirar atrás.",
        slot=ItemSlot.BOOTS,
        rarity=ItemRarity.UNCOMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("botas_reforzadas", CAPAS_POR_RANURA[ItemSlot.BOOTS]),
        icon_key="botas_reforzadas",
        en_tienda=True,
    ),
    ItemSemilla(
        code="espada_corta_acero",
        name="Espada corta de acero",
        description="Bien templada y sin florituras. Corta lo que hay que cortar y nada más: una virtud rara.",
        slot=ItemSlot.WEAPON,
        rarity=ItemRarity.UNCOMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("espada_corta_acero", CAPAS_POR_RANURA[ItemSlot.WEAPON]),
        icon_key="espada_corta_acero",
        en_tienda=True,
    ),
    ItemSemilla(
        code="escudo_roble",
        name="Escudo redondo de roble",
        description="Aro de hierro y madera veteada. Aguanta el primer error y te deja sitio para el segundo intento.",
        slot=ItemSlot.OFFHAND,
        rarity=ItemRarity.UNCOMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("escudo_roble", CAPAS_POR_RANURA[ItemSlot.OFFHAND]),
        icon_key="escudo_roble",
        en_tienda=True,
    ),
    ItemSemilla(
        code="anteojos_erudito",
        name="Anteojos de erudito",
        description="Cristal pulido en montura de latón. No hacen más lista a nadie; solo dejan de estorbar la letra pequeña.",
        slot=ItemSlot.ACCESSORY,
        rarity=ItemRarity.UNCOMMON,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("anteojos_erudito", ("accessory_face",)),
        icon_key="anteojos_erudito",
        en_tienda=True,
    ),
    ItemSemilla(
        code="sombrero_estrellado",
        name="Sombrero estrellado",
        description="Ala ancha y constelaciones bordadas en hilo de plata. Cada estrella marca una noche en vela que valió la pena.",
        slot=ItemSlot.HEAD,
        rarity=ItemRarity.RARE,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("sombrero_estrellado", CAPAS_POR_RANURA[ItemSlot.HEAD]),
        icon_key="sombrero_estrellado",
        en_tienda=True,
        destacado=3,
    ),
    ItemSemilla(
        code="armadura_placas",
        name="Armadura de placas pulidas",
        description="Reflejo de espejo y juntas perfectas. Solo la lleva bien quien ya lleva tiempo en pie.",
        slot=ItemSlot.BODY,
        rarity=ItemRarity.RARE,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("armadura_placas", CAPAS_POR_RANURA[ItemSlot.BODY]),
        icon_key="armadura_placas",
        en_tienda=True,
    ),
    ItemSemilla(
        code="capa_plumas_nocturnas",
        name="Capa de plumas nocturnas",
        description="Plumas de cuervo cosidas en escama. Absorbe la luz igual que un buen apunte absorbe una clase entera.",
        slot=ItemSlot.CAPE,
        rarity=ItemRarity.RARE,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("capa_plumas_nocturnas", CAPAS_POR_RANURA[ItemSlot.CAPE]),
        icon_key="capa_plumas_nocturnas",
        en_tienda=True,
    ),
    ItemSemilla(
        code="arco_bosque_antiguo",
        name="Arco largo del Bosque Antiguo",
        description="Tejo de doscientos años, encordado con seda. Perdona menos errores que el de fresno y premia mucho más.",
        slot=ItemSlot.WEAPON,
        rarity=ItemRarity.RARE,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("arco_bosque_antiguo", CAPAS_POR_RANURA[ItemSlot.WEAPON]),
        icon_key="arco_bosque_antiguo",
        en_tienda=True,
    ),
    ItemSemilla(
        code="escudo_blason_reino",
        name="Escudo con blasón del Reino",
        description="El emblema en esmalte, todavía sin muescas. Llevarlo obliga: el blasón se defiende estudiando.",
        slot=ItemSlot.OFFHAND,
        rarity=ItemRarity.RARE,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("escudo_blason_reino", CAPAS_POR_RANURA[ItemSlot.OFFHAND]),
        icon_key="escudo_blason_reino",
        en_tienda=True,
    ),
    ItemSemilla(
        code="corona_laurel_plata",
        name="Corona de laurel plateada",
        description="Hojas de plata batida, ligerísimas. En el Reino se concede a quien enseña, no a quien vence.",
        slot=ItemSlot.HEAD,
        rarity=ItemRarity.EPIC,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("corona_laurel_plata", CAPAS_POR_RANURA[ItemSlot.HEAD]),
        icon_key="corona_laurel_plata",
        en_tienda=True,
        destacado=4,
    ),
    ItemSemilla(
        code="tunica_constelaciones",
        name="Túnica de las constelaciones",
        description="Terciopelo azul con el cielo de invierno bordado. Dicen que las estrellas cambian según lo que hayas aprendido.",
        slot=ItemSlot.BODY,
        rarity=ItemRarity.EPIC,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("tunica_constelaciones", CAPAS_POR_RANURA[ItemSlot.BODY]),
        icon_key="tunica_constelaciones",
        en_tienda=True,
    ),
    ItemSemilla(
        code="espada_obsidiana",
        name="Espada de obsidiana",
        description="Vidrio volcánico con filo imposible. Es bella y frágil, como cualquier certeza que no se repasa.",
        slot=ItemSlot.WEAPON,
        rarity=ItemRarity.EPIC,
        origin=ItemOrigin.SHOP,
        render_manifest=manifiesto("espada_obsidiana", CAPAS_POR_RANURA[ItemSlot.WEAPON]),
        icon_key="espada_obsidiana",
        en_tienda=True,
    ),
)


# ---------------------------------------------------------------------------
# 8.3 Conocimiento (`knowledge`, 6 curados + 3 plantillas)
# ---------------------------------------------------------------------------

_CONOCIMIENTO: tuple[ItemSemilla, ...] = (
    ItemSemilla(
        code="espada_del_sql",
        name="Espada del SQL",
        description="Forjada en el Castillo de las Consultas. Su filo separa lo que preguntas de lo que de verdad necesitas saber.",
        slot=ItemSlot.WEAPON,
        rarity=ItemRarity.LEGENDARY,
        origin=ItemOrigin.KNOWLEDGE,
        requirements=_condicion("path_completed", area=_area("sql")),
        requirement_facts=("path",),
        auto_grant=True,
        render_manifest=manifiesto("espada_del_sql", CAPAS_POR_RANURA[ItemSlot.WEAPON]),
        icon_key="espada_del_sql",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.PATH_COMPLETED,
                area_slug="sql",
                target_count=1,
                label_template="Completa una ruta de {area}",
            ),
        ),
    ),
    ItemSemilla(
        code="cetro_bigquery",
        name="Cetro de BigQuery",
        description="Cristal de la Bóveda de los Mil Petabytes. Pesa poco y responde rápido, si sabes cuánto vas a leer.",
        slot=ItemSlot.WEAPON,
        rarity=ItemRarity.EPIC,
        origin=ItemOrigin.KNOWLEDGE,
        requirements=_condicion("mastery_gte", area=_area("bigquery"), value=80),
        requirement_facts=("mastery",),
        auto_grant=True,
        render_manifest=manifiesto("cetro_bigquery", CAPAS_POR_RANURA[ItemSlot.WEAPON]),
        icon_key="cetro_bigquery",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.MASTERY_GTE,
                area_slug="bigquery",
                target_value=Decimal("80.00"),
                label_template="Dominio de {area}: {current} / {target} %",
            ),
        ),
    ),
    ItemSemilla(
        code="escudo_data_engineer",
        name="Escudo del Data Engineer",
        description="Placas soldadas como las juntas de un acueducto. Aguanta el caudal de medianoche sin filtrar una gota.",
        slot=ItemSlot.OFFHAND,
        rarity=ItemRarity.LEGENDARY,
        origin=ItemOrigin.KNOWLEDGE,
        requirements=_condicion("path_completed", area=_area("data_engineering")),
        requirement_facts=("path",),
        auto_grant=True,
        render_manifest=manifiesto("escudo_data_engineer", CAPAS_POR_RANURA[ItemSlot.OFFHAND]),
        icon_key="escudo_data_engineer",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.PATH_COMPLETED,
                area_slug="data_engineering",
                target_count=1,
                label_template="Completa una ruta de {area}",
            ),
        ),
    ),
    ItemSemilla(
        code="baculo_maestria_ia",
        name="Báculo de la Maestría en IA",
        description="Coronado por la lente del Oráculo. No adivina el futuro: estima, y te obliga a medir cuánto se equivoca.",
        slot=ItemSlot.WEAPON,
        rarity=ItemRarity.LEGENDARY,
        origin=ItemOrigin.KNOWLEDGE,
        requirements={
            "all": [
                _condicion("path_completed", area=_area("inteligencia_artificial")),
                _condicion("mastery_gte", area=_area("inteligencia_artificial"), value=85),
            ]
        },
        requirement_facts=("path", "mastery"),
        auto_grant=True,
        render_manifest=manifiesto("baculo_maestria_ia", CAPAS_POR_RANURA[ItemSlot.WEAPON]),
        icon_key="baculo_maestria_ia",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.PATH_COMPLETED,
                position=0,
                area_slug="inteligencia_artificial",
                target_count=1,
                label_template="Completa una ruta de {area}",
            ),
            RequisitoSemilla(
                requirement_type=RequirementType.MASTERY_GTE,
                position=1,
                area_slug="inteligencia_artificial",
                target_value=Decimal("85.00"),
                label_template="Dominio de {area}: {current} / {target} %",
            ),
        ),
    ),
    ItemSemilla(
        code="tomo_erudito",
        name="Tomo del Erudito",
        description="Tres saberes encuadernados en un solo volumen. Premia la amplitud: nadie llega aquí por un único camino.",
        slot=ItemSlot.OFFHAND,
        rarity=ItemRarity.LEGENDARY,
        origin=ItemOrigin.KNOWLEDGE,
        requirements=_condicion("areas_mastered_gte", count=3),
        requirement_facts=("mastery",),
        auto_grant=True,
        render_manifest=manifiesto("tomo_erudito", CAPAS_POR_RANURA[ItemSlot.OFFHAND]),
        icon_key="tomo_erudito",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.AREAS_MASTERED_GTE,
                target_count=3,
                label_template="Conocimientos dominados: {current} / {target}",
            ),
        ),
    ),
    ItemSemilla(
        code="corona_del_maestro",
        name="Corona del Maestro",
        description="Cinco gemas, cinco territorios dominados. La única pieza mítica del Reino y la más difícil de merecer.",
        slot=ItemSlot.HEAD,
        rarity=ItemRarity.MYTHIC,
        origin=ItemOrigin.KNOWLEDGE,
        requirements=_condicion("areas_mastered_gte", count=5),
        requirement_facts=("mastery",),
        auto_grant=True,
        render_manifest=manifiesto("corona_del_maestro", CAPAS_POR_RANURA[ItemSlot.HEAD]),
        icon_key="corona_del_maestro",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.AREAS_MASTERED_GTE,
                target_count=5,
                label_template="Conocimientos dominados: {current} / {target}",
            ),
        ),
    ),
    ItemSemilla(
        code="tpl_capa_estudiante",
        name="Capa del Estudiante de {short_name}",
        description="Tela teñida con el color de la disciplina. Se gana al terminar la ruta entera, no antes.",
        slot=ItemSlot.CAPE,
        rarity=ItemRarity.RARE,
        origin=ItemOrigin.KNOWLEDGE,
        requirements=_condicion("path_completed", area=_area("self")),
        requirement_facts=("path",),
        auto_grant=True,
        render_manifest=manifiesto(
            "tpl_capa_estudiante",
            CAPAS_POR_RANURA[ItemSlot.CAPE],
            tinte={"channel": "category_color", "mode": "modulate"},
        ),
        icon_key="tpl_capa_estudiante",
        is_template=True,
        visibility=ItemVisibility.OWNER,
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.PATH_COMPLETED,
                area_slug="self",
                target_count=1,
                label_template="Completa una ruta de {area}",
            ),
        ),
    ),
    ItemSemilla(
        code="tpl_capa_maestro",
        name="Capa del Maestro de {short_name}",
        description="El mismo corte que la del estudiante, con el broche de maestría. Exige dominio sostenido, no una buena tarde.",
        slot=ItemSlot.CAPE,
        rarity=ItemRarity.EPIC,
        origin=ItemOrigin.KNOWLEDGE,
        requirements=_condicion("mastery_gte", area=_area("self"), value=80),
        requirement_facts=("mastery",),
        auto_grant=True,
        render_manifest=manifiesto(
            "tpl_capa_maestro",
            CAPAS_POR_RANURA[ItemSlot.CAPE],
            tinte={"channel": "category_color", "mode": "modulate"},
        ),
        icon_key="tpl_capa_maestro",
        is_template=True,
        visibility=ItemVisibility.OWNER,
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.MASTERY_GTE,
                area_slug="self",
                target_value=Decimal("80.00"),
                label_template="Dominio de {area}: {current} / {target} %",
            ),
        ),
    ),
    ItemSemilla(
        code="tpl_insignia_perfeccion",
        name="Insignia de la Perfección en {short_name}",
        description="Esmalte sin una sola burbuja. Un 100 % en una prueba, o dos de 95 %: el Reino no castiga un descuido.",
        slot=ItemSlot.ACCESSORY,
        rarity=ItemRarity.EPIC,
        origin=ItemOrigin.KNOWLEDGE,
        requirements={
            "any": [
                _condicion("assessment_score_gte", area=_area("self"), value=100),
                _condicion("assessment_score_gte", area=_area("self"), value=95, count=2),
            ]
        },
        requirement_facts=("assessment",),
        auto_grant=True,
        render_manifest=manifiesto(
            "tpl_insignia_perfeccion",
            ("accessory_body",),
            tinte={"channel": "category_color", "mode": "modulate"},
        ),
        icon_key="tpl_insignia_perfeccion",
        is_template=True,
        visibility=ItemVisibility.OWNER,
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.ASSESSMENT_SCORE_GTE,
                group_index=0,
                area_slug="self",
                target_value=Decimal("100.00"),
                target_count=1,
                label_template="Consigue {value} % en una evaluación de {area}",
            ),
            RequisitoSemilla(
                requirement_type=RequirementType.ASSESSMENT_SCORE_GTE,
                group_index=1,
                area_slug="self",
                target_value=Decimal("95.00"),
                target_count=2,
                label_template="Consigue {value} % en dos evaluaciones de {area}",
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# 8.4 Racha (`streak`, 4 ítems) — siempre sobre la MEJOR racha
# ---------------------------------------------------------------------------

_RACHA: tuple[ItemSemilla, ...] = (
    ItemSemilla(
        code="antorcha_constancia",
        name="Antorcha de la Constancia",
        description="Arde con aceite de siete noches. Una vez encendida, ningún día perdido vuelve a apagarla.",
        slot=ItemSlot.ACCESSORY,
        rarity=ItemRarity.UNCOMMON,
        origin=ItemOrigin.STREAK,
        requirements=_condicion("streak_gte", days=7, kind="best"),
        requirement_facts=("streak",),
        auto_grant=True,
        render_manifest=manifiesto("antorcha_constancia", ("accessory_body",)),
        icon_key="antorcha_constancia",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.STREAK_GTE,
                target_count=7,
                streak_kind=StreakKind.BEST,
                label_template="Racha: {current} / {target} días",
            ),
        ),
    ),
    ItemSemilla(
        code="botas_caminante",
        name="Botas del Caminante Incansable",
        description="Catorce jornadas seguidas grabadas en la suela. El camino ya no te pesa: te sostiene.",
        slot=ItemSlot.BOOTS,
        rarity=ItemRarity.RARE,
        origin=ItemOrigin.STREAK,
        requirements=_condicion("streak_gte", days=14, kind="best"),
        requirement_facts=("streak",),
        auto_grant=True,
        render_manifest=manifiesto("botas_caminante", CAPAS_POR_RANURA[ItemSlot.BOOTS]),
        icon_key="botas_caminante",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.STREAK_GTE,
                target_count=14,
                streak_kind=StreakKind.BEST,
                label_template="Racha: {current} / {target} días",
            ),
        ),
    ),
    ItemSemilla(
        code="capa_llamas_persistentes",
        name="Capa de las Llamas Persistentes",
        description="El fuego de treinta días cosido en el forro. Se ve de noche desde la muralla.",
        slot=ItemSlot.CAPE,
        rarity=ItemRarity.EPIC,
        origin=ItemOrigin.STREAK,
        requirements=_condicion("streak_gte", days=30, kind="best"),
        requirement_facts=("streak",),
        auto_grant=True,
        render_manifest=manifiesto("capa_llamas_persistentes", CAPAS_POR_RANURA[ItemSlot.CAPE]),
        icon_key="capa_llamas_persistentes",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.STREAK_GTE,
                target_count=30,
                streak_kind=StreakKind.BEST,
                label_template="Racha: {current} / {target} días",
            ),
        ),
    ),
    ItemSemilla(
        code="corona_fuego_eterno",
        name="Corona de Fuego Eterno",
        description="Cien días sin faltar. El Reino la reserva para quienes convirtieron el estudio en costumbre.",
        slot=ItemSlot.HEAD,
        rarity=ItemRarity.LEGENDARY,
        origin=ItemOrigin.STREAK,
        requirements=_condicion("streak_gte", days=100, kind="best"),
        requirement_facts=("streak",),
        auto_grant=True,
        render_manifest=manifiesto("corona_fuego_eterno", CAPAS_POR_RANURA[ItemSlot.HEAD]),
        icon_key="corona_fuego_eterno",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.STREAK_GTE,
                target_count=100,
                streak_kind=StreakKind.BEST,
                label_template="Racha: {current} / {target} días",
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# 8.5 Logro (`achievement`, 3 ítems)
# ---------------------------------------------------------------------------

_LOGRO: tuple[ItemSemilla, ...] = (
    ItemSemilla(
        code="pluma_primer_paso",
        name="Pluma del Primer Paso",
        description="La pluma con la que firmaste tu primera lección terminada. Pequeña, y la más difícil de conseguir dos veces.",
        slot=ItemSlot.ACCESSORY,
        rarity=ItemRarity.COMMON,
        origin=ItemOrigin.ACHIEVEMENT,
        requirements=_condicion("achievement_unlocked", achievement_id="ACH_FIRST_STEP"),
        requirement_facts=("achievement",),
        auto_grant=True,
        render_manifest=manifiesto("pluma_primer_paso", ("accessory_face",)),
        icon_key="pluma_primer_paso",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.ACHIEVEMENT_UNLOCKED,
                achievement_code="ACH_FIRST_STEP",
                label_template="Desbloquea el logro «Primer Paso»",
            ),
        ),
    ),
    ItemSemilla(
        code="escudo_primer_desafio",
        name="Escudo del Primer Desafío",
        description="Sostuvo tu primera prueba del Castillo y no se partió. Las siguientes ya no dan tanto miedo.",
        slot=ItemSlot.OFFHAND,
        rarity=ItemRarity.UNCOMMON,
        origin=ItemOrigin.ACHIEVEMENT,
        requirements=_condicion("achievement_unlocked", achievement_id="ACH_PASSED"),
        requirement_facts=("achievement",),
        auto_grant=True,
        render_manifest=manifiesto("escudo_primer_desafio", CAPAS_POR_RANURA[ItemSlot.OFFHAND]),
        icon_key="escudo_primer_desafio",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.ACHIEVEMENT_UNLOCKED,
                achievement_code="ACH_PASSED",
                label_template="Desbloquea el logro «Aprobado/a»",
            ),
        ),
    ),
    ItemSemilla(
        code="yelmo_veterano",
        name="Yelmo del Veterano",
        description="Abollado en diez niveles de servicio. Quien lo lleva ya no pregunta por dónde se empieza.",
        slot=ItemSlot.HEAD,
        rarity=ItemRarity.RARE,
        origin=ItemOrigin.ACHIEVEMENT,
        requirements=_condicion("level_gte", level=10),
        requirement_facts=("level",),
        auto_grant=True,
        render_manifest=manifiesto("yelmo_veterano", CAPAS_POR_RANURA[ItemSlot.HEAD], oculta=OCULTA_CABELLO),
        icon_key="yelmo_veterano",
        requisitos=(
            RequisitoSemilla(
                requirement_type=RequirementType.LEVEL_GTE,
                target_count=10,
                label_template="Nivel {current} / {target}",
            ),
        ),
    ),
)


#: Los 46 ítems del catálogo inicial (06c §8.6: 15 C · 10 PC · 8 R · 7 E · 5 L · 1 M).
ITEMS: tuple[ItemSemilla, ...] = _INICIALES + _TIENDA + _CONOCIMIENTO + _RACHA + _LOGRO


@dataclass(frozen=True, slots=True)
class ListadoTienda:
    """Una fila de `shop_listings` con el precio y el nivel que fija la rareza."""

    item_code: str
    price: int
    min_level: int
    is_featured: bool
    featured_order: int | None


def listados_tienda(cfg: ServicioConfig) -> list[ListadoTienda]:
    """Ofertas de la tienda; precio y nivel salen de `game_configs`, nunca del código.

    Se omite cualquier ítem cuya rareza no esté en `shop.sellable_rarities` o que no
    tenga precio (los míticos valen `null`): el catálogo puede crecer sin tocar esto.
    """
    precios = cfg.obtener_json("shop.price_by_rarity")
    minimos = cfg.obtener_json("shop.min_level_by_rarity")
    vendibles = {str(r) for r in cfg.obtener_lista("shop.sellable_rarities")}
    tope_destacados = cfg.obtener_int("shop.featured_max")

    filas: list[ListadoTienda] = []
    for item in ITEMS:
        if not item.en_tienda:
            continue
        rareza = item.rarity.value
        precio = precios.get(rareza)
        if rareza not in vendibles or precio is None:
            continue
        destacado = item.destacado is not None and item.destacado <= tope_destacados
        filas.append(
            ListadoTienda(
                item_code=item.code,
                price=int(precio),
                min_level=int(minimos.get(rareza, 1)),
                is_featured=destacado,
                featured_order=item.destacado if destacado else None,
            )
        )
    return filas


def por_codigo() -> dict[str, ItemSemilla]:
    """Índice `code -> ítem` del catálogo semilla."""
    return {item.code: item for item in ITEMS}
