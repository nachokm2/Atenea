"""Fase D del Plan B (`docs/planes/mundo-caminable.md`): el piloto real.

Genera **una sola lámina** con 2 fotogramas (contacto + paso) de la figura
simplificada del mundo caminable — 1 Orden (Acero) × 1 familia (masculina),
nada más — para juzgar si el arte real convence antes de comprometerse a las
8 láminas completas (Fase E-G).

## Por qué una lámina y no dos llamadas sueltas

La misma razón que ya vale para el catálogo de equipo: pedirle al modelo un
fotograma por llamada garantiza que cada uno dibuje una persona distinta
(mismo fallo que documenta `vestir.py`, "dándole el lienzo entero dibujó otra
persona"). Una sola llamada, una rejilla, un personaje.

## Qué NO hace este script

No edita el arte real (`vestir.py` sigue intacto, sin tocar). Genera una
imagen nueva, de cero, describiendo el estilo en palabras (`ESTILO`, reusado
tal cual) en vez de partir de una ilustración — la figura simplificada no
tiene identidad que preservar (sin cara, sin pelo suelto), así que no hace
falta una base fija que editar.

## Uso

    python scripts/experimento_figura_mundo.py            # nada, solo valida el entorno
    python scripts/experimento_figura_mundo.py --aplicar   # llama al modelo, cuesta céntimos
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "arte" / "experimentos_mundo"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vestir import FONDO, clave_openai  # noqa: E402 - tras el sys.path.insert

LIENZO = 1024

#: Igual que `vestir.ESTILO`, pero sin "idéntico al de la imagen de
#: partida": esta es una generación de cero, no una edición — no hay ninguna
#: imagen de partida a la que referirse, y esa frase confundiría al modelo.
ESTILO_SIN_IMAGEN_DE_PARTIDA = (
    "Estilo de ilustración: contorno de tinta oscura de grosor constante "
    "alrededor de cada forma, sombreado plano en dos o tres tonos planos por "
    "celdas, sin aerógrafo, sin degradados suaves y sin brillos especulares. "
    "Proporciones de seis cabezas y media, no alargadas."
)

#: La prenda real del kit inicial de la Orden del Acero (`backend/app/seeds/items.py`,
#: código `jubon_recluta`) — no una descripción inventada.
PRENDA_ACERO = (
    "un jubón de cuero endurecido con remaches de hierro, pantalón sencillo "
    "y botas de camino de suela gastada"
)

PROMPT = (
    "Una lámina de fotogramas sobre fondo {fondo}: dos casillas iguales, una "
    "junto a la otra, mismo tamaño, mismo alto de figura, con la coronilla a "
    "la misma altura en las dos. En cada casilla la MISMA figura de cuerpo "
    "entero, de frente, centrada: un caminante simplificado, pequeño, sin "
    "rasgos de cara ni pelo suelto —el rostro queda en sombra bajo una "
    "capucha sencilla—, vestido con {prenda}. Los brazos cuelgan a los "
    "costados; las manos están cerradas en puño y vacías, sin dibujar arma, "
    "escudo ni ningún objeto. Casilla 1: pose de contacto, pierna izquierda "
    "adelante, talón en el suelo, pierna derecha atrás. Casilla 2: pose de "
    "paso, la pierna derecha pasando junto a la izquierda con la rodilla "
    "alzada. {estilo}"
).format(fondo=FONDO, prenda=PRENDA_ACERO, estilo=ESTILO_SIN_IMAGEN_DE_PARTIDA)


def pedir_generacion(prompt: str) -> bytes:
    """Una llamada a generación de imágenes (no edición): no hay base que
    editar, esta figura no tiene identidad que preservar de una imagen previa.
    """
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
    (SALIDA / "prompt.txt").write_text(PROMPT, encoding="utf-8")
    print(f"prompt escrito en {SALIDA / 'prompt.txt'} — revísalo antes de --aplicar")

    if not args.aplicar:
        print("Sin --aplicar no se llama al modelo.")
        return 0

    clave_openai()  # falla rápido y claro si falta la llave, antes de journalear nada
    bruto = pedir_generacion(PROMPT)
    (SALIDA / "lamina_acero_masculino.png").write_bytes(bruto)
    print(f"lámina en {SALIDA / 'lamina_acero_masculino.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
