"""Genera capas de equipo vistiendo a la figura que ya existe.

El problema que resuelve: el arte de Atenea no se puede apilar. Las seis figuras
base son ilustraciones terminadas y **ya vestidas**, y las piezas del catálogo son
fichas de producto, cada una recortada a su propio marco. No comparten lienzo ni
ancla, así que no hay forma de poner una encima de otra.

La salida de esto sí: capas RGBA de 1024×1024 con la pieza en su sitio y
transparencia alrededor, que es lo que el servidor ya sabe describir desde que
`_capas_de` emite `key`, `z`, `src` y el rectángulo.

## Por qué se genera ENCIMA de la figura y no aparte

Por dos razones, y las dos importan igual.

La primera es el **estilo**. Pedirle a un modelo «una coraza en estilo anime con
contorno de tinta» produce algo parecido al arte de Atenea, no el arte de Atenea.
Editando la ilustración real, el estilo no hay que describirlo: está en la imagen
que se le entrega.

La segunda es el **encaje**. Una pieza dibujada aparte hay que colocarla después, y
para eso harían falta anclas y escalas por pieza que no existen en ninguna parte.
Una pieza que nace pintada sobre el cuerpo ya está colocada: nunca se movió.

## El pegado de vuelta no es opcional

`gpt-image` no respeta la máscara: devuelve la imagen entera recreada. En el
piloto cambió las mangas remangadas por mangas largas y puso fondo negro, todo
fuera de la zona pedida. Por eso se compone a mano: de la respuesta se toma
**solo lo de dentro de la máscara** y el resto es la figura original, píxel a
píxel. Sin ese paso, cada pieza traería consigo una versión ligeramente distinta
del personaje.

## El fondo se quita por conectividad, no por umbral

El modelo devuelve fondo negro, y el contorno de tinta de la pieza también es
casi negro. Un umbral se comería el contorno. Se marca como fondo lo oscuro
**conectado al borde** de la imagen, que es la misma técnica que ya usa
`preparar_arte.py` con el damero; y después se encoge un poco esa máscara, porque
el contorno toca el fondo y si no se pierde y el borde queda dentado.

## Uso

    python scripts/vestir.py --figura base_femenino_001 --ranura cuerpo \\
        --prompt "coraza de placas de acero con hombreras y faldar corto"

Necesita `OPENAI_API_KEY` en el `.env` de la raíz. Cada llamada cuesta céntimos.
Sin `--aplicar` no llama al modelo: solo escribe la figura normalizada y la
máscara, para mirar la zona antes de gastar.
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from piezas import Pieza, por_codigo
from PIL import Image, ImageFilter
from scipy import ndimage

RAIZ = Path(__file__).resolve().parent.parent
FIGURAS = RAIZ / "app" / "assets" / "arte" / "personajes"
SALIDA = RAIZ / "arte" / "capas"

#: Lienzo maestro del avatar (06c §2.4).
LIENZO = 1024

#: Alto de la figura dentro del lienzo y línea de suelo. Con estos dos números
#: las seis figuras alinean la coronilla en y=52-53: un píxel de dispersión.
ALTO_FIGURA = 940
BASE_Y = 990

#: Umbral por debajo del cual un píxel cuenta como fondo candidato.
NEGRO = 48

#: El fondo que se le pide al modelo, y que no aparece en el arte de Atenea.
#:
#: Sin pedirlo, el modelo devuelve fondo negro, y entonces separar la figura es
#: adivinar: su contorno de tinta es tan oscuro como el fondo, un umbral se come
#: el contorno y encogerlo deja el borde dentado en las puntas del pelo. Con un
#: magenta plano la separación deja de ser por luminosidad y pasa a ser por
#: color, que sí es inequívoco.
FONDO = "magenta saturado y plano (#FF00FF), sin degradados ni sombras"

MODELO = "gpt-image-2"

#: Lo que se le repite al modelo en cada llamada.
#:
#: No es una cortesía: sin esto se va. Pidiéndole la figura femenina en ropa
#: interior devolvió otra persona, aerografiada, sin contorno de tinta y con
#: proporciones de ocho cabezas en vez de las seis y media del arte de Atenea.
#: Los rasgos del estilo van nombrados uno a uno porque "el mismo estilo" no
#: significa nada para un modelo que no ve la ilustración como referencia de
#: estilo, sino como una imagen que hay que editar.
ESTILO = (
    "Estilo de ilustración obligatorio, idéntico al de la imagen de partida: "
    "contorno de tinta oscura de grosor constante alrededor de cada forma, "
    "sombreado plano en dos o tres tonos planos por celdas, sin aerógrafo, sin "
    "degradados suaves y sin brillos especulares. Proporciones de seis cabezas y "
    "media, no alargadas. No cambies la cara, el peinado, el tono de piel, las "
    "manos, la altura ni la pose: los brazos siguen caídos a los costados."
)


#: Sobre qué figura se generan las piezas de cada familia.
#:
#: Una sola, porque dentro de una familia el cuerpo es casi el mismo y hacer tres
#: juegos sería pagar tres veces por el mismo dibujo. La elegida es la **mediana**
#: de su familia, no la primera.
#:
#: Está medido sobre los cuerpos ya desnudos, y midiendo el **torso solo**: a la
#: altura del pecho los brazos se funden con él, y un brazo más separado infla el
#: número sin que la pechera cambie de talla. Estas son las filas donde los tres
#: cuerpos tienen los brazos sueltos, en anchura de torso:
#:
#:     dy          001    002    003
#:     hombros     238    256    281
#:     cintura     158    177    180
#:     cadera      183    193    198
#:
#: La 002 es la mediana en las tres. Generando sobre ella, ninguna figura se
#: desvía más de unos 12 px por lado —unos 3 dp en pantalla—; generando sobre un
#: extremo se dobla. Y el sentido del error importa: una pieza estrecha deja
#: asomar el cuerpo por los hombros, que es el fallo que se ve.
#:
#: Aparte de esto, el modelo tiende a mejorar el cuerpo que destapa: la 003 salió
#: primero con 34 px más de hombro por lado que sus hermanas. `DESNUDEZ` se lo
#: pide expresamente y lo baja, pero no lo quita del todo.
CANONICA: dict[str, str] = {
    "masculino": "base_masculino_002",
    "femenino": "base_femenino_002",
}

#: Lo que se le añade solo al generar una pieza.
#:
#: Sin esto viste al personaje. Pidiéndole una capa carmesí sobre el cuerpo en
#: ropa interior devolvió, además de la capa, una túnica negra, un cinturón y un
#: pantalón marrón: la banda de la capa abarca casi todo el cuerpo, y un cuerpo
#: en camiseta le parece algo que hay que terminar de vestir.
SOLO_LA_PIEZA = (
    "Añade ÚNICAMENTE esa pieza. Todo lo demás se queda exactamente como está: "
    "el personaje sigue en camiseta sin mangas blanca y pantalón corto gris, y "
    "no le pongas ninguna otra prenda, ni túnica, ni cinturón, ni pantalón, ni "
    "nada que no se te haya pedido."
)

#: Y esto, solo a lo que no va en los pies.
#:
#: Iba dentro de `SOLO_LA_PIEZA`, junto al resto, y se volvió contra sí mismo:
#: estaba ahí para que las capas dejaran de traer botas de regalo, pero también
#: se lo decía a las botas. Pidiéndole unas botas de camino sobre la figura
#: femenina devolvió los pies descalzos, obedeciendo. Dos de los cuatro pares
#: salieron así y un tercero con una sola bota.
DESCALZO = (
    " Sigue DESCALZO, sin botas ni sandalias, y con los brazos y las piernas "
    "desnudos."
)

#: Lo que se le añade solo al desnudar.
#:
#: Quitar ropa le invita a mejorar el cuerpo que aparece debajo, y lo hace: el
#: masculino 003 salió 30 px más ancho de pecho por lado que sus dos hermanos,
#: la misma diferencia que hay entre familias. Eso rompe lo que abarata el
#: catálogo entero —un juego de piezas por familia, porque dentro de una familia
#: el cuerpo es el mismo—, y obligaría a tres juegos por familia en vez de uno.
DESNUDEZ = (
    "Conserva EXACTAMENTE la misma complexión y la misma anchura de hombros, "
    "pecho, cintura y piernas que tiene la figura vestida. No lo hagas más "
    "musculoso, ni más ancho, ni más atlético: debajo de la ropa hay el mismo "
    "cuerpo, ni uno mejor ni uno distinto."
)


@dataclass(frozen=True, slots=True)
class Banda:
    """Franja vertical donde puede pintar una ranura, medida desde la coronilla.

    Los límites no son estéticos: la línea de ojos cae en y≈195 desde la
    coronilla, así que nada de cabeza puede bajar de ahí sin taparle la cara al
    aprendiz, que es su identidad.
    """

    desde: int
    hasta: int
    holgura: int = 6

    relleno: bool = False
    """Rellena cada fila de borde a borde de la silueta, huecos incluidos.

    Solo para desnudar, y hace falta de verdad. La figura femenina vestida está
    de piernas abiertas —a media pantorrilla, las botas ocupan x 389-444 y
    601-657—, y el cuerpo desnudo que devuelve el modelo tiene las piernas mucho
    más juntas y estrechas: x 452-478 y 543-569. O sea, justo en el hueco de
    entre medias, que en una zona hecha de la silueta no existe. Las piernas se
    recortaban enteras y la figura acababa en una punta a la altura de la rodilla.
    """

    protege_cara: bool = False
    """Saca la cara de la zona editable.

    Los siete objetos de cabeza del catálogo dicen «deja la cara descubierta», y
    esto es no tener que fiarse de que el modelo lo lea: sin cara editable, un
    yelmo o una capucha tienen que dibujarse alrededor, que es lo que hacen los
    de verdad. La cara del aprendiz es su identidad; el resto de la cabeza, no.
    """

    solo_extremos: bool = False
    """Se queda con el primer trozo de cada fila y el último, y suelta el resto.

    A la altura de las manos, la fila son tres cosas: mano, cadera, mano. Una
    banda que las una deja al modelo repintar el pantalón cuando lo que se le
    pidió fueron unos guantes.
    """

    mano: str | None = None
    """`"diestra"` o `"zurda"`: hace de la banda un rectángulo junto a esa mano.

    Lo que se empuña no se lleva puesto, y por eso no cabe en una franja del
    cuerpo: una espada es sobre todo hoja, y la hoja está en el aire, al lado de
    la figura, donde la silueta no llega. Con esta bandera la zona deja de ser
    «la silueta recortada a unas filas» y pasa a ser un rectángulo centrado en la
    mano, del que se descuenta el cuerpo salvo en la propia mano, para que la
    empuñadura se vea agarrada y la hoja tenga aire.

    «Diestra» y «zurda» son desde quien mira, que es como ya lo hace el dibujo
    vectorial de reserva: el arma a la derecha de la imagen y el escudo a la
    izquierda.
    """

    ancho_maximo: int = 10_000
    """Descarta un trozo más ancho que esto, en píxeles.

    Con `solo_extremos`, una fila por debajo de las manos tiene por extremos las
    dos piernas, que son mucho más anchas que una mano. Sin este tope, la banda
    se derrama pierna abajo en cuanto se pasa una fila.
    """


BANDAS: dict[str, Banda] = {
    # La pasada que deja al aprendiz en ropa interior. Tiene que ir **antes**
    # que cualquier pieza: la figura de partida viene vestida, y una pieza más
    # estrecha que la prenda pintada debajo deja la vieja asomando por los
    # lados. Se vio en el piloto de las botas.
    #
    # La máscara va ceñida a la silueta aunque la composición luego se quede con
    # la imagen entera. Es lo único que ata al modelo al personaje: dándole el
    # lienzo entero dibujó **otra persona** —otra cara, otra altura y los brazos
    # cruzados en vez de a los costados—, y una pose distinta invalida de golpe
    # todas las piezas que se pinten después.
    # Empieza en el cuello y no en los hombros, y eso importa más de lo que
    # parece: por ahí pasa la costura entre la cabeza que se conserva y el cuerpo
    # que dibuja el modelo. Cortando en dy 195 la costura cae en los hombros, y
    # ahí las dos imágenes no coinciden —el cuello se ensancha de golpe y el pelo
    # salta—, así que se veía una raya cruzando el pecho. Medido sobre el cuerpo
    # desnudo, el cuello es la fila más estrecha: dy 165-180, 73 px de ancho.
    # Ahí el corte es piel contra piel.
    "base": Banda(relleno=True, desde=178, hasta=970, holgura=3),
    # Y las mismas dos, por tramos, para cuando de una sola pasada se desvía.
    # Cuanta más superficie se le da al modelo, más se inventa: con el lienzo
    # entero dibujó otra persona; con el cuerpo entero, una figura más alta y
    # estrecha que la silueta, que la máscara luego recorta a lo largo. Un tramo
    # corto tiene tan poco margen que no le queda sitio donde desviarse.
    "base_torso": Banda(relleno=True, desde=195, hasta=470, holgura=3),
    "base_piernas": Banda(relleno=True, desde=440, hasta=970, holgura=3),
    # Medido sobre el cuerpo desnudo, bajando fila a fila desde la coronilla: la
    # cabeza se ensancha hasta dy≈80, se estrecha hasta el cuello en dy 165-180 y
    # los hombros arrancan de golpe en dy 195. La banda anterior llegaba a 200 y
    # se metía en los hombros.
    # Holgura grande, y no por descuido. La banda es la silueta ensanchada, así
    # que con poca holgura una pieza solo puede dibujarse pegada a la cabeza: el
    # sombrero de ala ancha salió un pegote y la capucha acabó pareciendo otro
    # peinado, porque el ala y la caída no tenían dónde salir. Cincuenta y seis
    # píxeles es el ancho de un ala.
    "cabeza": Banda(desde=-40, hasta=180, holgura=14, protege_cara=True),
    "cuerpo": Banda(desde=215, hasta=455),
    "botas": Banda(desde=700, hasta=960, holgura=4),
    "capa": Banda(desde=140, hasta=800, holgura=10),
    # Las manos, medidas sobre la figura canónica: la mano es el ensanchamiento
    # del final del brazo —de 15 px de antebrazo en dy 445 a 37 en dy 505— y ahí
    # se acaba. `solo_extremos` suelta el trozo del medio de cada fila, que a esa
    # altura es la cadera: sin eso, al pedir unos guantes el modelo repinta el
    # pantalón.
    #
    # Ojo con esta banda más que con ninguna. Los brazos no miden lo mismo en las
    # tres figuras de la familia: la mano está en dy 480-515 en la 002 y en dy
    # 500-545 en la 001, treinta píxeles más abajo. En una bota o una pechera esa
    # diferencia se pierde; en un guante, que mide cuarenta píxeles, es casi su
    # propio tamaño. Si al verlo en pantalla el guante flota sobre la mano, la
    # salida es generar las cuatro piezas de mano por figura y no por familia:
    # son cuatro objetos, no treinta y uno.
    "manos": Banda(desde=462, hasta=548, holgura=3, solo_extremos=True, ancho_maximo=60),
    # Lo que se empuña, que no es lo mismo que lo que se calza en la mano. Una
    # antorcha es sobre todo mango, y un guante no: ciñendo la banda a la mano,
    # la antorcha y la pluma salieron invisibles porque no tenían dónde estar.
    "empunado": Banda(desde=400, hasta=600, holgura=14, solo_extremos=True, ancho_maximo=48),
    # Lo que se empuña de verdad: un arma en la diestra y un escudo en la zurda.
    # Sus límites son relativos al centro de la mano, no a la coronilla, porque
    # es la mano la que sostiene la pieza. Una espada sube mucho más de lo que
    # baja: la hoja va hacia arriba y el pomo queda apenas por debajo del puño.
    # Cuatrocientos píxeles por arriba, que con la mano a la altura de la cadera
    # deja la punta por encima de la cabeza; con trescientos treinta la hoja
    # llegaba al techo de la banda y salía cortada a ras.
    "arma": Banda(desde=-400, hasta=230, mano="diestra"),
    "escudo": Banda(desde=-200, hasta=200, mano="zurda"),
    # La cara, y solo para los anteojos, que son la única pieza del catálogo que
    # la toca. Iba de 150 a 215, que sobre el cuerpo desnudo es el cuello y los
    # hombros: los 195 de «línea de ojos» venían de otra escala. Con la cabeza
    # entre dy 0 y 160, los ojos caen hacia dy 85-100.
    "cara": Banda(desde=70, hasta=125, holgura=2),
    # El pecho, para lo que se prende encima sin ser prenda: una insignia.
    "pecho": Banda(desde=235, hasta=340, holgura=3),
    # La cadera y el costado, para lo que cuelga: un morral, una bolsa.
    "cadera": Banda(desde=370, hasta=520, holgura=5),
}


def clave_openai() -> str:
    """Lee la llave del `.env` de la raíz. Nunca se imprime."""
    env = RAIZ / ".env"
    for linea in env.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*OPENAI_API_KEY\s*=\s*(.*)$", linea)
        if m and m.group(1).strip():
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit("Falta OPENAI_API_KEY en el .env de la raíz.")


def normalizar(nombre: str) -> Image.Image:
    """Lleva una figura al lienzo maestro, centrada y a la altura canónica."""
    ruta = FIGURAS / f"{nombre}.webp"
    if not ruta.exists():
        raise SystemExit(f"No existe {ruta}")
    im = Image.open(ruta).convert("RGBA")
    im = im.crop(im.split()[3].getbbox())
    escala = ALTO_FIGURA / im.height
    im = im.resize((max(1, round(im.width * escala)), ALTO_FIGURA), Image.LANCZOS)
    hoja = Image.new("RGBA", (LIENZO, LIENZO), (0, 0, 0, 0))
    hoja.paste(im, ((LIENZO - im.width) // 2, BASE_Y - ALTO_FIGURA), im)
    return hoja


def figura_de_partida(nombre: str, ranura: str) -> Image.Image:
    """La desnuda si ya se generó; si no, la ilustración original.

    Las piezas se pintan sobre el cuerpo desnudo, nunca sobre la ilustración
    vestida: si no, cada capa arrastra la ropa de fábrica por debajo.
    """
    desnuda = SALIDA / nombre / "base.png"
    # `base` rehace el cuerpo desde la ilustración original; los tramos se
    # encadenan sobre lo que ya haya desnudo.
    if ranura != "base" and desnuda.exists():
        return Image.open(desnuda).convert("RGBA")
    return normalizar(nombre)


def coronilla(figura: Image.Image) -> int:
    """Primera fila con cuerpo. Es el origen de todas las medidas."""
    alfa = figura.split()[3]
    return next(
        y for y in range(LIENZO) if any(alfa.getpixel((x, y)) > 40 for x in range(0, LIENZO, 3))
    )


def zona_editable(figura: Image.Image, ranura: str) -> np.ndarray:
    """Silueta ensanchada, recortada a la banda de la ranura."""
    banda = BANDAS[ranura]
    alfa = np.array(figura.split()[3]) > 40
    top = coronilla(figura)

    if banda.mano:
        return _junto_a_la_mano(alfa, top, banda)

    # Soltar el trozo central va **antes** de ensanchar, no después: la
    # dilatación de doce píxeles salva el hueco entre el brazo y la cadera, así
    # que la fila pasa a ser un solo trozo y el filtro la descartaba entera. Se
    # quedaba en cero píxeles editables.
    util = _solo_los_extremos(alfa, banda) if banda.solo_extremos else alfa

    cuerpo = ndimage.binary_dilation(util, structure=np.ones((3, 3)), iterations=banda.holgura * 4)
    if banda.relleno:
        cuerpo = _de_borde_a_borde(cuerpo)
    filas = np.zeros_like(cuerpo)
    arriba = max(0, top + banda.desde)
    abajo = min(LIENZO, top + banda.hasta)
    filas[arriba:abajo, :] = True
    zona = cuerpo & filas

    if banda.solo_extremos:
        # Ensanchar alrededor de la mano vuelve a alcanzar la cadera —el hueco
        # entre las dos es de unos cuarenta píxeles y la holgura de una banda de
        # empuñar es mayor—, así que se le quita lo que sea cuerpo y no se
        # eligió. La banda puede crecer hacia el lienzo vacío, que es donde va el
        # mango de una antorcha, y nunca sobre el pantalón.
        zona &= ~(alfa & ~util)

    if banda.protege_cara:
        zona &= ~_la_cara(alfa, top)
    return zona


def _de_borde_a_borde(mascara: np.ndarray) -> np.ndarray:
    """Cada fila, del primer píxel al último; lo de en medio se da por dentro."""
    lleno = np.zeros_like(mascara)
    for y in np.where(mascara.any(axis=1))[0]:
        xs = np.where(mascara[y])[0]
        lleno[y, xs.min() : xs.max() + 1] = True
    return lleno


def _centro_de_la_mano(alfa: np.ndarray, top: int, cual: str) -> tuple[int, int]:
    """Dónde cae una mano, medido sobre la propia figura.

    La mano es el trozo lateral de las filas donde el brazo ya se ha separado del
    torso: entre ocho y sesenta píxeles de ancho, que la distingue de una pierna.
    Se promedian varias filas porque una sola puede caer en un dedo.
    """
    centros: list[int] = []
    filas: list[int] = []
    for dy in range(480, 550, 10):
        y = top + dy
        if y >= LIENZO:
            break
        etiquetas, cuantos = ndimage.label(alfa[y])
        trozos = []
        for i in range(1, cuantos + 1):
            xs = np.where(etiquetas == i)[0]
            if 8 < xs.size < 60:
                trozos.append((int(xs.min()), int(xs.max())))
        if len(trozos) < 2:
            continue
        izq, der = trozos[0], trozos[-1]
        # «Diestra» es la derecha de quien mira, que es donde el dibujo
        # vectorial de reserva lleva poniendo el arma desde siempre.
        elegido = der if cual == "diestra" else izq
        centros.append((elegido[0] + elegido[1]) // 2)
        filas.append(y)
    if not centros:
        # Sin manos reconocibles, el sitio de siempre: a la altura de la cadera y
        # al borde de la figura.
        ancho = np.where(alfa.any(axis=0))[0]
        x = int(ancho.max()) if cual == "diestra" else int(ancho.min())
        return x, top + 510
    return sum(centros) // len(centros), sum(filas) // len(filas)


def _junto_a_la_mano(alfa: np.ndarray, top: int, banda: Banda) -> np.ndarray:
    """Un rectángulo alrededor de una mano, con el cuerpo dentro.

    Con el cuerpo dentro **a propósito**, aunque la primera versión lo
    descontaba. Un arma no está solo al lado de la figura: se empuña, y la hoja
    sube por delante del brazo y a veces del torso. Descontando el cuerpo, de una
    espada de entrenamiento solo sobrevivía el trozo que caía en lienzo vacío, y
    de un arco de fresno la punta. El modelo las había dibujado enteras.

    Lo que descontaba el cuerpo era el miedo a que pedir una espada acabara
    repintando la cadera. De eso se encarga ya `_lo_que_cambio`, que compara con
    la figura de partida tolerando desplazamiento: lo que el modelo no toca no
    entra en la capa, esté donde esté.
    """
    cx, cy = _centro_de_la_mano(alfa, top, banda.mano or "diestra")
    zona = np.zeros_like(alfa)
    x0, x1 = max(0, cx - 95), min(LIENZO, cx + 95)
    y0, y1 = max(0, cy + banda.desde), min(LIENZO, cy + banda.hasta)
    zona[y0:y1, x0:x1] = True
    return zona


def _solo_los_extremos(alfa: np.ndarray, banda: Banda) -> np.ndarray:
    """De cada fila, el primer trozo y el último; lo de en medio se suelta.

    Sobre la silueta sin ensanchar, que es la única donde el brazo y la cadera
    siguen siendo dos cosas distintas.

    El primero y el último, y no «el que no contiene la mitad del lienzo»: a la
    altura de las manos el pantalón ya se ha abierto en dos perneras, así que
    ninguna contiene la mitad y las dos pasaban por extremas. Salía una tira
    cruzando la entrepierna.
    """
    limpia = np.zeros_like(alfa)
    for y in np.where(alfa.any(axis=1))[0]:
        etiquetas, cuantos = ndimage.label(alfa[y])
        if cuantos < 2:
            continue
        for i in (1, cuantos):
            xs = np.where(etiquetas == i)[0]
            if xs.size <= banda.ancho_maximo:
                limpia[y, xs] = True
    return limpia


def _la_cara(alfa: np.ndarray, top: int) -> np.ndarray:
    """El óvalo de la cara, medido sobre la propia cabeza de cada figura.

    No un rectángulo fijo: cada figura tiene su pelo, y lo que hay que proteger
    es la cara, no el ancho del peinado. Por eso se toma el centro de cada fila
    de la cabeza y se guarda su parte central, que es donde están los ojos, la
    nariz y la boca; las sienes y el contorno quedan libres, que es justo por
    donde pasa una capucha.
    """
    cara = np.zeros_like(alfa)
    # Desde los ojos, no desde la coronilla. Protegiendo también la frente no le
    # quedaba sitio donde poner un yelmo y devolvía la cabeza igual: un yelmo, una
    # capucha y una corona se apoyan precisamente ahí.
    for dy in range(78, 160):
        y = top + dy
        if y >= LIENZO:
            break
        xs = np.where(alfa[y])[0]
        if xs.size < 20:
            continue
        centro = (xs.min() + xs.max()) / 2
        medio = (xs.max() - xs.min()) * 0.31
        cara[y, int(centro - medio) : int(centro + medio) + 1] = True
    return cara


def como_mascara(zona: np.ndarray) -> Image.Image:
    """La API pinta donde el alfa vale 0."""
    m = Image.new("RGBA", (LIENZO, LIENZO), (0, 0, 0, 255))
    m.putalpha(Image.fromarray(np.where(zona, 0, 255).astype(np.uint8), "L"))
    return m


def pedir_edicion(figura_png: bytes, mascara_png: bytes, prompt: str) -> bytes:
    """Una llamada a la API de imágenes. Devuelve el PNG crudo."""
    import httpx  # noqa: PLC0415 - solo hace falta si se va a llamar de verdad

    with httpx.Client(timeout=300) as c:
        r = c.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {clave_openai()}"},
            files={
                "image": ("figura.png", figura_png, "image/png"),
                "mask": ("mascara.png", mascara_png, "image/png"),
            },
            data={"model": MODELO, "prompt": prompt, "size": f"{LIENZO}x{LIENZO}", "n": "1"},
        )
    if r.status_code != 200:
        raise SystemExit(f"La API respondió {r.status_code}: {r.text[:300]}")
    dato = r.json()["data"][0]
    if dato.get("b64_json"):
        return base64.b64decode(dato["b64_json"])
    return httpx.get(dato["url"], timeout=120).content


def _pegado_al_borde(candidato: np.ndarray) -> np.ndarray:
    """De los píxeles candidatos, los que se tocan con el borde del lienzo.

    Por conectividad y no por umbral suelto: un hueco del mismo color encerrado
    dentro de la figura —el ojo de una hebilla— no es fondo.
    """
    semilla = np.zeros_like(candidato)
    semilla[0, :] |= candidato[0, :]
    semilla[-1, :] |= candidato[-1, :]
    semilla[:, 0] |= candidato[:, 0]
    semilla[:, -1] |= candidato[:, -1]
    return ndimage.binary_propagation(semilla, mask=candidato)


def solo_fondo(nuevo: Image.Image) -> np.ndarray:
    """El fondo que puso el modelo, sea magenta o sea negro.

    Si obedeció y pintó magenta, se separa por color y el recorte es exacto: no
    hay nada magenta en el arte de Atenea, así que el contorno de tinta no corre
    peligro y no hace falta encoger nada.

    Si no obedeció, se cae al método de siempre —oscuro y pegado al borde,
    encogido para recuperar el contorno—, que funciona pero deja el borde algo
    dentado donde el dibujo es fino.
    """
    rgb = np.array(nuevo.convert("RGB"), dtype=np.int16)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]

    # Sin pedirle conectividad con el borde, al revés que al negro: el magenta no
    # existe en la paleta de Atenea, así que un magenta encerrado dentro de la
    # figura tampoco es figura. Se coló entre los mechones de pelo en el primer
    # intento y, exigiendo que tocara el borde, se quedaba dentro.
    magenta = (r > 120) & (b > 120) & (g < r - 60) & (g < b - 60)
    if magenta.sum() > 0.10 * LIENZO * LIENZO:
        # Ensancharlo se come el halo de píxeles medio teñidos del antialias,
        # que si no dejan una orla rosa alrededor de toda la figura.
        return ndimage.binary_dilation(magenta, structure=np.ones((3, 3)), iterations=2)

    oscuro = rgb.max(axis=2) < NEGRO
    # `border_value=1` o el borde mismo del lienzo se erosiona y las cuatro
    # esquinas salen opacas: la capa acaba midiendo 1024×1024 siempre.
    return ndimage.binary_erosion(
        _pegado_al_borde(oscuro), structure=np.ones((5, 5)), border_value=1
    )


def desnudar(figura: Image.Image, nuevo: Image.Image, zona: np.ndarray) -> Image.Image:
    """El cuerpo del modelo con la cabeza de siempre.

    Se compone al revés que una pieza, y por eso no vale reutilizar
    `extraer_capa`. En una pieza, el fondo del modelo se vuelve transparente y
    **destapa la figura de debajo**: correcto, porque ahí no hay prenda. Al
    desnudar, ese mismo hueco tiene que **borrar**: el cuerpo desnudo es más
    estrecho que el vestido, y si no se vacía la zona primero quedan flotando
    las mangas, las perneras y las botas de fábrica alrededor de un cuerpo que
    ya no las lleva.

    Fuera de la zona no se toca nada, y la zona empieza bajo la barbilla. Esa es
    la única garantía de que la cara sigue siendo la misma cara: el modelo
    dibuja de buena gana otra persona —lo hizo—, y la cara del aprendiz es su
    identidad, no un detalle de estilo.

    Tampoco se rellenan huecos: el hueco entre un brazo y el torso es fondo de
    verdad, y taparlo pinta una mancha negra en el costado.
    """
    util = zona & ~solo_fondo(nuevo)

    # Las dos mitades se cruzan en el corte en vez de encontrarse a cuchillo: la
    # de arriba se desvanece mientras la de abajo aparece. Un corte limpio se ve
    # siempre, por bien que coincidan las dos imágenes.
    #
    # Solo en el corte horizontal, y por filas. Con la distancia al borde de la
    # zona entera, la rampa también bajaba a cero alrededor de toda la silueta, y
    # ahí `1 - rampa` devolvía la figura vestida: reaparecían las mangas y las
    # botas en fantasma, ensanchando la caja cincuenta píxeles.
    filas = np.where(zona.any(axis=1))[0]
    corte = int(filas.min()) if filas.size else 0
    rampa = np.clip((np.arange(LIENZO) - corte) / FUNDIDO, 0, 1)[:, None] * np.ones(
        (1, LIENZO)
    )

    cuerpo = nuevo.copy()
    cuerpo.putalpha(
        Image.fromarray((util * rampa * 255).astype(np.uint8), "L").filter(
            ImageFilter.GaussianBlur(0.6)
        )
    )

    vaciada = figura.copy()
    alfa = np.array(vaciada.split()[3]) * (1 - rampa)
    vaciada.putalpha(Image.fromarray(alfa.astype(np.uint8), "L"))
    return Image.alpha_composite(vaciada, cuerpo)


#: Cuánto tiene que cambiar un píxel para contar como pieza, de 0 a 255.
#:
#: No cero: el modelo redibuja la imagen entera, así que hasta lo que no toca
#: vuelve con uno o dos niveles de diferencia. Y no mucho más alto, o una prenda
#: de un color parecido al de la piel dejaría agujeros.
CAMBIO = 30

#: Trozos sueltos más pequeños que esto se tiran, en píxeles.
#:
#: Son el ruido de recompresión del modelo: motas de dos o tres píxeles
#: repartidas por toda la banda que, si se dejan, salpican la capa de suciedad.
MOTA = 400

#: Y trozos sueltos menores que esta parte del mayor, también.
#:
#: El modelo no solo resombrea lo que no toca: a veces lo **mueve**. Al pedir un
#: jubón sobre la figura femenina redibujó los brazos un poco más adentro, y esas
#: dos tiras de piel desplazada difieren del original en 212 niveles —más que el
#: propio jubón, que difiere 156—, así que ningún umbral las separa. Lo que sí
#: las distingue es el tamaño: sueltas y flacas al lado de la prenda.
#:
#: Una fracción y no un número fijo porque las piezas no miden lo mismo. Y no
#: tanta como para tirar la segunda bota o el segundo guante, que vienen en dos
#: trozos parecidos.
PARTE_MINIMA = 0.15

#: Agujeros interiores más pequeños que esto se tapan, en píxeles.
#:
#: La comparación tolerante tiene un precio: el contorno de tinta de una bota
#: cae a unos píxeles del contorno de la pierna, y como los dos son casi negros
#: se dan por «lo mismo». La capa salía acribillada a lo largo de todo el
#: perfil.
#:
#: Se tapan solo los pequeños, y ahí está la gracia. El hueco entre los paños de
#: una capa también queda encerrado, y ese **no** se puede tapar: rellenarlo mete
#: en la capa una copia de la camiseta y del pantalón. Los dos tamaños no se
#: solapan, medidos sobre las piezas de verdad:
#:
#:     unas botas      huecos de 80, 62, 60, 45, 36, 35, 30, 30 px
#:     una capa        huecos de 11456, 5292, 4919, 1021, 286, 170 px
#:
#: Trescientos cae con holgura entre los ochenta de un contorno y los mil de un
#: paño.
AGUJERO = 300

#: Cuántos píxeles tarda una capa en desaparecer contra el borde de su banda.
#:
#: La banda acaba donde acaba, pero el modelo pinta hasta el último píxel que le
#: dejas, así que un corte a cuchillo deja una raya. En la figura femenina salía
#: una barra horizontal cruzando el pecho y el pelo, justo en el borde alto de la
#: banda del cuerpo: ahí el modelo había redibujado los hombros con otro tono y
#: la capa los traía de golpe.
#:
#: No pasa nada por perder catorce píxeles en el borde: la banda se dibuja con
#: holgura de sobra alrededor de donde va la prenda, precisamente para esto.
FUNDIDO = 14


def _lo_que_cambio(figura: Image.Image, nuevo: Image.Image) -> np.ndarray:
    """Los píxeles donde el modelo pintó algo distinto de lo que había.

    Sin esto, una capa se lleva puesto medio cuerpo. `extraer_capa` se queda con
    todo lo que hay en la banda y no es fondo, y en una capa abierta por delante
    eso incluye la camiseta y la piel que se ven **entre** los paños: el archivo
    `cape_front` acababa llevando dentro una copia del torso, que luego se pinta
    encima de la armadura y la tapa.

    La comparación tolera desplazamiento, y esa es la parte que importa. El
    modelo no solo resombrea lo que no toca: lo mueve unos píxeles. Comparando
    píxel contra píxel, un brazo redibujado dos píxeles más adentro difiere 212
    niveles —más que el propio jubón, que difiere 156—, así que entraba en la
    capa y salía un brazo doble. Un píxel cuenta como «lo mismo» si su color
    aparece en el original **en algún sitio cercano**, y entonces el brazo movido
    vuelve a ser el brazo.

    Donde la figura de partida no tenía nada, cualquier cosa que no sea fondo es
    la pieza: es por donde una capa cuelga más allá del cuerpo.
    """
    antes = np.array(figura.convert("RGB"), dtype=np.int16)
    despues = np.array(nuevo.convert("RGB"), dtype=np.int16)

    parecido = np.full(antes.shape[:2], 255, dtype=np.int16)
    for dy in (-6, -3, 0, 3, 6):
        for dx in (-6, -3, 0, 3, 6):
            corrido = np.roll(np.roll(antes, dy, axis=0), dx, axis=1)
            parecido = np.minimum(parecido, np.abs(corrido - despues).max(axis=2))

    vacio = np.array(figura.split()[3]) <= 40
    return (parecido > CAMBIO) | vacio


def _tapar_agujeros(mascara: np.ndarray) -> np.ndarray:
    """Cierra los huecos pequeños que quedan dentro de la pieza."""
    huecos, cuantos = ndimage.label(~mascara)
    if cuantos == 0:
        return mascara
    # El fondo de verdad es el trozo de «no pieza» que toca el borde del lienzo.
    fuera = set(np.unique(huecos[0, :])) | set(np.unique(huecos[-1, :]))
    fuera |= set(np.unique(huecos[:, 0])) | set(np.unique(huecos[:, -1]))
    tamanos = ndimage.sum_labels(~mascara, huecos, range(1, cuantos + 1))
    pequenos = [
        i + 1 for i, t in enumerate(tamanos) if t <= AGUJERO and (i + 1) not in fuera
    ]
    return mascara | np.isin(huecos, pequenos)


def _sin_motas(mascara: np.ndarray) -> np.ndarray:
    """Tira los trozos sueltos que son ruido, o cuerpo movido, y no pieza."""
    etiquetas, cuantos = ndimage.label(mascara)
    if cuantos == 0:
        return mascara
    tamanos = ndimage.sum_labels(mascara, etiquetas, range(1, cuantos + 1))
    corte = max(MOTA, PARTE_MINIMA * max(tamanos))
    grandes = {i + 1 for i, t in enumerate(tamanos) if t >= corte}
    return np.isin(etiquetas, list(grandes))


def extraer_capa(nuevo: Image.Image, zona: np.ndarray, figura: Image.Image) -> Image.Image:
    """Se queda solo con la pieza: dentro de la zona y sin el fondo del modelo.

    El cierre de 3×3 solo sutura el dentado del antialias. No se rellenan
    huecos: un hueco de fondo encerrado dentro de la pieza es fondo de verdad.
    En la banda de la capa, el hueco entre el brazo y el torso queda encerrado
    por el sobaco, el brazo y la mano, y rellenarlo pinta un pegote macizo en el
    costado. Es el mismo fallo que ya se vio al desnudar.
    """
    fondo = solo_fondo(nuevo)
    util = zona & ~fondo & _lo_que_cambio(figura, nuevo)
    util = _tapar_agujeros(ndimage.binary_closing(util, structure=np.ones((5, 5))))
    util = _sin_motas(util)

    # Se desvanece contra el borde de la banda, que si no se ve el corte.
    borde = np.clip(ndimage.distance_transform_edt(zona) / FUNDIDO, 0, 1)
    alfa = Image.fromarray((util * borde * 255).astype(np.uint8), "L").filter(
        ImageFilter.GaussianBlur(0.7)
    )
    capa = nuevo.copy()
    capa.putalpha(alfa)
    return capa


#: Hasta dónde puede haber capa por delante del cuerpo, desde la coronilla.
#:
#: Una capa se prende a los hombros y cae por detrás: por delante llega al pecho,
#: al embozo y poco más. Por debajo de la cintura, lo que se ve entre los paños
#: es el aprendiz, no la capa.
DELANTE_HASTA = 460


def partir_capa(capa: Image.Image, cuerpo: Image.Image, top: int) -> dict[str, Image.Image]:
    """Una capa dibujada, en sus dos capas de la pila: detrás y delante.

    La semilla le da a la ranura CAPE dos capas —`cape_back` en z=20, por detrás
    del cuerpo, y `cape_front` en z=140, por delante—, y no son dos dibujos sino
    dos trozos del mismo. Pedirle al modelo «la parte de la capa que queda
    detrás» sería pedirle algo que no se ve; el corte, en cambio, es geometría:

      - lo que cae **fuera** de la silueta del cuerpo es la tela que cuelga, y va
        detrás. Que se dibuje detrás no cambia nada, porque ahí no hay cuerpo que
        la tape: sencillamente es donde le toca en la pila.
      - lo que cae **dentro** es el embozo, los hombros y el broche, y va delante,
        que es lo único que de verdad tiene que taparle el pecho al aprendiz.

    Antes se cortaba solo con eso y no bastaba. Una capa abierta por delante deja
    ver el cuerpo entre los paños, y el modelo redibuja ese cuerpo con su propio
    sombreado: el pantalón volvía con sesenta niveles de diferencia y las piernas
    con cincuenta, de sobra para pasar por «cambiado». Así que `cape_front`
    llevaba dentro una copia del pantalón y de las piernas, y esa copia se pinta
    en z=140, por encima de todo: unas botas desaparecían bajo una capa.

    Un umbral no los separa —la capa roja da 173 y la pierna 50, pero sus colas
    se solapan—, y por conectividad tampoco: el pantalón redibujado toca la tela
    por el borde interior, así que es el mismo trozo.

    Lo que sí los separa es dónde están. Una capa se prende a los hombros y cae
    por detrás; por delante llega al pecho y poco más. Así que solo lo de encima
    de la cintura puede ir delante, y el resto se manda detrás, donde el cuerpo
    lo tapa. Si era el cuerpo redibujado, desaparece; si era tela de verdad, no
    se pierde.
    """
    dentro = np.array(cuerpo.split()[3]) > 40
    alfa = np.array(capa.split()[3])
    hay = alfa > 40

    etiquetas, _ = ndimage.label(hay)
    asoman = set(np.unique(etiquetas[hay & ~dentro])) - {0}
    de_la_capa = np.isin(etiquetas, list(asoman)) if asoman else hay

    arriba = np.zeros_like(hay)
    arriba[: min(LIENZO, top + DELANTE_HASTA), :] = True

    partes: dict[str, Image.Image] = {}
    for nombre, mascara in (
        # Lo de debajo de la cintura que cae dentro del cuerpo no se tira: se
        # manda detrás. Ahí el cuerpo lo tapa, que es exactamente lo que se
        # quiere si resultó ser el cuerpo redibujado, y si era tela de verdad
        # tampoco se pierde.
        ("cape_back", de_la_capa & (~dentro | ~arriba)),
        ("cape_front", de_la_capa & dentro & arriba),
    ):
        trozo = capa.copy()
        trozo.putalpha(Image.fromarray(np.where(mascara, alfa, 0).astype(np.uint8), "L"))
        partes[nombre] = trozo
    return partes


def damero(imagen: Image.Image) -> Image.Image:
    """Fondo de cuadros para mirar el recorte de una capa."""
    fondo = Image.new("RGBA", (LIENZO, LIENZO), (235, 235, 235, 255))
    for y in range(0, LIENZO, 32):
        for x in range(0, LIENZO, 32):
            if (x // 32 + y // 32) % 2:
                fondo.paste((205, 205, 205, 255), (x, y, x + 32, y + 32))
    return Image.alpha_composite(fondo, imagen)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--pieza",
        help="Código de un objeto del catálogo (`armadura_placas`). Saca de "
        "`piezas.py` la banda, el nombre del archivo y qué pintar, y de "
        "`CANONICA` sobre qué figura hacerlo.",
    )
    p.add_argument(
        "--familia",
        choices=sorted(CANONICA),
        default="masculino",
        help="Qué juego de piezas se está haciendo. Solo con --pieza.",
    )
    p.add_argument("--figura", help="base_femenino_001, base_masculino_002…")
    p.add_argument("--ranura", choices=sorted(BANDAS))
    p.add_argument("--prompt", help="Qué prenda pintar. Obligatorio con --aplicar.")
    p.add_argument("--nombre", help="Nombre del archivo de salida (por defecto, la ranura).")
    p.add_argument("--aplicar", action="store_true", help="Llama al modelo. Cuesta dinero.")
    p.add_argument(
        "--reusar",
        action="store_true",
        help="Recompone desde el PNG que ya devolvió el modelo, sin volver a llamarlo. "
        "Para afinar el recorte sin pagar dos veces por la misma imagen.",
    )
    args = p.parse_args(argv)

    pieza: Pieza | None = None
    if args.pieza:
        if args.figura or args.ranura or args.prompt:
            raise SystemExit("--pieza ya trae figura, banda y prompt: no los repitas.")
        pieza = por_codigo(args.pieza)
        args.figura = CANONICA[args.familia]
        args.ranura = pieza.banda
        args.prompt = pieza.prompt
        # Una capa se genera de una vez y se parte después, así que mientras se
        # genera se llama `<codigo>_cape` y no toma todavía uno de los dos
        # nombres de la pila.
        args.nombre = args.nombre or pieza.nombre
    elif not (args.figura and args.ranura):
        raise SystemExit("Sin --pieza hacen falta --figura y --ranura.")

    destino = SALIDA / args.figura
    destino.mkdir(parents=True, exist_ok=True)
    nombre = args.nombre or args.ranura

    if args.reusar:
        # La partida y la máscara de **entonces**, no unas recalculadas ahora.
        # Generar una pieza cambia el directorio —`base.png` aparece, y con él
        # cambia de qué figura se parte—, así que recomponer con la silueta de
        # después recorta la pieza contra un cuerpo que el modelo nunca vio.
        if not (destino / f"bruto_{nombre}.png").exists():
            raise SystemExit(f"No hay bruto_{nombre}.png que reusar.")
        figura = Image.open(destino / f"partida_{nombre}.png").convert("RGBA")
        zona = np.array(Image.open(destino / f"mascara_{nombre}.png").split()[3]) == 0
        print("reusando la respuesta guardada: no se llama al modelo")
        return _componer(args, destino, nombre, figura, zona, pieza)

    figura = figura_de_partida(args.figura, args.ranura)
    zona = zona_editable(figura, args.ranura)

    # Con nombre de pieza, no un `figura.png` compartido: la imagen de partida
    # cambia según lo que ya exista, y en el mismo archivo una pieza pisaba la
    # partida de otra.
    figura.save(destino / f"partida_{nombre}.png")
    como_mascara(zona).save(destino / f"mascara_{nombre}.png")

    rojo = Image.new("RGBA", (LIENZO, LIENZO), (255, 60, 60, 110))
    Image.composite(
        Image.alpha_composite(figura.copy(), rojo),
        figura,
        Image.fromarray((zona * 255).astype(np.uint8), "L"),
    ).save(destino / f"control_{nombre}.png")

    print(f"zona editable: {int(zona.sum())} px · control_{nombre}.png")
    if not args.aplicar:
        print("Sin --aplicar no se llama al modelo. Mira el control y vuelve.")
        return 0

    if not args.prompt:
        raise SystemExit("--aplicar necesita --prompt.")

    bruto = pedir_edicion(
        (destino / f"partida_{nombre}.png").read_bytes(),
        (destino / f"mascara_{nombre}.png").read_bytes(),
        f"{args.prompt}. {ESTILO}"
        + (
            f" {DESNUDEZ}"
            if args.ranura.startswith("base")
            else f" {SOLO_LA_PIEZA}" + ("" if args.ranura == "botas" else DESCALZO)
        )
        + f" El fondo, {FONDO}.",
    )
    (destino / f"bruto_{nombre}.png").write_bytes(bruto)
    return _componer(args, destino, nombre, figura, zona, pieza)


def _componer(
    args,
    destino: Path,
    nombre: str,
    figura: Image.Image,
    zona: np.ndarray,
    pieza: Pieza | None = None,
) -> int:
    """Del PNG que devolvió el modelo al archivo que se usa. Sin red."""
    nuevo = Image.open(destino / f"bruto_{nombre}.png").convert("RGBA")

    if args.ranura.startswith("base"):
        cuerpo = desnudar(figura, nuevo, zona)
        cuerpo.save(destino / "base.png")
        damero(cuerpo).save(destino / "base_sola.png")
        print(f"cuerpo desnudo en {args.figura}/base.png · caja {cuerpo.split()[3].getbbox()}")
        return 0

    capa = extraer_capa(nuevo, zona, figura)
    Image.alpha_composite(figura, capa).save(destino / f"{nombre}_puesta.png")

    salidas = (
        {
            f"{pieza.codigo}_{k}": v
            for k, v in partir_capa(capa, figura, coronilla(figura)).items()
        }
        if pieza is not None and pieza.capa == "cape"
        else {nombre: capa}
    )
    for archivo, trozo in salidas.items():
        trozo.save(destino / f"{archivo}.png")
        damero(trozo).save(destino / f"{archivo}_sola.png")
        print(f"capa {archivo}.png · caja {trozo.split()[3].getbbox()}")
    print(f"mírala puesta en {nombre}_puesta.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
