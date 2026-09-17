"""Separa las manos del cuerpo, para que un arma pueda ocultarlas.

## Por qué

Cada pieza empuñada del catálogo trae su propio puño dibujado: el modelo lo
añadió porque el estilo obligatorio le prohibía tocar las manos existentes y a
la vez se le pedía un arma empuñada, y esa es la única forma de obedecer a las
dos cosas. El resultado en pantalla son **dos manos**: la del arma y la del
cuerpo, asomando por el borde de la primera —diecinueve píxeles en la espada,
cuarenta y siete en el arco—.

Mover la capa no lo arregla: el puño dibujado es más pequeño que la mano del
cuerpo, así que nunca la tapa entera. Y ningún prompt va a conseguir que el
modelo clave un puño exactamente sobre una mano que no ve.

Lo que sí lo arregla es que la mano del cuerpo **se pueda apagar**. El motor ya
sabe hacerlo —`suppresses_layers`, que hoy usa un yelmo cerrado para tapar el
pelo—, pero solo puede apagar capas, y la mano era parte del cuerpo. Este guion
la saca a su propia capa, igual que `separar_piel_y_pelo.py` sacó las otras dos.

## Cómo encuentra la muñeca

Midiendo. El brazo colgado se estrecha hasta unos veintitrés píxeles en la
muñeca y se vuelve a ensanchar hasta casi cuarenta en la mano, así que el mínimo
local entre el codo y los dedos es el sitio del corte. No hay número escrito a
mano: cada figura tiene sus proporciones y se mide la suya.

## La garantía que hace esto seguro

**Cuerpo sin manos más las dos manos devuelve el original, píxel a píxel.** Y
lo mismo para la capa de piel, que va pegada al cuerpo y también hay que
partir: se dibuja encima para teñirla, así que si conservara las manos las
repintaría enteras sobre la que acabamos de apagar —el arreglo no se vería y
ninguna prueba se enteraría—. Se
comprueba en cada ejecución y el guion falla si deja de cumplirse. Sin arma
equipada el avatar no cambia absolutamente nada, que era el riesgo: un corte mal
puesto se vería como una muñeca partida en el noventa por ciento de las
pantallas, porque la mayoría de los aprendices no llevan arma.

Uso:

    python scripts/separar_manos.py                    # las seis figuras
    python scripts/separar_manos.py base_masculino_002 # una sola
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

#: Los cuerpos que ya viajan en el paquete, y donde se dejan las manos.
CUERPOS = pathlib.Path("app/assets/arte/capas/cuerpos")

#: Un píxel cuenta como figura a partir de esta opacidad.
OPACO = 40

#: Dónde buscar la muñeca, desde el borde superior del lienzo.
#:
#: Por arriba el antebrazo todavía se estrecha desde el codo y por abajo ya
#: empiezan las piernas, que son mucho más anchas y arruinarían el mínimo.
BUSCA_MUNECA = range(440, 560)

#: Hasta dónde llega una mano por debajo de la muñeca.
#:
#: Generoso a propósito: lo que sobre se descarta solo, porque solo se toma piel
#: y los dedos acaban antes. Quedarse corto, en cambio, parte la mano.
LARGO_MANO = 110

#: Un trozo de fila más ancho que esto ya no es una mano: es una pierna.
ANCHO_MAXIMO = 60


def _piel(a: np.ndarray) -> np.ndarray:
    """Los píxeles de piel. El pantalón es gris y queda fuera por el azul."""
    r = a[:, :, 0].astype(int)
    g = a[:, :, 1].astype(int)
    b = a[:, :, 2].astype(int)
    return (a[:, :, 3] > OPACO) & (r > 150) & (r > b + 35) & (g > b + 10) & (g < r)


def _trozos(fila: np.ndarray) -> list[np.ndarray]:
    """Los tramos contiguos de una fila de píxeles encendidos."""
    if not len(fila):
        return []
    return np.split(fila, np.where(np.diff(fila) > 1)[0] + 1)


def muneca(es_piel: np.ndarray, lado: str) -> int:
    """La altura donde el brazo de ese lado es más estrecho.

    `lado` es desde quien mira, igual que en `vestir.py`: «diestra» es el brazo
    que aparece a la derecha de la imagen.
    """
    ancho: dict[int, int] = {}
    for y in BUSCA_MUNECA:
        trozos = [t for t in _trozos(np.where(es_piel[y])[0]) if len(t) <= ANCHO_MAXIMO]
        if not trozos:
            continue
        brazo = trozos[-1] if lado == "diestra" else trozos[0]
        ancho[y] = len(brazo)
    if not ancho:
        raise ValueError(f"no encuentro el brazo {lado}")

    # El ancla es la PUNTA DE LOS DEDOS, que es el único accidente fiable en las
    # seis figuras: es donde el brazo se acaba y debajo ya no hay nada suyo.
    #
    # Se probaron dos anclas peores. «El punto más estrecho» caía entre los
    # dedos en dos figuras y partía la mano por la mitad. «Lo más ancho del
    # antebrazo» se iba al codo en otras dos, porque cerca del codo el brazo es
    # más ancho que la mano.
    #
    # Desde la punta se sube: la muñeca es el sitio más estrecho del tramo que
    # va de una mano de alto a un tercio de mano por encima de los dedos.
    dedos = max(ancho)
    tramo = [y for y in ancho if dedos - LARGO_MANO <= y <= dedos - LARGO_MANO // 3]
    if not tramo:
        raise ValueError(f"el brazo {lado} es más corto que una mano")
    return min(tramo, key=lambda y: (ancho[y], -y))


def mano_de(a: np.ndarray, es_piel: np.ndarray, lado: str) -> np.ndarray:
    """La máscara de una mano: de la muñeca a la punta de los dedos.

    Se corta la piel por la muñeca y se toma la **componente conexa** que queda
    colgando de ese lado. Fila a fila no vale: ir cogiendo «el trozo más a la
    derecha» se desvía en cuanto la mano deja de ser lo más externo —en la
    figura femenina 003 saltaba al muslo y se llevaba un trozo de pierna, y en
    la masculina 003 perdía el hilo y dejaba la mano casi entera sin marcar.
    Una componente conexa no se desvía: o toca la mano o no la toca.
    """
    corte = muneca(es_piel, lado)
    debajo = es_piel.copy()
    debajo[:corte, :] = False
    debajo[corte + LARGO_MANO :, :] = False

    etiquetas, cuantas = ndimage.label(debajo)
    if not cuantas:
        raise ValueError(f"no hay nada bajo la muñeca {lado}")

    # De las piezas que cuelgan bajo el corte, la mano es la del lado que toca y
    # la más pequeña de las candidatas: las piernas son mucho mayores.
    trozos_fila = [t for t in _trozos(np.where(es_piel[corte])[0]) if len(t) <= ANCHO_MAXIMO]
    if not trozos_fila:
        raise ValueError(f"la muñeca {lado} no tiene brazo")
    brazo = trozos_fila[-1] if lado == "diestra" else trozos_fila[0]
    etiqueta = etiquetas[corte, int(brazo.mean())]
    if etiqueta == 0:
        raise ValueError(f"la muñeca {lado} cae en el vacío")
    semilla = etiquetas == etiqueta

    # Cualquier tinta, no solo la opaca. Con el umbral de `OPACO` se quedaban
    # atrás los píxeles del contorno a medio pintar —alfa por debajo de 40—, y
    # como no se los llevaba la mano se quedaban en el cuerpo: al apagar la mano
    # aparecía un **fantasma** con su forma, tenue pero visible sobre el fondo
    # oscuro. Se vio componiendo la pila fuera de la aplicación; ninguna prueba
    # lo habría contado, porque los píxeles estaban donde tenían que estar.
    hay = a[:, :, 3] > 0

    # El contorno de tinta de los dedos no es piel, y sin él la mano se lleva el
    # relleno y deja el dibujo: por eso hay que crecer más allá de la piel.
    #
    # Pero crecer y luego quitar «todo lo que no es piel» quitaba también ese
    # contorno, que es justo lo que se quería conservar. La distinción buena no
    # es piel contra no-piel: es **dentro contra fuera de la mano**. Se toma el
    # rectángulo que ocupa la mano, con un margen corto, y dentro de él vale
    # todo lo que haya; fuera, nada.
    ys, xs = np.where(semilla)
    if not len(xs):
        raise ValueError(f"la mano {lado} salió vacía")
    margen = 6
    dentro = np.zeros_like(hay)
    dentro[
        max(0, ys.min() - margen) : ys.max() + margen + 1,
        max(0, xs.min() - margen) : xs.max() + margen + 1,
    ] = True

    crecida = ndimage.binary_dilation(semilla, np.ones((3, 3)), iterations=4)
    return crecida & hay & dentro


#: Las capas que viajan pegadas al cuerpo y hay que partir con él.
#:
#: La piel es la misma silueta con los brillos llevados al blanco, y se dibuja
#: **encima** del cuerpo para teñirla del tono que eligió el aprendiz. Así que
#: incluye las manos, y si no se parte también, repinta entera la mano que
#: acabamos de apagar: el arreglo no se vería en pantalla y las pruebas
#: seguirían verdes, porque comprueban qué se dibuja y no qué se ve.
#:
#: El pelo no hace falta: se midió y toca cero píxeles de las manos.
PEGADAS = ("piel",)


def _partir(a: np.ndarray, manos: dict[str, np.ndarray], base: str) -> None:
    """Escribe `base_sin_manos` y las dos manos de una imagen ya alineada.

    Falla sin escribir nada si recomponer las tres piezas no devuelve el
    original píxel a píxel: sin arma equipada se vería el corte, y la mayoría de
    los aprendices no lleva arma.
    """
    sin = a.copy()
    sin[:, :, 3] = np.where(manos["diestra"] | manos["zurda"], 0, a[:, :, 3])

    recompuesto = Image.fromarray(sin).copy()
    piezas: list[tuple[str, Image.Image]] = []
    for lado, mascara in manos.items():
        capa = a.copy()
        capa[:, :, 3] = np.where(mascara, a[:, :, 3], 0)
        recompuesto.alpha_composite(Image.fromarray(capa))
        piezas.append(("hand_right" if lado == "diestra" else "hand_left", Image.fromarray(capa)))

    perdida = int(np.abs(np.array(recompuesto).astype(int) - a.astype(int)).max())
    if perdida:
        raise SystemExit(
            f"{base}: recomponer no devuelve el original (diferencia {perdida}). "
            "Sin arma equipada se vería el corte, así que no se escribe nada."
        )

    for nombre, imagen in piezas:
        imagen.save(CUERPOS / f"{base}_{nombre}.webp", "WEBP", quality=90, method=6)
    Image.fromarray(sin).save(CUERPOS / f"{base}_sin_manos.webp", "WEBP", quality=90, method=6)


def separar(figura: str) -> dict[str, int]:
    """Escribe las dos manos y el cuerpo sin ellas. Devuelve cuántos píxeles."""
    a = np.array(Image.open(CUERPOS / f"{figura}.webp").convert("RGBA"))
    es_piel = _piel(a)

    manos = {lado: mano_de(a, es_piel, lado) for lado in ("diestra", "zurda")}
    # Disjuntas, y no es cosmético. En la figura femenina 001 los dos brazos
    # caen lo bastante juntos como para que las máscaras compartan píxeles, y un
    # píxel semitransparente compuesto dos veces no queda como estaba: 150 sobre
    # 150 da 211. La comprobación de `_partir` lo cazó con una diferencia de 63.
    manos["zurda"] &= ~manos["diestra"]

    _partir(a, manos, figura)
    # Las mismas máscaras sobre las capas pegadas: son la misma silueta en el
    # mismo encuadre, así que el recorte del cuerpo vale tal cual.
    for capa in PEGADAS:
        ruta = CUERPOS / f"{figura}_{capa}.webp"
        if not ruta.exists():
            raise SystemExit(f"falta {ruta}, que el cuerpo necesita para teñirse")
        _partir(np.array(Image.open(ruta).convert("RGBA")), manos, f"{figura}_{capa}")

    return {"diestra": int(manos["diestra"].sum()), "zurda": int(manos["zurda"].sum())}


def main(argv: list[str] | None = None) -> int:
    if not CUERPOS.is_dir():
        print(f"No encuentro {CUERPOS}. Ejecuta desde la raíz del repositorio.")
        return 1

    figuras = argv or sorted(
        f.stem
        for f in CUERPOS.glob("base_*.webp")
        if not any(s in f.stem for s in ("_piel", "_pelo", "_hand_", "_sin_manos"))
    )
    for figura in figuras:
        cuentas = separar(figura)
        print(
            f"{figura:22} diestra {cuentas['diestra']:>5} px   "
            f"zurda {cuentas['zurda']:>5} px   recompone exacto"
        )
    print(f"\n{len(figuras) * 2} manos y {len(figuras)} cuerpos sin manos.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
