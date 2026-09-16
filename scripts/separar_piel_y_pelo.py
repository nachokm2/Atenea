"""Saca de cada cuerpo dos capas teñibles: la piel y el pelo.

Al crear personaje se eligen seis tonos de piel y diez colores de pelo, y hasta
hoy ninguno cambiaba nada: en el arte hay **dos** tonos de piel —uno por familia,
medidos [252,211,165] y [243,180,114]— y seis colores de pelo, soldados cada uno
a su figura. El aprendiz elegía de una lista y recibía lo que trajera la
ilustración.

Esto no genera arte nuevo ni llama a ningún modelo: parte los cuerpos que ya
existen. Doce archivos derivados, cero euros.

## Por qué normalizar y no exportar el recorte tal cual

El cliente tiñe con `BlendMode.modulate`, que multiplica, así que **solo puede
oscurecer**. El tono más claro que ofrece la pantalla es Marfil `#F3D6BE`, más
oscuro que la piel dibujada: aplicado sobre el recorte crudo, elegir «marfil»
dejaría la piel más oscura que antes.

Por eso la capa se normaliza: se divide por el color de referencia de esa región
en esa figura, de modo que lo iluminado queda cerca del blanco y la sombra
conserva su proporción. Multiplicar después por el color elegido devuelve
exactamente ese color en la luz y su sombra correspondiente en la sombra. Y
elegir el color de referencia reproduce el original píxel a píxel.

La referencia es un percentil alto y no la media. Con la media, todo lo que esté
por encima satura a blanco y se pierde el modelado; con el pelo negro, cuya media
ronda 35, dividir por ella dejaría un manchón plano.

## Cómo se distingue el pelo de la piel

Por color no basta y está medido: el pelo rubio de la figura femenina 003 cae en
el mismo rango cálido que la piel, y los pantalones beige de la masculina 002
también. Lo que sí funciona es la forma.

El pelo se busca **sembrando en la coronilla y propagando** por píxeles de color
parecido. Así la melena larga, que llega a la cintura, entra entera por estar
conectada; y cualquier otra cosa del mismo color que no toque la cabeza se queda
fuera. La piel es después lo cálido que no es pelo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vestir import SALIDA, coronilla

DESTINO = Path(__file__).resolve().parent.parent / "app" / "assets" / "arte" / "capas" / "cuerpos"

#: Percentil de luminancia que se lleva al blanco al normalizar.
#:
#: Noventa y cinco y no cien: el máximo absoluto suele ser un brillo de un puñado
#: de píxeles, y anclarse a él dejaría el resto de la región más apagada de lo
#: que debe.
BRILLO = 95

#: Cuánto puede alejarse un píxel del color sembrado para seguir siendo pelo.
#:
#: Por canal y sobre el color de la coronilla. Generoso a propósito: el pelo va
#: de la sombra al brillo, y quedarse corto parte la melena en trozos.
TOLERANCIA = 95

#: A partir de qué distancia se puede usar el color de la piel para descartar.
#:
#: Medido sobre las seis figuras, la distancia entre el pelo y la piel va de 31
#: —el rubio de la femenina 003, que es casi del color de su piel— a 133. Con el
#: pelo lejos de la piel se puede descartar por color; con el rubio no, y ahí
#: manda solo la forma.
SEPARABLE = 45

#: Cuánto tiene que parecerse un píxel a la piel para no ser pelo.
CERCA_DE_LA_PIEL = 35

#: Desde qué fila empieza el óvalo que protege la cara, con y sin ayuda del color.
#:
#: Con el color disponible basta empezar a la altura de los ojos y el flequillo se
#: tiñe entero. Sin él hay que subir hasta el nacimiento del pelo, y el precio es
#: que el flequillo conserva su color de origen.
CARA_CON_COLOR = 95
CARA_SIN_COLOR = 78

#: Franja que se protege del pelo además del óvalo de la cara, y cuánta anchura
#: de la fila ocupa a cada lado del centro.
#:
#: Salió de mirar el resultado teñido: la piel en sombra de debajo de la barbilla
#: tiene casi el tono de un castaño oscuro, así que por color no hay forma de
#: separarla del pelo; por sitio, sí.
#:
#: Hubo una segunda franja para la frente, por la sombra que el flequillo
#: proyecta ahí, y se retiró: se comía el propio flequillo. Al pelo azul le
#: quedaba una banda castaña debajo y al plateado se le veían las raíces rojas.
#: La raya de la frente es más fina que el destrozo de quitarla.
#:
#: Solo por el centro. El pelo largo cae por los **lados** del cuello en las tres
#: figuras femeninas, así que proteger la fila entera cortaría la melena; por el
#: centro no pasa pelo en ninguna de las seis.
FRANJAS: tuple[tuple[int, int, float], ...] = (
    (150, 205, 0.40),  # la garganta, entre la barbilla y los hombros
)

#: Filas desde la coronilla donde se siembra el pelo.
#:
#: Ahí arriba solo hay pelo en las seis figuras: la cara empieza más abajo y el
#: cuerpo no llega. Es el único sitio del que se puede partir sin dudar.
SIEMBRA = (6, 45)


def _lienzo_alfa(mascara: np.ndarray) -> Image.Image:
    """Máscara booleana a canal alfa, suavizado para que no dentee el borde."""
    return Image.fromarray((mascara * 255).astype(np.uint8), "L").filter(
        ImageFilter.GaussianBlur(0.6)
    )


def _cara_y_cuello(hay: np.ndarray, top: int, *, desde: int) -> np.ndarray:
    """La cara y la garganta, que no son pelo por mucho que se le parezcan.

    El óvalo empieza en `desde`, y esa fila decide un compromiso real. Si empieza
    alto protege la frente pero se traga el flequillo, que cae justo ahí: el pelo
    plateado salía con las raíces rojas. Si empieza bajo, el flequillo se tiñe
    pero la sombra que proyecta en la frente puede colarse como pelo.

    Cuando el pelo y la piel se distinguen por color, la exclusión por color ya
    protege la frente y el óvalo puede empezar a la altura de los ojos. Cuando no
    —el rubio de la figura femenina 003 está a 31 de su propia piel—, la forma es
    lo único que queda y el óvalo tiene que subir.
    """
    protegido = np.zeros_like(hay)
    for dy in range(desde, 160):
        y = top + dy
        if y >= hay.shape[0]:
            break
        xs = np.where(hay[y])[0]
        if xs.size < 20:
            continue
        centro = (xs.min() + xs.max()) / 2
        medio = (xs.max() - xs.min()) * 0.31
        protegido[y, int(centro - medio) : int(centro + medio) + 1] = True
    for arriba, abajo, parte in FRANJAS:
        for dy in range(arriba, abajo):
            y = top + dy
            if y >= hay.shape[0]:
                break
            xs = np.where(hay[y])[0]
            if xs.size < 20:
                continue
            centro = (xs.min() + xs.max()) / 2
            medio = (xs.max() - xs.min()) * parte
            protegido[y, int(centro - medio) : int(centro + medio) + 1] = True
    return protegido


def color_de_la_piel(rgb: np.ndarray, hay: np.ndarray, top: int) -> np.ndarray:
    """El color de la piel de esa figura, medido en el muslo.

    Ahí no hay ropa ni pelo en ninguna de las seis, así que es el único sitio del
    que se puede tomar la muestra sin condiciones.
    """
    zona = np.zeros_like(hay)
    zona[top + 620 : top + 700, :] = True
    pix = rgb[zona & hay]
    calida = pix[(pix[:, 0] > 180) & (pix[:, 0] > pix[:, 2].astype(int) + 30)]
    return np.median(calida if calida.size else pix, axis=0)


def pelo_de(rgb: np.ndarray, hay: np.ndarray, top: int) -> np.ndarray:
    """El pelo: lo que está conectado con la coronilla y se le parece.

    Con dos exclusiones, y las dos hicieron falta al verlo teñido.

    **La cara.** El pelo gris de la figura canosa está a 56 de distancia de su
    piel, dentro de la tolerancia, así que la propagación cruzaba a la cara:
    teñido de verde salía la cara verde. Se recorta el mismo óvalo que protege
    `vestir.py` cuando pinta un yelmo. El precio es que la barba, que cae dentro
    del óvalo, no se tiñe con el pelo.

    **El color de la piel, pero solo cuando se puede.** Medida la distancia entre
    pelo y piel en las seis figuras, va de 31 a 133: con el pelo lejos se puede
    descartar por color —eso quitó una mancha azul en el cuello de la masculina
    001—, pero el rubio de la femenina 003 es casi del color de su piel y ahí ese
    descarte se llevaría la melena entera. Por eso se mira antes si son
    separables.
    """
    semilla = np.zeros_like(hay)
    semilla[top + SIEMBRA[0] : top + SIEMBRA[1], :] = True
    semilla &= hay
    if not semilla.any():
        return np.zeros_like(hay)

    referencia = np.median(rgb[semilla], axis=0)
    parecido = (np.abs(rgb - referencia).max(axis=2) <= TOLERANCIA) & hay

    piel = color_de_la_piel(rgb, hay, top)
    separables = np.abs(referencia - piel).max() > SEPARABLE
    if separables:
        parecido &= np.abs(rgb - piel).max(axis=2) > CERCA_DE_LA_PIEL

    # Propagar desde la coronilla: así entra la melena larga por estar unida, y
    # se queda fuera lo que sea del mismo color sin tocar la cabeza.
    pelo = ndimage.binary_propagation(semilla & parecido, mask=parecido)
    desde = CARA_CON_COLOR if separables else CARA_SIN_COLOR
    return pelo & ~_cara_y_cuello(hay, top, desde=desde)


def piel_de(rgb: np.ndarray, hay: np.ndarray, pelo: np.ndarray) -> np.ndarray:
    """La piel: lo cálido que no es pelo.

    Cálido quiere decir que el rojo le saca ventaja al azul. La camiseta y el
    pantalón son grises o blancos —sus tres canales van juntos—, así que caen
    solos sin necesidad de decir dónde están.
    """
    calido = (rgb[:, :, 0].astype(int) - rgb[:, :, 2]) > 45
    claro = rgb.max(axis=2) > 90
    piel = hay & calido & claro & ~pelo

    # Cerrar los huecos finos, y hay uno concreto que obliga: la costura del
    # cuello. `desnudar` cruza ahí la cabeza que se conserva con el cuerpo que
    # dibuja el modelo, y esa franja de píxeles es mezcla de camisa y piel, así
    # que no pasa el test de cálido y se quedaba sin teñir. Con los tonos
    # oscuros salía una banda clara cruzando el pecho.
    #
    # El radio se queda muy por debajo del ancho de la camiseta, que mide
    # trescientos y pico píxeles, así que no hay riesgo de tragársela.
    piel = ndimage.binary_closing(piel, structure=np.ones((21, 21)))
    return piel & hay & ~pelo


def normalizar(rgb: np.ndarray, mascara: np.ndarray) -> np.ndarray:
    """Lleva los brillos de la región al blanco conservando el sombreado."""
    salida = rgb.astype(np.float32).copy()
    zona = rgb[mascara].astype(np.float32)
    if zona.size == 0:
        return rgb
    referencia = np.percentile(zona, BRILLO, axis=0)
    referencia = np.maximum(referencia, 12.0)  # sin esto, el pelo negro divide por casi cero
    salida[mascara] = np.clip(zona / referencia * 255.0, 0, 255)
    return salida.astype(np.uint8)


def separar(figura: str) -> dict[str, tuple[int, int]]:
    """Escribe las dos capas teñibles de una figura. Devuelve cuántos píxeles."""
    cuerpo = Image.open(SALIDA / figura / "base.png").convert("RGBA")
    rgb = np.array(cuerpo.convert("RGB"))
    hay = np.array(cuerpo.split()[3]) > 40
    top = coronilla(cuerpo)

    pelo = pelo_de(rgb, hay, top)
    piel = piel_de(rgb, hay, pelo)

    DESTINO.mkdir(parents=True, exist_ok=True)
    cuentas: dict[str, tuple[int, int]] = {}
    for nombre, mascara in (("pelo", pelo), ("piel", piel)):
        capa = Image.fromarray(normalizar(rgb, mascara), "RGB").convert("RGBA")
        capa.putalpha(_lienzo_alfa(mascara))
        destino = DESTINO / f"{figura}_{nombre}.webp"
        capa.save(destino, "WEBP", quality=90, method=6)
        cuentas[nombre] = (int(mascara.sum()), destino.stat().st_size)
    return cuentas


def main(argv: list[str] | None = None) -> int:
    figuras = argv or sorted(d.name for d in SALIDA.iterdir() if (d / "base.png").exists())
    for figura in figuras:
        cuentas = separar(figura)
        detalle = "  ".join(
            f"{n}: {px:>6} px, {tam / 1024:>4.0f} KB" for n, (px, tam) in cuentas.items()
        )
        print(f"{figura:22} {detalle}")
    print(f"\n{len(figuras) * 2} capas teñibles en {DESTINO.relative_to(DESTINO.parents[4])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
