"""Todas las piezas de una familia, puestas sobre su cuerpo, en una lámina.

Mirarlas de una en una no sirve: lo que hay que ver es si la familia entera se
sostiene junta, si el estilo aguanta de la primera a la última y si alguna se
sale de su sitio. Y una capa hay que verla apilada como la apilará el cliente,
con `cape_back` por debajo del cuerpo.
"""

import sys
from pathlib import Path

sys.path.insert(0, "scripts")

from PIL import Image, ImageDraw

from piezas import TODAS

Z_CUERPO = 40  # `body_base` en la pila de 06c §2.3
COLUMNAS = 6
LADO = 300


def archivos_de(pieza):
    return (
        [f"{pieza.codigo}_cape_back", f"{pieza.codigo}_cape_front"]
        if pieza.capa == "cape"
        else [pieza.nombre]
    )


def main(figura: str, salida: str) -> int:
    d = Path("arte/capas") / figura
    base = Image.open(d / "base.png").convert("RGBA")
    celdas = []
    for pieza in TODAS:
        nombres = [n for n in archivos_de(pieza) if (d / f"{n}.png").exists()]
        if not nombres:
            continue
        lienzo = Image.new("RGBA", base.size, (255, 255, 255, 255))
        for n in nombres:
            if n.endswith("_back"):
                lienzo = Image.alpha_composite(lienzo, Image.open(d / f"{n}.png").convert("RGBA"))
        lienzo = Image.alpha_composite(lienzo, base)
        for n in nombres:
            if not n.endswith("_back"):
                lienzo = Image.alpha_composite(lienzo, Image.open(d / f"{n}.png").convert("RGBA"))
        celda = lienzo.convert("RGB").resize((LADO, LADO), Image.LANCZOS)
        ImageDraw.Draw(celda).text((6, 6), pieza.codigo, fill=(90, 90, 90))
        celdas.append(celda)

    filas = (len(celdas) + COLUMNAS - 1) // COLUMNAS
    hoja = Image.new("RGB", (LADO * COLUMNAS, LADO * filas), (255, 255, 255))
    for i, c in enumerate(celdas):
        hoja.paste(c, (LADO * (i % COLUMNAS), LADO * (i // COLUMNAS)))
    hoja.save(salida)
    print(f"{len(celdas)} piezas en {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
