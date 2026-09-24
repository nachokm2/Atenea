"""Fase T2 del terreno ilustrado (Parte A, `docs/planes/mundo-caminable.md`).

Genera **una lámina** de terreno ambiental para `TerrenoDelMundo`
(`app/lib/pantallas/aventura/mundo/terreno.dart`): la primera variante real de
`tramo_00.webp`, para juzgar si un fondo ilustrado ya se siente "más un
reino" antes de invertir en más variantes (Fase T3).

## Por qué esta lámina es distinta a la del personaje

`scripts/experimento_figura_mundo.py` genera sobre magenta y recorta a la
silueta (`solo_fondo()`) porque el personaje necesita fondo transparente. El
terreno es lo opuesto: tiene que llenar el lienzo entero, opaco, sin
recortar nada — el borde de la lámina es el dato que hace que las bandas
empalmen, no ruido a descartar. Por eso este script no usa `solo_fondo()` ni
ninguna función de `vestir.py` para separar fondo de figura.

## Qué NO dibuja

Ningún camino, ninguna figura de personaje ni objeto grande y discreto (una
roca enorme, un árbol solitario) que se note al repetirse — el sendero
sigue siendo 100% procedural (`pintor_senda.dart`) encima de este terreno, y
un elemento grande y único desentonaría cada vez que la banda se repita.

## Uso

    python scripts/experimento_terreno_mundo.py            # nada, valida el entorno
    python scripts/experimento_terreno_mundo.py --aplicar   # llama al modelo, cuesta céntimos
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "arte" / "experimentos_mundo"
ASSETS = RAIZ / "app" / "assets" / "arte" / "mundo" / "terreno"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vestir import clave_openai  # noqa: E402 - tras el sys.path.insert

LIENZO = 1024

#: Mismo lenguaje visual ya aprobado para el personaje
#: (`experimento_figura_mundo.py.ESTILO_SIN_IMAGEN_DE_PARTIDA`), sin la frase
#: sobre una imagen de partida: esta también es una generación de cero.
ESTILO = (
    "Estilo de ilustración: contorno de tinta oscura de grosor constante "
    "alrededor de cada forma, sombreado plano en dos o tres tonos planos por "
    "celdas, sin aerógrafo, sin degradados suaves y sin brillos especulares."
)

PROMPT = (
    "Una textura de terreno de fantasía medieval, vista de frente y algo "
    "elevada, para usarse como fondo de un mapa de nivel de videojuego móvil "
    "(como los mapas de Candy Crush o Clash Royale): pradera con parches de "
    "pasto en dos tonos de verde, tierra y piedra clara asomando entre el "
    "pasto, un par de rocas chicas y matas de pasto alto dispersas de forma "
    "irregular, sin ningún elemento grande, único o repetido de forma obvia. "
    "El lienzo se ve COMPLETO de terreno, de borde a borde, sin ningún hueco "
    "de otro color, sin cielo, sin horizonte y sin ningún camino, sendero o "
    "figura dibujados — el terreno se ve desde directamente arriba, como un "
    "campo visto en un mapa, no como un paisaje con perspectiva. "
    "Fundamental para que la imagen se pueda repetir en vertical sin que se "
    "note la costura: el borde superior y el borde inferior de la imagen "
    "tienen que verse del mismo tono de pasto liso, sin ninguna roca, mata "
    "ni detalle grande pegado a esos dos bordes — los detalles grandes van "
    "solo en la mitad central de la imagen. "
    f"{ESTILO}"
)


def pedir_generacion(prompt: str) -> bytes:
    """Generación de imágenes, sin base ni máscara — un terreno ambiental no
    tiene identidad que preservar de ninguna imagen previa."""
    import httpx  # noqa: PLC0415 - solo hace falta si se va a llamar de verdad

    with httpx.Client(timeout=300) as c:
        r = c.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {clave_openai()}"},
            json={
                "model": "gpt-image-2",
                "prompt": prompt,
                "size": f"{LIENZO}x{LIENZO}",
                "n": 1,
            },
        )
    if r.status_code != 200:
        raise SystemExit(f"La API respondió {r.status_code}: {r.text[:300]}")
    dato = r.json()["data"][0]
    if dato.get("b64_json"):
        return base64.b64decode(dato["b64_json"])
    return httpx.get(dato["url"], timeout=120).content


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--aplicar", action="store_true", help="Llama al modelo. Cuesta dinero.")
    args = p.parse_args(argv)

    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "prompt_terreno.txt").write_text(PROMPT, encoding="utf-8")
    print(f"prompt escrito en {SALIDA / 'prompt_terreno.txt'} — revísalo antes de --aplicar")

    if not args.aplicar:
        print("Sin --aplicar no se llama al modelo.")
        return 0

    clave_openai()  # falla rápido y claro si falta la llave, antes de journalear nada
    bruto = pedir_generacion(PROMPT)
    ruta_lamina = SALIDA / "lamina_terreno_tramo_00.png"
    ruta_lamina.write_bytes(bruto)
    print(f"lámina en {ruta_lamina}")

    ASSETS.mkdir(parents=True, exist_ok=True)
    destino = ASSETS / "tramo_00.webp"
    # Sin recorte ni normalización: el lienzo ya sale cuadrado y opaco, y acá
    # es justamente el borde completo lo que hace falta conservar.
    from PIL import Image  # noqa: PLC0415 - solo hace falta si se va a llamar de verdad

    Image.open(ruta_lamina).convert("RGB").save(destino, "WEBP", lossless=False, quality=90)
    print(f"tramo -> {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
