"""Qué pintar para cada objeto del catálogo, y dónde.

`vestir.py` sabe generar una capa; esto dice cuáles hay que generar. Los 46
objetos salen de `backend/app/seeds/items.py`, que es la fuente: aquí no se
inventa ninguno ni se cambia ninguno de sitio.

## De dónde sale cada descripción

Del propio catálogo. El texto de la semilla es narrativo, pero lleva dentro casi
todo lo visual que hace falta —«mil escamas cosidas una a una», «paño gris sobre
malla ligera, con el emblema del Muro al pecho»—, así que el prompt lo repite en
vez de inventar otra cosa. Un objeto descrito aquí de forma distinta a como lo
describe el Reino sería un objeto distinto, y el aprendiz leería una cosa y
vería otra.

## Las dos capas de una capa

`CAPAS_POR_RANURA` en la semilla le da a la ranura CAPE dos capas de dibujado:
`cape_back` (z=20, por detrás del cuerpo) y `cape_front` (z=140, por delante).
No son dos dibujos: son dos trozos del mismo. El modelo pinta la capa puesta, y
el corte se hace después por geometría —lo que queda fuera de la silueta del
cuerpo cuelga por detrás, lo que queda dentro es el embozo y el broche—, que es
gratis y no se puede equivocar.

## Lo que no está aquí

Las armas y los escudos, que son quince. No se llevan puestos: se sostienen, y su
sitio no es una franja del cuerpo sino un rectángulo al lado de la mano, con
lienzo vacío alrededor. `zona_editable` corta contra la silueta, así que ese
rectángulo no se puede expresar todavía. Mientras tanto siguen saliendo de ficha
al margen, que es justo para lo que se dejó ese camino.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Pieza:
    """Un objeto del catálogo y cómo se dibuja."""

    codigo: str
    """`code` del ítem en la semilla. Da nombre al archivo."""

    capa: str
    """Capa de la pila de dibujado (06c §2.3). Da la otra mitad del nombre."""

    banda: str
    """Franja de `vestir.BANDAS` donde el modelo puede pintar."""

    prompt: str
    """Qué prenda pintar, en los términos en que el Reino la describe."""

    @property
    def nombre(self) -> str:
        """El archivo, que es lo que el servidor manda en `src` sin extensión."""
        return f"{self.codigo}_{self.capa}"


# ---------------------------------------------------------------------------
# Cabeza
# ---------------------------------------------------------------------------

CABEZA: tuple[Pieza, ...] = (
    Pieza(
        "capucha_viajero",
        "head",
        "cabeza",
        "una capucha de lana basta echada sobre la cabeza, de color pardo, con la "
        "caída gruesa de la lana mojada. Deja la cara descubierta",
    ),
    Pieza(
        "yelmo_guardia",
        "head",
        "cabeza",
        "un yelmo de acero pulido con nasal recto que baja entre los ojos. Deja la "
        "cara visible a los lados del nasal",
    ),
    Pieza(
        "sombrero_estrellado",
        "head",
        "cabeza",
        "un sombrero de ala ancha azul noche con constelaciones bordadas en hilo de "
        "plata. Deja la cara descubierta bajo el ala",
    ),
    Pieza(
        "corona_laurel_plata",
        "head",
        "cabeza",
        "una corona de hojas de laurel de plata batida, finísima y ligera, ceñida "
        "sobre el pelo. Deja la cara entera descubierta",
    ),
    Pieza(
        "corona_del_maestro",
        "head",
        "cabeza",
        "una corona de oro con cinco gemas engastadas al frente, una por territorio "
        "dominado. Deja la cara entera descubierta",
    ),
    Pieza(
        "corona_fuego_eterno",
        "head",
        "cabeza",
        "una corona de hierro con llamas doradas que se alzan de los engastes, "
        "ardiendo sin consumirse. Deja la cara entera descubierta",
    ),
    Pieza(
        "yelmo_veterano",
        "head",
        "cabeza",
        "un yelmo de acero gastado y abollado por diez niveles de servicio, con la "
        "pintura saltada en los bordes. Deja la cara visible",
    ),
)

# ---------------------------------------------------------------------------
# Cuerpo
# ---------------------------------------------------------------------------

CUERPO: tuple[Pieza, ...] = (
    Pieza(
        "jubon_recluta",
        "outfit",
        "cuerpo",
        "un jubón de cuero endurecido color tabaco con remaches de hierro en el "
        "pecho y los hombros",
    ),
    Pieza(
        "tunica_iniciacion",
        "outfit",
        "cuerpo",
        "una túnica de lino crudo sencilla, sin adornos, ceñida con un cordón "
        "trenzado a la cintura",
    ),
    Pieza(
        "chaleco_explorador",
        "outfit",
        "cuerpo",
        "un chaleco de viaje verde oliva lleno de bolsillos con solapa, correas "
        "cruzadas al pecho y una cuerda enrollada al hombro",
    ),
    Pieza(
        "sobreveste_vigia",
        "outfit",
        "cuerpo",
        "una sobreveste de paño gris sobre malla ligera, con el emblema de un muro "
        "de piedra bordado al pecho",
    ),
    Pieza(
        "cota_escamas_cobre",
        "outfit",
        "cuerpo",
        "una cota de escamas de cobre, mil escamas pequeñas solapadas una sobre "
        "otra, con brillo cálido de metal viejo",
    ),
    Pieza(
        "armadura_placas",
        "outfit",
        "cuerpo",
        "una armadura de placas de acero pulido como un espejo, con hombreras "
        "redondeadas, peto, juntas articuladas y faldar corto",
    ),
    Pieza(
        "tunica_constelaciones",
        "outfit",
        "cuerpo",
        "una túnica de terciopelo azul profundo con constelaciones bordadas en hilo "
        "de plata por el pecho y las mangas",
    ),
)

# ---------------------------------------------------------------------------
# Capa
# ---------------------------------------------------------------------------

CAPA: tuple[Pieza, ...] = (
    Pieza(
        "capa_lana_gris",
        "cape",
        "capa",
        "una capa de lana gris sencilla prendida a los hombros, que cae por detrás "
        "hasta media pantorrilla",
    ),
    Pieza(
        "capa_carmesi",
        "cape",
        "capa",
        "una capa carmesí de tinte intenso y caída impecable, prendida a los "
        "hombros con dos broches dorados",
    ),
    Pieza(
        "capa_plumas_nocturnas",
        "cape",
        "capa",
        "una capa de plumas de cuervo cosidas en escama, negra y absorbente, que "
        "apenas devuelve la luz",
    ),
    Pieza(
        "capa_llamas_persistentes",
        "cape",
        "capa",
        "una capa oscura con llamas anaranjadas cosidas en el forro, que asoman por "
        "el borde y por la abertura",
    ),
    Pieza(
        "tpl_capa_estudiante",
        "cape",
        "capa",
        "una capa de tela lisa de un solo color, sin adornos, prendida al hombro "
        "con un broche redondo sencillo",
    ),
    Pieza(
        "tpl_capa_maestro",
        "cape",
        "capa",
        "una capa de tela lisa de un solo color con el mismo corte que la del "
        "estudiante, rematada con un broche de maestría labrado y ribete dorado",
    ),
)

# ---------------------------------------------------------------------------
# Guantes
# ---------------------------------------------------------------------------

GUANTES: tuple[Pieza, ...] = (
    Pieza(
        "guantes_cuero",
        "gloves",
        "manos",
        "unos guantes de cuero curtido color avellana, sin adornos, ajustados a la "
        "mano",
    ),
    Pieza(
        "guanteletes_acero",
        "gloves",
        "manos",
        "unos guanteletes de acero articulados placa sobre placa, con los nudillos "
        "reforzados",
    ),
)

# ---------------------------------------------------------------------------
# Botas
# ---------------------------------------------------------------------------

BOTAS: tuple[Pieza, ...] = (
    Pieza(
        "botas_camino",
        "boots",
        "botas",
        "unas botas de cuero de caña media con la suela gastada y los cordones "
        "nuevos, sin adornos",
    ),
    Pieza(
        "sandalias_erudito",
        "boots",
        "botas",
        "unas sandalias de cuero blando con tiras cruzadas al tobillo, de suela "
        "fina, para andar por una biblioteca",
    ),
    Pieza(
        "botas_reforzadas",
        "boots",
        "botas",
        "unas botas altas de cuero oscuro con puntera de hierro, suela doble y "
        "hebillas en la caña",
    ),
    Pieza(
        "botas_caminante",
        "boots",
        "botas",
        "unas botas de viaje muy gastadas, de caña alta y cuero ablandado por el "
        "uso, con catorce muescas grabadas en la caña",
    ),
)

# ---------------------------------------------------------------------------
# Accesorios
#
# La única ranura cuyos objetos no comparten sitio en el cuerpo: un morral
# cuelga de la cadera, unos anteojos van en la cara, una insignia en el pecho y
# una antorcha en la mano. Por eso la banda va por pieza y no por ranura.
# ---------------------------------------------------------------------------

ACCESORIOS: tuple[Pieza, ...] = (
    Pieza(
        "morral_estudiante",
        "accessory_body",
        "cadera",
        "un morral de cuero remendado colgado del costado con una correa gastada, "
        "reventando de pergaminos enrollados",
    ),
    Pieza(
        "anteojos_erudito",
        "accessory_body",
        "cara",
        "unos anteojos redondos de montura de latón sobre el puente de la nariz, "
        "con los cristales limpios. No cambies los ojos ni la expresión",
    ),
    Pieza(
        "tpl_insignia_perfeccion",
        "accessory_body",
        "pecho",
        "una insignia redonda de esmalte liso prendida en el pecho, a la izquierda, "
        "con el esmalte sin una sola burbuja",
    ),
    Pieza(
        "antorcha_constancia",
        "accessory_body",
        "manos",
        "una antorcha corta empuñada en la mano, con la llama viva y el mango "
        "ennegrecido por el aceite",
    ),
    Pieza(
        "pluma_primer_paso",
        "accessory_body",
        "manos",
        "una pluma de escribir pequeña sostenida entre los dedos, de barba clara y "
        "punta entintada",
    ),
)

TODAS: tuple[Pieza, ...] = CABEZA + CUERPO + CAPA + GUANTES + BOTAS + ACCESORIOS

#: Lo que se genera primero para comprobar las bandas antes de la tanda entera.
#:
#: Una por banda, y cada una elegida por ser la más exigente de la suya: la
#: armadura de placas porque es lo más alejado de una camiseta; la capa porque
#: es la que hay que partir en dos; los anteojos porque tocan la cara, que es lo
#: único que no se puede tocar; la antorcha porque tiene que salir de la mano sin
#: mano que la sostenga dibujada aparte.
PILOTO: tuple[str, ...] = (
    "armadura_placas",
    "capa_carmesi",
    "yelmo_guardia",
    "guanteletes_acero",
    "botas_camino",
    "anteojos_erudito",
)


def por_codigo(codigo: str) -> Pieza:
    """El objeto con ese código. Tolera espacios y saltos de línea alrededor.

    Lo del `strip()` no es mimo: la lista de pendientes se genera con un
    redirección en Windows, que escribe CRLF, y cada código llegaba con un ``
    pegado detrás. Con la salida filtrada, una tanda de veinticinco piezas
    terminó con código 0 y sin generar ninguna.
    """
    limpio = codigo.strip()
    for pieza in TODAS:
        if pieza.codigo == limpio:
            return pieza
    raise KeyError(f"{limpio!r} no está en el catálogo de piezas.")
