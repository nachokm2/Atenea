"""Mide las seis figuras y saca la tabla de ajuste de las piezas de equipo.

## Por qué existe

Las 46 piezas de equipo se generaron **por familia**, editando la ilustración de
una figura canónica —`base_masculino_002` y `base_femenino_002`—. La decisión
estaba medida: dentro de una familia el torso difería «unos 12 px por lado», y
eso se dio por tolerable frente a generar 276 imágenes en vez de 92.

No era tolerable, y el número tampoco era ese. Medido de verdad, el torso varía
hasta **28 px por lado** y —lo que más se nota— la mano cambia de altura hasta
**54 px**. Como cada arma lleva dibujado su propio puño agarrándola, esos 54 px
son la distancia entre el puño de la pieza y la mano del cuerpo: se ven las dos.
Un aprendiz lo describió como «tengo dos manos», que es exactamente lo que es.

## Qué hace

Mide cada cuerpo desnudo y escribe, para cada figura, dos ajustes respecto a la
canónica de su familia:

  - **escalaTorso** — cuánto hay que ensanchar o estrechar una pieza que se ciñe
    al torso (túnica, capa, accesorio de cuerpo) para que siga los hombros.
  - **manoDx / manoDy** — cuánto hay que mover una pieza que se sostiene con la
    mano (arma, secundaria, guantes) para que su puño caiga sobre el del cuerpo.

La salida es la tabla que consume `app/lib/design/arte.dart`. No se aplica aquí
porque el ajuste vive en el cliente: hornear seis variantes de cada pieza
multiplicaría por seis los 2,3 MB de arte que viajan en el paquete.

## Lo que este ajuste no arregla

Una pieza dibujada para otro cuerpo sigue siendo una pieza dibujada para otro
cuerpo. Esto la coloca y la ajusta de talla; no le cambia la postura ni la
perspectiva. El arreglo completo es generar las piezas por figura, y cuesta
dinero de API y horas.

Uso:

    python scripts/medir_figuras.py            # imprime la tabla
    python scripts/medir_figuras.py --dart     # en la forma que espera arte.dart
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
from PIL import Image

#: Los cuerpos desnudos, ya exportados al paquete.
CUERPOS = pathlib.Path("app/assets/arte/capas/cuerpos")

#: Sobre estas se editó cada pieza. Su ajuste es, por definición, la identidad.
CANONICAS = {"masculino": "base_masculino_002", "femenino": "base_femenino_002"}

#: Un píxel cuenta como figura a partir de esta opacidad. Por debajo es el
#: desvanecido del borde, que se mueve solo y ensancharía la medida.
OPACO = 40

#: Franja del torso, en el lienzo maestro de 1024×1024. Empieza bajo la barbilla
#: y acaba sobre la cadera: es donde una túnica tiene que seguir al cuerpo.
TORSO = range(250, 560, 4)

#: Franja donde caen las manos en reposo. El punto más ancho de esta franja es
#: la mano, porque los brazos cuelgan separados del cuerpo.
MANOS = range(470, 620, 3)


def _silueta(imagen: Image.Image) -> np.ndarray:
    return np.array(imagen.convert("RGBA"))[:, :, 3] > OPACO


def medir(ruta: pathlib.Path) -> dict[str, float]:
    """Anchura del torso, su centro, y dónde está la mano derecha."""
    alfa = _silueta(Image.open(ruta))

    filas = [y for y in TORSO if alfa[y].any()]
    if not filas:
        raise ValueError(f"{ruta.name}: no hay figura en la franja del torso")
    izquierdas = [float(np.where(alfa[y])[0].min()) for y in filas]
    derechas = [float(np.where(alfa[y])[0].max()) for y in filas]

    # La mano es el punto más externo del brazo, pero «la fila más ancha» no
    # sirve para encontrarla: el brazo cuelga casi vertical, así que decenas de
    # filas empatan en anchura y el resultado depende de cuál se coja primero.
    # Con `argmax` salía una altura y con `max` otra, cincuenta píxeles más
    # abajo, para el mismo cuerpo.
    #
    # Se toma el borde derecho de cada fila, se mira cuál es el máximo, y la
    # mano es la **mediana** de las alturas que llegan a ese máximo (con dos
    # píxeles de margen). Así el empate deja de decidir.
    bordes = [(y, int(np.where(alfa[y])[0].max())) for y in MANOS if alfa[y].any()]
    if not bordes:
        raise ValueError(f"{ruta.name}: no hay figura en la franja de las manos")
    mano_x = max(x for _, x in bordes)
    mano_y = float(np.median([y for y, x in bordes if x >= mano_x - 2]))

    return {
        "torso": float(np.mean(derechas) - np.mean(izquierdas)),
        "centro": float(np.mean(derechas) + np.mean(izquierdas)) / 2,
        "mano_x": float(mano_x),
        "mano_y": float(mano_y),
    }


def tabla() -> dict[str, dict[str, float]]:
    """El ajuste de cada figura respecto a la canónica de su familia."""
    medidas = {
        f.stem: medir(f)
        for f in sorted(CUERPOS.glob("base_*.webp"))
        if "_piel" not in f.name and "_pelo" not in f.name
    }

    ajustes: dict[str, dict[str, float]] = {}
    for figura, m in medidas.items():
        familia = "masculino" if "masculino" in figura else "femenino"
        canon = medidas[CANONICAS[familia]]
        ajustes[figura] = {
            "escalaTorso": round(m["torso"] / canon["torso"], 4),
            # El centro se mueve con la escala, así que el desplazamiento del
            # torso se calcula ya escalado: dónde cae el centro de la pieza
            # después de estirarla, y cuánto falta para el centro del cuerpo.
            "torsoDx": round(m["centro"] - canon["centro"] * (m["torso"] / canon["torso"]), 1),
            "manoDx": round(m["mano_x"] - canon["mano_x"], 1),
            "manoDy": round(m["mano_y"] - canon["mano_y"], 1),
        }
    return ajustes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dart", action="store_true", help="en la forma de arte.dart")
    args = parser.parse_args(argv)

    if not CUERPOS.is_dir():
        print(f"No encuentro {CUERPOS}. Ejecuta desde la raíz del repositorio.")
        return 1

    ajustes = tabla()

    if args.dart:
        for figura, a in ajustes.items():
            print(
                f"  '{figura}': AjusteDeFigura("
                f"escalaTorso: {a['escalaTorso']}, torsoDx: {a['torsoDx']}, "
                f"manoDx: {a['manoDx']}, manoDy: {a['manoDy']}),"
            )
        return 0

    print(f"{'figura':24} {'torso':>7} {'torsoDx':>9} {'manoDx':>8} {'manoDy':>8}")
    for figura, a in ajustes.items():
        canonica = figura in CANONICAS.values()
        marca = "  <- canonica" if canonica else ""
        print(
            f"{figura:24} {a['escalaTorso']:>7.3f} {a['torsoDx']:>9.1f} "
            f"{a['manoDx']:>8.1f} {a['manoDy']:>8.1f}{marca}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
