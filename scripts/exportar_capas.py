"""Lleva las capas generadas al paquete de Flutter.

`vestir.py` escribe en `arte/capas/`, que está en la raíz del repositorio y
**fuera** del paquete Flutter. Nada de lo que hay ahí llega al binario: un
`assets:` de `app/pubspec.yaml` solo puede declarar rutas bajo `app/`. Este
guion es el puente, y es el paso que faltaba para que el arte por capas dejara
de ser una carpeta de PNG que nadie mira.

## Por qué no sirve `preparar_arte.py`

El otro guion de arte hace justo lo que aquí rompería el apilado. Convierte a
RGB, que tira el canal alfa; y recorta al rectángulo con contenido, que le da a
cada pieza un lienzo propio. Una capa vive precisamente de lo contrario: alfa
alrededor y el mismo lienzo de 1024×1024 para todas, que es lo que hace que
ponerlas una encima de otra las deje en su sitio sin calcular nada.

## Dónde acaba cada cosa

    assets/arte/capas/cuerpos/<figura>.webp      el cuerpo desnudo, uno por figura
    assets/arte/capas/<familia>/<pieza>.webp     las piezas, un juego por familia

Dos niveles distintos a propósito, y la razón está medida. Cada figura necesita
su propio cuerpo porque conserva su cara y su pelo. Las piezas, no: midiendo las
seis siluetas, dentro de una familia el cuerpo es el mismo con ±10 px, y entre
familias hay ~30 px por lado en pecho y cintura. Así que dos juegos de piezas
bastan, y hacer seis sería pagar tres veces por el mismo dibujo.

## WebP y no PNG

Mismo formato que el resto del arte del paquete, y no es solo consistencia: una
capa de 1024×1024 pesa 504 KB en PNG y 43 en WebP con calidad 90. Con el
catálogo entero la diferencia es entre unos 2 MB y unos 50.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "arte" / "capas"
DESTINO = RAIZ / "app" / "assets" / "arte" / "capas"

#: Calidad de WebP. Por encima de 90 el archivo crece sin que se note en un
#: avatar de 220 dp; por debajo, el contorno de tinta empieza a ensuciarse.
CALIDAD = 90

#: Los intermedios de `vestir.py`. Son pasos del camino, no arte.
INTERMEDIOS = ("partida_", "mascara_", "control_", "bruto_", "prueba_")
VISTAS = ("_sola", "_puesta")


def familia_de(figura: str) -> str:
    """`base_masculino_001` -> `masculino`."""
    for familia in ("masculino", "femenino"):
        if familia in figura:
            return familia
    raise SystemExit(f"No sé de qué familia es {figura}.")


def es_arte(nombre: str) -> bool:
    """Distingue una capa de los archivos de trabajo que la acompañan."""
    if not nombre.endswith(".png"):
        return False
    tronco = nombre[: -len(".png")]
    return not tronco.startswith(INTERMEDIOS) and not tronco.endswith(VISTAS)


def convertir(origen: Path, destino: Path) -> int:
    """Escribe el WebP con alfa y devuelve lo que pesa."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    Image.open(origen).convert("RGBA").save(destino, "WEBP", quality=CALIDAD, method=6)
    return destino.stat().st_size


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--figura",
        action="append",
        help="Exporta solo esta figura. Repetible. Por defecto, todas las que haya.",
    )
    p.add_argument("--simular", action="store_true", help="Dice qué haría y no escribe nada.")
    args = p.parse_args(argv)

    if not ORIGEN.exists():
        raise SystemExit(f"No hay nada que exportar: {ORIGEN} no existe.")

    figuras = sorted(d for d in ORIGEN.iterdir() if d.is_dir())
    if args.figura:
        pedidas = set(args.figura)
        figuras = [d for d in figuras if d.name in pedidas]
        if faltan := pedidas - {d.name for d in figuras}:
            raise SystemExit(f"No hay carpeta para {', '.join(sorted(faltan))}.")

    total = 0
    cuerpos = 0
    piezas: dict[str, set[str]] = {}

    for carpeta in figuras:
        familia = familia_de(carpeta.name)
        for archivo in sorted(carpeta.iterdir()):
            if not es_arte(archivo.name):
                continue
            tronco = archivo.stem
            if tronco == "base":
                destino = DESTINO / "cuerpos" / f"{carpeta.name}.webp"
                cuerpos += 1
            else:
                destino = DESTINO / familia / f"{tronco}.webp"
                # Dos figuras de la misma familia comparten juego de piezas, así
                # que la segunda pisaría a la primera. Se avisa en vez de
                # sobrescribir en silencio: si pasa, una de las dos sobra.
                ya = piezas.setdefault(familia, set())
                if tronco in ya:
                    print(f"  ¡ojo! {familia}/{tronco} ya venía de otra figura; se pisa")
                ya.add(tronco)

            relativo = destino.relative_to(RAIZ / "app")
            if args.simular:
                print(f"  {archivo.name:28} -> {relativo}")
                continue
            peso = convertir(archivo, destino)
            total += peso
            print(f"  {archivo.name:28} -> {relativo}  ({peso / 1024:.0f} KB)")

    if args.simular:
        print("\nSimulación: no se escribió nada.")
        return 0

    print(f"\n{cuerpos} cuerpo(s) y {sum(len(v) for v in piezas.values())} pieza(s)")
    print(f"{total / 1024:.0f} KB en total")
    if cuerpos or piezas:
        print("\nRecuerda declarar las carpetas en app/pubspec.yaml: las entradas")
        print("de directorio de Flutter NO son recursivas, hace falta una por carpeta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
