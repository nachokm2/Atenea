"""Pone a los cuerpos de una familia a la misma altura.

Las piezas se generan una vez por familia, sobre la figura canónica, y se ponen
a las tres por posición absoluta dentro del lienzo maestro. Eso solo funciona si
los tres cuerpos ocupan las mismas filas.

No las ocupaban. Medido sobre los seis cuerpos desnudos, la línea de suelo cae en
filas distintas dentro de la misma familia:

    figura                coronilla   suelo
    base_masculino_001           52     979
    base_masculino_002           53     974   <- canónica
    base_masculino_003           53     998
    base_femenino_001            53     957
    base_femenino_002            52     995   <- canónica
    base_femenino_003            52     973

Veinticuatro píxeles entre la 002 y la 003. Una bota generada sobre la canónica
se le queda a la 003 flotando esa distancia por encima del pie, y en el avatar se
ve el pie desnudo asomando por debajo de la bota.

Viene de la normalización: `vestir.normalizar` escala cada ilustración **vestida**
a la misma altura, y las seis llevan botas de distinto alto, así que el pie
desnudo que hay debajo acaba en sitios distintos.

## Por qué escalar y no mover

Bajar la figura entera arreglaría las botas y estropearía las coronas: la cabeza
se iría con ella. Escalando en vertical para que **coronilla y suelo** coincidan a
la vez, encajan las dos puntas y todo lo de en medio queda proporcionalmente en
su sitio. El estirón más grande de las seis es del 4 %, que no se ve.

La canónica no se toca: es la referencia, y sus piezas ya están hechas sobre ella.

Es idempotente. Después de la primera pasada las alturas ya coinciden, así que la
escala vale uno y no pasa nada por volver a ejecutarlo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vestir import CANONICA, LIENZO, SALIDA


def extremos(imagen: Image.Image) -> tuple[int, int]:
    """Coronilla y línea de suelo, en filas del lienzo."""
    filas = np.where((np.array(imagen.split()[3]) > 40).any(axis=1))[0]
    if filas.size == 0:
        raise SystemExit("El cuerpo está vacío.")
    return int(filas.min()), int(filas.max())


def alinear(cuerpo: Image.Image, coronilla: int, suelo: int) -> Image.Image:
    """Estira o encoge en vertical hasta clavar esas dos filas."""
    arriba, abajo = extremos(cuerpo)
    alto_actual = abajo - arriba
    alto_destino = suelo - coronilla
    if alto_actual == alto_destino and arriba == coronilla:
        return cuerpo

    recorte = cuerpo.crop((0, arriba, LIENZO, abajo + 1))
    estirado = recorte.resize((LIENZO, max(1, alto_destino + 1)), Image.LANCZOS)
    hoja = Image.new("RGBA", (LIENZO, LIENZO), (0, 0, 0, 0))
    hoja.paste(estirado, (0, coronilla), estirado)
    return hoja


def main(argv: list[str] | None = None) -> int:
    del argv
    for familia, canonica in CANONICA.items():
        referencia = SALIDA / canonica / "base.png"
        if not referencia.exists():
            print(f"{familia}: falta la canónica ({canonica}); se salta")
            continue
        with Image.open(referencia) as abierta:
            coronilla, suelo = extremos(abierta.convert("RGBA"))
        print(f"{familia}: referencia {canonica}, coronilla {coronilla}, suelo {suelo}")

        for carpeta in sorted(SALIDA.iterdir()):
            if not carpeta.is_dir() or familia not in carpeta.name:
                continue
            archivo = carpeta / "base.png"
            if not archivo.exists() or carpeta.name == canonica:
                continue
            # Con `with`, que si no PIL deja el archivo abierto y en Windows
            # guardar encima del mismo da «Invalid argument».
            with Image.open(archivo) as abierto:
                cuerpo = abierto.convert("RGBA")
            antes = extremos(cuerpo)
            alineado = alinear(cuerpo, coronilla, suelo)
            alineado.save(archivo)
            print(
                f"  {carpeta.name}: {antes} -> {extremos(alineado)}"
                f"  ({(suelo - coronilla) / max(1, antes[1] - antes[0]):.3f}×)"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
