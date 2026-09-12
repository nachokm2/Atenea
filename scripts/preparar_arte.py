"""Convierte las ilustraciones de origen en recursos utilizables por la app.

Las piezas vienen de un generador de imágenes y traen tres problemas que las
hacen inservibles tal cual dentro de una aplicación móvil:

1. **No tienen transparencia.** El damero que parece "fondo transparente" está
   pintado en los píxeles: los archivos son RGB, sin canal alfa. Apilarlos
   taparía todo lo que hubiera debajo.
2. **Pesan demasiado.** Entre 1,5 y 2,4 MB cada una, 78 MB en total, para un
   binario que debe caber en un teléfono.
3. **Cada una llena su propio lienzo**, con 28 tamaños distintos y sin margen
   común, así que no hay dos que compartan escala.

Este script resuelve los tres: recorta el damero con un relleno desde los bordes
que no cruza el contorno del dibujo, recorta al contenido real, escala a un
tamaño sensato y guarda en WebP con alfa.

    python scripts/preparar_arte.py --origen "C:/ruta/Visual" --destino app/assets/arte

Con `--informe` no escribe nada y solo dice qué haría.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

# --------------------------------------------------------------------------
# Reglas por categoría
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Regla:
    """Cómo se trata una categoría de arte."""

    carpeta_destino: str
    alto_maximo: int
    lado_maximo: int
    descripcion: str


#: Carpeta de origen -> cómo se procesa y dónde acaba.
REGLAS: dict[str, Regla] = {
    "Personajes": Regla("personajes", 1024, 1024, "figuras completas del avatar"),
    "Cabello": Regla("items/cabello", 512, 512, "peinados"),
    "Pecheras": Regla("items/cuerpo", 512, 512, "torso y vestimenta"),
    "Capas": Regla("items/capa", 512, 512, "capas"),
    "Cascos-Gorros": Regla("items/cabeza", 512, 512, "cascos y tocados"),
    "Botas": Regla("items/botas", 512, 512, "calzado"),
    "Guantes": Regla("items/guantes", 512, 512, "guantes y guanteletes"),
    "Herramientas": Regla("items/arma", 512, 512, "armas y utensilios"),
    "Accesorios": Regla("items/accesorio", 512, 512, "accesorios"),
}

#: Diferencia máxima entre canales para considerar un píxel gris. El damero es
#: gris; el dibujo, salvo el metal, no lo es.
SATURACION_MAXIMA = 16

#: Holgura alrededor de los dos tonos del damero de cada imagen.
HOLGURA = 14

#: Ancho en píxeles de la franja de borde que se usa para deducir el fondo.
FRANJA = 12

#: Islas opacas más pequeñas que esta fracción de la imagen se descartan: son
#: las motas que deja el damero al recortarse, no parte del dibujo.
MOTA_MAXIMA = 0.0004

#: Margen transparente que se deja alrededor del contenido, en píxeles.
MARGEN = 8


def _tonos_del_damero(rgb: np.ndarray) -> tuple[int, int]:
    """Deduce los dos tonos del damero mirando la franja de borde.

    No sirve un umbral fijo: unas ilustraciones traen el damero casi blanco y
    otras bastante más oscuro. Cada imagen declara el suyo en sus bordes.
    """
    franja = np.concatenate(
        [
            rgb[:FRANJA].reshape(-1, 3),
            rgb[-FRANJA:].reshape(-1, 3),
            rgb[:, :FRANJA].reshape(-1, 3),
            rgb[:, -FRANJA:].reshape(-1, 3),
        ]
    ).astype(np.int16)
    grises = franja[(franja.max(axis=1) - franja.min(axis=1)) <= SATURACION_MAXIMA]
    if grises.size == 0:
        return 235, 255
    luz = grises.mean(axis=1)
    return int(np.percentile(luz, 3)), int(np.percentile(luz, 97))


def _sin_motas(opaco: np.ndarray) -> np.ndarray:
    """Descarta las islas opacas diminutas que el damero deja tras el recorte."""
    etiquetas, cuantas = ndimage.label(opaco)
    if cuantas == 0:
        return opaco
    tamanos = np.bincount(etiquetas.ravel())
    tamanos[0] = 0
    minimo = max(24, int(opaco.size * MOTA_MAXIMA))
    grandes = np.zeros(tamanos.size, dtype=bool)
    grandes[tamanos >= minimo] = True
    return grandes[etiquetas]


def _mascara_de_fondo(rgb: np.ndarray) -> np.ndarray:
    """Máscara del damero: gris del tono del borde **y** conectado con el borde.

    La condición de conectividad es la que salva el dibujo: una armadura tiene
    zonas plateadas casi tan claras como el fondo, pero están encerradas por su
    propio contorno oscuro, así que el relleno no llega hasta ellas.
    """
    oscuro, claro_ref = _tonos_del_damero(rgb)
    maximo = rgb.max(axis=2).astype(np.int16)
    minimo = rgb.min(axis=2).astype(np.int16)
    luz = rgb.mean(axis=2)
    gris = (maximo - minimo) <= SATURACION_MAXIMA
    en_rango = (luz >= oscuro - HOLGURA) & (luz <= claro_ref + HOLGURA)
    candidato = gris & en_rango

    semilla = np.zeros_like(candidato)
    semilla[0, :] = candidato[0, :]
    semilla[-1, :] = candidato[-1, :]
    semilla[:, 0] = candidato[:, 0]
    semilla[:, -1] = candidato[:, -1]

    # Reconstrucción morfológica: crece la semilla del borde solo por donde el
    # fondo sea continuo.
    fondo = ndimage.binary_propagation(semilla, mask=candidato)

    # Lo que queda opaco pero es una mota suelta también era fondo.
    return ~_sin_motas(~fondo)


def _recortar(imagen: Image.Image) -> Image.Image:
    """Recorta al contenido visible dejando un margen uniforme."""
    caja = imagen.getbbox()
    if caja is None:
        return imagen
    izq, arr, der, aba = caja
    izq = max(0, izq - MARGEN)
    arr = max(0, arr - MARGEN)
    der = min(imagen.width, der + MARGEN)
    aba = min(imagen.height, aba + MARGEN)
    return imagen.crop((izq, arr, der, aba))


def _escalar(imagen: Image.Image, regla: Regla) -> Image.Image:
    """Reduce la imagen respetando el alto y el lado máximo de su categoría."""
    factor = min(
        regla.alto_maximo / imagen.height,
        regla.lado_maximo / max(imagen.width, imagen.height),
        1.0,
    )
    if factor >= 1.0:
        return imagen
    nuevo = (max(1, round(imagen.width * factor)), max(1, round(imagen.height * factor)))
    return imagen.resize(nuevo, Image.LANCZOS)


def _nombre_de_archivo(origen: Path) -> str:
    """`Botas_de_Hierro.png` -> `botas_de_hierro.webp`."""
    base = origen.stem.lower()
    reemplazos = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n", "-": "_", " ": "_"}
    for viejo, nuevo in reemplazos.items():
        base = base.replace(viejo, nuevo)
    return f"{base}.webp"


def procesar(origen: Path, destino: Path, regla: Regla, *, solo_informe: bool) -> dict:
    """Procesa una ilustración y devuelve el detalle de lo ocurrido."""
    imagen = Image.open(origen).convert("RGB")
    bytes_antes = origen.stat().st_size
    rgb = np.asarray(imagen)

    fondo = _mascara_de_fondo(rgb)
    alfa = np.where(fondo, 0, 255).astype(np.uint8)

    # Suaviza el borde: un desenfoque leve del alfa evita el halo de píxeles
    # medio claros que deja el damero al recortarse.
    alfa_suave = ndimage.uniform_filter(alfa.astype(np.float32), size=3)
    alfa = np.where(alfa == 0, 0, alfa_suave).astype(np.uint8)

    salida = Image.fromarray(np.dstack([rgb, alfa]), mode="RGBA")
    salida = _escalar(_recortar(salida), regla)

    proporcion_visible = float((alfa > 0).mean())
    resultado = {
        "origen": str(origen),
        "destino": str(destino),
        "antes": bytes_antes,
        "dimensiones": salida.size,
        "visible_pct": round(proporcion_visible * 100, 1),
    }

    if solo_informe:
        resultado["despues"] = None
        return resultado

    destino.parent.mkdir(parents=True, exist_ok=True)
    salida.save(destino, "WEBP", quality=86, method=4)
    resultado["despues"] = destino.stat().st_size
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepara el arte de Atenea para la app.")
    parser.add_argument("--origen", required=True, help="Carpeta con las ilustraciones originales")
    parser.add_argument("--destino", required=True, help="Carpeta de recursos de la app")
    parser.add_argument("--informe", action="store_true", help="No escribe nada; solo informa")
    args = parser.parse_args(argv)

    origen = Path(args.origen)
    destino = Path(args.destino)
    if not origen.is_dir():
        print(f"No existe la carpeta de origen: {origen}", file=sys.stderr)
        return 1

    total_antes = total_despues = 0
    procesados: list[dict] = []
    sin_regla: list[str] = []

    for carpeta in sorted(p for p in origen.iterdir() if p.is_dir()):
        regla = REGLAS.get(carpeta.name)
        if regla is None:
            sin_regla.append(carpeta.name)
            continue
        for archivo in sorted(carpeta.glob("*.png")):
            salida = destino / regla.carpeta_destino / _nombre_de_archivo(archivo)
            info = procesar(archivo, salida, regla, solo_informe=args.informe)
            procesados.append(info)
            total_antes += info["antes"]
            total_despues += info["despues"] or 0
            marca = "informe" if args.informe else f"{(info['despues'] or 0) / 1024:7.0f} KB"
            print(
                f"  {archivo.parent.name:<16} {archivo.name:<28} "
                f"{info['antes'] / 1024 / 1024:5.1f} MB -> {marca}  "
                f"{info['dimensiones'][0]}x{info['dimensiones'][1]}  "
                f"visible {info['visible_pct']}%"
            )

    print()
    print(f"{len(procesados)} ilustraciones procesadas")
    print(f"antes:   {total_antes / 1024 / 1024:.1f} MB")
    if not args.informe:
        print(f"despues: {total_despues / 1024 / 1024:.1f} MB")
        if total_antes:
            print(f"ahorro:  {100 - total_despues * 100 / total_antes:.1f}%")
    if sin_regla:
        print(f"carpetas sin regla (no se tocaron): {', '.join(sin_regla)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
