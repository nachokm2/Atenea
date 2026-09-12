"""Semilla de `knowledge_areas` y `territories`: la taxonomía canónica del Reino.

Los siete conocimientos sembrados son exactamente los de `items.canonical_area_slugs`
(contrato §5.4): son las áreas que tienen ítem curado propio en el catálogo de §8.3 de
06c y las que la IA puede reconocer al clasificar una ruta creada por el usuario. Un
área creada al vuelo por alguien no es canónica y no aparece aquí.

Cada conocimiento tiene **un** territorio (relación 1:1): el nombre narrativo que se
dibuja en el mapa, su emblema (`icon_hint`) y la palabra clave que certifica que el
nombre poético sigue hablando del concepto real (`concept_keyword`). El *estado* del
territorio (con niebla, descubierto, dominado) no vive aquí: se deriva del progreso de
cada usuario.

`short_name` está acotado a 18 caracteres porque alimenta los nombres de los ítems
derivados ("Capa del Maestro de {short_name}").
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import KnowledgeCategory

__all__ = ["AREAS", "AreaSemilla", "por_slug"]


@dataclass(frozen=True, slots=True)
class AreaSemilla:
    """Un conocimiento canónico con su territorio en el mapa."""

    slug: str
    """Identificador canónico estable; coincide con `items.canonical_area_slugs`."""

    name: str
    short_name: str
    """Máximo 18 caracteres: se interpola en los nombres de ítems derivados."""

    category: KnowledgeCategory
    description: str
    icon_key: str
    accent_color: str
    """Color de la categoría en `#RRGGBB`."""

    territory_name: str
    """Nombre narrativo del territorio ("Castillo de las Consultas")."""

    territory_icon: str
    """Emblema del territorio: la pista visual que dibuja el mapa."""

    concept_keyword: str
    """Palabra clave que ancla el nombre narrativo al concepto real."""

    territory_description: str


#: Los siete conocimientos canónicos del MVP y sus territorios.
AREAS: tuple[AreaSemilla, ...] = (
    AreaSemilla(
        slug="sql",
        name="SQL",
        short_name="SQL",
        category=KnowledgeCategory.DATA,
        description=(
            "El lenguaje con el que se interroga a las bases de datos relacionales: "
            "seleccionar, filtrar, agrupar y unir tablas para responder preguntas."
        ),
        icon_key="scroll_query",
        accent_color="#4A90D9",
        territory_name="Castillo de las Consultas",
        territory_icon="castle",
        concept_keyword="consulta",
        territory_description=(
            "Una fortaleza de salones encadenados donde cada puerta responde solo a "
            "quien sabe formular la pregunta exacta. Sus archiveros guardan tablas "
            "que nadie ha unido todavía."
        ),
    ),
    AreaSemilla(
        slug="bigquery",
        name="BigQuery",
        short_name="BigQuery",
        category=KnowledgeCategory.DATA,
        description=(
            "El almacén analítico de Google Cloud: consultas sobre volúmenes enormes, "
            "particionado, agrupamiento y control del coste por byte leído."
        ),
        icon_key="vault_data",
        accent_color="#2E6FA7",
        territory_name="Bóveda de los Mil Petabytes",
        territory_icon="vault",
        concept_keyword="almacén",
        territory_description=(
            "Una cripta sin fondo donde la respuesta llega en segundos, pero cada "
            "byte leído se paga. Aquí se aprende a preguntar mucho gastando poco."
        ),
    ),
    AreaSemilla(
        slug="data_engineering",
        name="Ingeniería de Datos",
        short_name="Datos",
        category=KnowledgeCategory.DATA,
        description=(
            "El oficio de mover, limpiar y modelar datos: canalizaciones, orquestación, "
            "calidad, idempotencia y modelos analíticos que sobreviven al tiempo."
        ),
        icon_key="aqueduct",
        accent_color="#3E7C63",
        territory_name="Acueductos del Gran Caudal",
        territory_icon="aqueduct",
        concept_keyword="canalización",
        territory_description=(
            "Arcos de piedra que llevan el agua desde las fuentes hasta la ciudad. "
            "Si una junta falla, todo el Reino bebe turbio: los ingenieros del caudal "
            "vigilan cada tramo."
        ),
    ),
    AreaSemilla(
        slug="inteligencia_artificial",
        name="Inteligencia Artificial",
        short_name="IA",
        category=KnowledgeCategory.AI,
        description=(
            "Modelos que aprenden de los datos: aprendizaje automático, evaluación "
            "honesta, modelos de lenguaje y el criterio para saber cuándo no usarlos."
        ),
        icon_key="oracle_eye",
        accent_color="#8E6CC8",
        territory_name="Torre del Oráculo",
        territory_icon="tower",
        concept_keyword="modelo",
        territory_description=(
            "En lo alto, una máquina de vidrio predice el mañana a partir del ayer. "
            "Acierta a menudo; el aprendiz sabio aprende también a medir cuándo falla."
        ),
    ),
    AreaSemilla(
        slug="gcp",
        name="Google Cloud Platform",
        short_name="GCP",
        category=KnowledgeCategory.CLOUD,
        description=(
            "La nube de Google: proyectos, identidades y permisos, almacenamiento, "
            "cómputo gestionado y el coste como una decisión de diseño más."
        ),
        icon_key="sky_citadel",
        accent_color="#4C7BD9",
        territory_name="Ciudadela de las Nubes",
        territory_icon="cloud_keep",
        concept_keyword="nube",
        territory_description=(
            "Una fortaleza que flota y crece según quién la habite. Sus llaves no son "
            "de hierro sino de permisos, y la puerta mal cerrada cuesta oro cada noche."
        ),
    ),
    AreaSemilla(
        slug="python",
        name="Python",
        short_name="Python",
        category=KnowledgeCategory.PROGRAMMING,
        description=(
            "El lenguaje de propósito general del oficio de datos: tipos, estructuras, "
            "funciones, módulos y las bibliotecas con las que se analiza y se automatiza."
        ),
        icon_key="serpent_quill",
        accent_color="#D6A83A",
        territory_name="Foso de la Serpiente",
        territory_icon="forge",
        concept_keyword="lenguaje",
        territory_description=(
            "Un taller cálido donde la serpiente enseña a escribir poco y decir mucho. "
            "Quien la domina automatiza en una tarde lo que otros repiten cada semana."
        ),
    ),
    AreaSemilla(
        slug="business_intelligence",
        name="Business Intelligence",
        short_name="BI",
        category=KnowledgeCategory.BUSINESS,
        description=(
            "Convertir datos en decisiones: métricas bien definidas, modelado para el "
            "negocio, tableros que se leen de un vistazo y narrativa con evidencia."
        ),
        icon_key="banner_chart",
        accent_color="#C2703C",
        territory_name="Sala del Consejo",
        territory_icon="council_hall",
        concept_keyword="métrica",
        territory_description=(
            "La mesa donde se decide el destino del Reino. Aquí no gana quien habla "
            "más alto, sino quien trae la métrica bien definida y sabe explicarla."
        ),
    ),
)


def por_slug() -> dict[str, AreaSemilla]:
    """Índice `slug -> área` para resolver referencias del catálogo de ítems."""
    return {area.slug: area for area in AREAS}
