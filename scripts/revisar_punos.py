"""Cada arma empuñada, compuesta como la compone el cliente, ampliada y medida.

Lo que este guion existe para evitar está escrito en `docs/PENDIENTE.md` §4.3:
**una hoja de contactos pequeña no sirve para dar algo por bueno.** Tres piezas
se declararon arregladas mirando miniaturas y al ampliarlas tenían agujeros.

Así que aquí cada arma sale sola, recortada alrededor de la mano y ampliada,
sobre el **tono de piel más claro**, que es donde un resto de la mano original
se ve. Sobre «Ébano» todo parece oscuro y los restos claros desaparecen: por eso
no se revisa ahí.

La pila reproduce `avatar_capas.dart` en el mismo orden, incluido el detalle que
importa: el tinte es `BlendMode.modulate`, o sea una **multiplicación**, y por
eso las capas normalizadas devuelven el color donde da la luz y su sombra donde
hay sombra.

    python scripts/revisar_punos.py            # las 18, una lámina por familia
    python scripts/revisar_punos.py --sola espada_entrenamiento_weapon
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
from PIL import Image

RAIZ = pathlib.Path(__file__).resolve().parent.parent

#: **Los recursos exportados, no el taller.** Es lo que la aplicación carga de
#: verdad: si el taller y el `.webp` se han separado —y ya pasó una vez, con una
#: pieza que se quedó con el recorte de una versión anterior del guion—, mirar
#: el taller enseña algo que nadie ve.
CAPAS = RAIZ / "app" / "assets" / "arte" / "capas"
CUERPOS = CAPAS / "cuerpos"
SALIDA = RAIZ / "arte" / "diagnostico" / "punos"

#: Las dos figuras que llevan el arte dibujado; las otras cuatro se derivan.
CANONICAS = ("base_masculino_002", "base_femenino_002")

#: «Marfil», el primero de la lista de `CatalogoAvatar.tonosPiel`. El más claro
#: a propósito: es el único tono sobre el que un resto de piel sin teñir se
#: distingue del fondo.
PIEL = (0xF3, 0xD6, 0xBE)

#: Alfa por debajo del cual un píxel no cuenta como dibujo. El mismo umbral que
#: usa `quitar_punos.py`, para que las dos medidas hablen del mismo píxel.
OPACO = 40

#: Cuánto se amplía el recorte. A tamaño original la mano ocupa unos 60 px de
#: lado en una figura de 1024: mirar eso en una lámina es mirar nada.
AUMENTO = 3

#: Margen alrededor de la caja de la mano, en píxeles del original.
MARGEN = 70


def cargar(ruta: pathlib.Path) -> np.ndarray | None:
    if not ruta.is_file():
        return None
    return np.asarray(Image.open(ruta).convert("RGBA"), dtype=np.uint8).copy()


def sobre(fondo: np.ndarray, capa: np.ndarray | None) -> np.ndarray:
    """Pinta `capa` encima de `fondo` con alfa, como haría el compositor."""
    if capa is None:
        return fondo
    a = capa[:, :, 3:4].astype(np.float32) / 255.0
    fondo[:, :, :3] = (capa[:, :, :3] * a + fondo[:, :, :3] * (1 - a)).astype(np.uint8)
    fondo[:, :, 3] = np.maximum(fondo[:, :, 3], capa[:, :, 3])
    return fondo


def tenir(capa: np.ndarray | None, color: tuple[int, int, int]) -> np.ndarray | None:
    """`BlendMode.modulate`: multiplica. Es lo que hace el cliente al teñir."""
    if capa is None:
        return None
    salida = capa.copy()
    for i, canal in enumerate(color):
        salida[:, :, i] = (capa[:, :, i].astype(np.uint16) * canal // 255).astype(np.uint8)
    return salida


def familia_de(figura: str) -> str:
    return "femenino" if "femenino" in figura else "masculino"


def cuerpo_de(figura: str, sufijo: str) -> pathlib.Path:
    return CUERPOS / f"{figura}{sufijo}.webp"


def equipo_de(figura: str, nombre: str) -> pathlib.Path:
    return CAPAS / familia_de(figura) / f"{nombre}.webp"


def componer(figura: str, arma: str) -> tuple[np.ndarray, dict[str, int]]:
    """La figura con esa arma puesta, en el orden exacto de `avatar_capas.dart`."""
    cuerpo = cargar(cuerpo_de(figura, "_sin_manos"))
    if cuerpo is None:
        raise SystemExit(
            f"falta {cuerpo_de(figura, '_sin_manos')}: corre separar_manos.py y exportar_capas.py"
        )

    lienzo = np.zeros_like(cuerpo)
    lienzo = sobre(lienzo, cuerpo)
    lienzo = sobre(lienzo, tenir(cargar(cuerpo_de(figura, "_piel_sin_manos")), PIEL))

    # La izquierda va **antes** del equipo: un escudo la tapa.
    lienzo = sobre(lienzo, cargar(cuerpo_de(figura, "_hand_left")))
    lienzo = sobre(lienzo, tenir(cargar(cuerpo_de(figura, "_piel_hand_left")), PIEL))

    lienzo = sobre(lienzo, cargar(equipo_de(figura, arma)))

    # La derecha va **después**, y solo si la pieza no trae la suya.
    puno = cargar(equipo_de(figura, f"{arma}_puno"))
    if puno is None:
        lienzo = sobre(lienzo, cargar(cuerpo_de(figura, "_hand_right")))
        lienzo = sobre(lienzo, tenir(cargar(cuerpo_de(figura, "_piel_hand_right")), PIEL))
    else:
        lienzo = sobre(lienzo, tenir(puno, PIEL))

    mano = cargar(cuerpo_de(figura, "_hand_right"))
    caja = recuadro(mano[:, :, 3] > OPACO) if mano is not None else None
    medidas = {"con_puno": int(puno is not None)}
    return lienzo, {**medidas, **(caja or {})}


def recuadro(mascara: np.ndarray) -> dict[str, int] | None:
    filas = np.where(mascara.any(axis=1))[0]
    columnas = np.where(mascara.any(axis=0))[0]
    if filas.size == 0 or columnas.size == 0:
        return None
    return {
        "y0": int(filas[0]),
        "y1": int(filas[-1]),
        "x0": int(columnas[0]),
        "x1": int(columnas[-1]),
    }


def recortar(lienzo: np.ndarray, caja: dict[str, int]) -> Image.Image:
    alto, ancho = lienzo.shape[:2]
    y0 = max(0, caja["y0"] - MARGEN)
    y1 = min(alto, caja["y1"] + MARGEN)
    x0 = max(0, caja["x0"] - MARGEN)
    x1 = min(ancho, caja["x1"] + MARGEN)
    trozo = Image.fromarray(lienzo[y0:y1, x0:x1])
    return trozo.resize(
        (trozo.width * AUMENTO, trozo.height * AUMENTO), Image.Resampling.NEAREST
    )


def armas_de(figura: str) -> list[str]:
    return sorted(
        f.stem
        for f in (CAPAS / familia_de(figura)).glob("*_weapon.webp")
        if not f.stem.endswith("_puno")
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sola", help="revisa una sola pieza por su nombre")
    args = p.parse_args(argv)

    SALIDA.mkdir(parents=True, exist_ok=True)
    for figura in CANONICAS:
        if not (CAPAS / familia_de(figura)).is_dir():
            print(f"{figura}: no está en el taller; se salta")
            continue
        armas = [a for a in armas_de(figura) if not args.sola or a == args.sola]
        for arma in armas:
            lienzo, datos = componer(figura, arma)
            if "y0" not in datos:
                print(f"  {arma}: no encuentro la mano derecha de {figura}")
                continue
            recorte = recortar(lienzo, datos)
            destino = SALIDA / f"{figura}__{arma}.png"
            # Sobre un gris medio: con fondo transparente, un agujero en la
            # pieza y un trozo de fondo se ven igual, que es justamente lo que
            # hay que distinguir.
            fondo = Image.new("RGBA", recorte.size, (128, 128, 128, 255))
            fondo.alpha_composite(recorte)
            fondo.convert("RGB").save(destino)
            print(f"  {destino.name:58} {'con puño' if datos['con_puno'] else 'SIN puño'}")

    print(f"\nLáminas en {SALIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
