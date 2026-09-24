"""Fase D del Plan B (`docs/planes/mundo-caminable.md`): el piloto real.

Genera **una lámina por pose** (`--pose marcha`: contacto + paso; `--pose
reposo`: de pie + de pie más bajo) de la figura simplificada del mundo
caminable — 1 Orden (Acero) × 1 familia (masculina), nada más — para juzgar
si el arte real convence antes de comprometerse a las 8 láminas completas
(Fase E-G). El reposo se sumó después de la primera ronda: parado o
caminando el arte real se veía bien, pero antes de tocar una parada y al
llegar a ella —la mayor parte del tiempo en pantalla— seguía cayendo al
cuadrado de mentira, porque esa ronda solo cubrió marcha.

## Por qué una lámina y no dos llamadas sueltas

La misma razón que ya vale para el catálogo de equipo: pedirle al modelo un
fotograma por llamada garantiza que cada uno dibuje una persona distinta
(mismo fallo que documenta `vestir.py`, "dándole el lienzo entero dibujó otra
persona"). Una sola llamada, una rejilla, un personaje — por pose: marcha y
reposo siguen siendo dos llamadas separadas en este piloto, no las 6 casillas
de una vez que sí pedirá la Fase E.

## Qué NO hace este script

No edita el arte real (`vestir.py` sigue intacto, sin tocar). Genera una
imagen nueva, de cero, describiendo el estilo en palabras (`ESTILO`, reusado
tal cual) en vez de partir de una ilustración — la figura simplificada no
tiene identidad que preservar (sin cara, sin pelo suelto), así que no hace
falta una base fija que editar.

## Uso

    python scripts/experimento_figura_mundo.py                    # nada, valida el entorno
    python scripts/experimento_figura_mundo.py --aplicar           # marcha, cuesta céntimos
    python scripts/experimento_figura_mundo.py --aplicar --pose reposo
    python scripts/experimento_figura_mundo.py --completar-marcha  # espejo, gratis, sin llamar al modelo

Ojo: `--pose marcha --aplicar` vuelve a escribir sobre `marcha_00/01.webp`
—los ya aprobados—, no se corre dos veces por accidente.
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "arte" / "experimentos_mundo"
ASSETS = RAIZ / "app" / "assets" / "arte" / "mundo" / "masculino" / "acero"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vestir import ALTO_FIGURA, BASE_Y, FONDO, clave_openai, solo_fondo  # noqa: E402

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

#: El reposo, pedido después de que Rodrigo viera el spike: parado o al andar
#: se veía bien, pero antes de tocar y al llegar a cada parada —la mayor
#: parte del tiempo en pantalla— seguía cayendo al cuadrado de mentira,
#: porque el reposo no se había generado en la primera ronda.
PROMPT_REPOSO = (
    "Una lámina de fotogramas sobre fondo {fondo}: dos casillas iguales, una "
    "junto a la otra, mismo tamaño, mismo alto de figura, con la coronilla a "
    "la misma altura en las dos. En cada casilla la MISMA figura de cuerpo "
    "entero, de frente, centrada: un caminante simplificado, pequeño, sin "
    "rasgos de cara ni pelo suelto —el rostro queda en sombra bajo una "
    "capucha sencilla—, vestido con {prenda}. Los brazos cuelgan a los "
    "costados; las manos están cerradas en puño y vacías, sin dibujar arma, "
    "escudo ni ningún objeto. Casilla 1: de pie, quieto, erguido, piernas "
    "juntas. Casilla 2: la misma pose de pie, pero un poco más baja, como al "
    "exhalar — rodillas apenas flexionadas, hombros un poco caídos. {estilo}"
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


#: El modelo dibuja un marco negro alrededor de la lámina entera (y la línea
#: que separa las casillas) de unos 6px — nada que ver con la figura, pero
#: `solo_fondo` en modo magenta no lo reconoce como fondo (solo sabe de
#: magenta, no de negro pegado al borde) y sin recortarlo antes, ese marco
#: cuenta como "figura": la silueta sale del tamaño de la casilla entera.
MARGEN_BORDE = 14


def _recortar_a_silueta(cruda: Image.Image) -> Image.Image:
    """La silueta real de una casilla, con fondo transparente — sin escalar."""
    sin_marco = cruda.crop((MARGEN_BORDE, MARGEN_BORDE, cruda.width - MARGEN_BORDE, cruda.height - MARGEN_BORDE))
    alfa = (~solo_fondo(sin_marco)).astype("uint8") * 255
    con_alfa = sin_marco.copy()
    con_alfa.putalpha(Image.fromarray(alfa, mode="L"))
    bbox = con_alfa.split()[3].getbbox()
    if bbox is None:
        raise SystemExit("No se encontró figura sobre el fondo.")
    return con_alfa.crop(bbox)


def recortar_casillas(lamina: Image.Image, cantidad: int, *, escala_independiente: bool) -> list[Image.Image]:
    """Cada casilla de la lámina, ya recortada y llevada al lienzo maestro.

    Mismo alineamiento que `vestir.normalizar`: fondo fuera (`solo_fondo`),
    recorte a la silueta, escala y pegado con la base en `BASE_Y`.

    `escala_independiente=True` (marcha): cada casilla se reescala sola a
    `ALTO_FIGURA` — la ilustración cruda venía con la coronilla a alturas
    distintas por puro ruido del modelo, y contacto/paso de un mismo ciclo no
    deben bambolearse en altura, así que igualarlas es corregir un defecto.

    `escala_independiente=False` (reposo): la escala se mide en la PRIMERA
    casilla y se aplica igual a todas — acá la diferencia de alto ENTRE
    casillas es la pose (el "bob" de exhalar, más baja a propósito, pedido
    en el prompt); reescalar cada una por separado a `ALTO_FIGURA` borraría
    exactamente esa diferencia, que es el único fotograma nuevo que aporta.
    """
    ancho_casilla = lamina.width // cantidad
    siluetas = [
        _recortar_a_silueta(
            lamina.crop((i * ancho_casilla, 0, (i + 1) * ancho_casilla, lamina.height)).convert("RGBA")
        )
        for i in range(cantidad)
    ]
    escala_compartida = ALTO_FIGURA / siluetas[0].height

    casillas: list[Image.Image] = []
    for silueta in siluetas:
        escala = ALTO_FIGURA / silueta.height if escala_independiente else escala_compartida
        alto_final = round(silueta.height * escala)
        redimensionada = silueta.resize((max(1, round(silueta.width * escala)), alto_final), Image.LANCZOS)
        hoja = Image.new("RGBA", (LIENZO, LIENZO), (0, 0, 0, 0))
        hoja.paste(redimensionada, ((LIENZO - redimensionada.width) // 2, BASE_Y - alto_final), redimensionada)
        casillas.append(hoja)
    return casillas


def completar_marcha_por_espejo() -> None:
    """`marcha_02`/`marcha_03` como espejo horizontal de `marcha_00`/`01`.

    Rodrigo, viendo el piloto de 2 poses duplicadas sin más (`02`=`00`,
    `03`=`01` tal cual): "el paso [...] se lee, pero tosco" — confirmado
    con `AskUserQuestion` que SÍ lee como caminar, solo falta que las piernas
    alternen. Duplicar sin espejar repetía la MISMA pierna adelante dos veces
    seguidas en vez de alternar izquierda/derecha, que es media zancada real.

    Espejar en vez de generar de nuevo: la figura es simétrica de frente (sin
    arma horneada en el cuerpo — eso es un prop aparte, ver el plan), así que
    un espejo horizontal de "contacto, pierna izquierda adelante" ES,
    literalmente, "contacto, pierna derecha adelante". Costo: US$0. El
    espejo de `Caminante` por dirección (`miraDerecha`) compone limpio con
    este —ver su comentario en `caminante.dart`—, así que no hace falta
    tocar nada del lado Flutter.
    """
    for base, espejo in (("marcha_00", "marcha_02"), ("marcha_01", "marcha_03")):
        origen = ASSETS / f"{base}.webp"
        if not origen.exists():
            raise SystemExit(f"Falta {origen} — corré --pose marcha --aplicar primero.")
        imagen = Image.open(origen).convert("RGBA")
        destino = ASSETS / f"{espejo}.webp"
        imagen.transpose(Image.FLIP_LEFT_RIGHT).save(destino, "WEBP", lossless=False, quality=90)
        print(f"{origen.name} espejado -> {destino}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--aplicar", action="store_true", help="Llama al modelo. Cuesta dinero.")
    p.add_argument(
        "--pose",
        choices=("marcha", "reposo"),
        default="marcha",
        help="Qué lámina pedir y procesar.",
    )
    p.add_argument(
        "--completar-marcha",
        action="store_true",
        help="Genera marcha_02/03 espejando 00/01 (gratis, sin llamar al modelo) y termina.",
    )
    args = p.parse_args(argv)

    if args.completar_marcha:
        completar_marcha_por_espejo()
        return 0

    prompt = PROMPT if args.pose == "marcha" else PROMPT_REPOSO
    nombre_lamina = f"lamina_{args.pose}_acero_masculino.png"

    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / f"prompt_{args.pose}.txt").write_text(prompt, encoding="utf-8")
    print(f"prompt escrito en {SALIDA / f'prompt_{args.pose}.txt'} — revísalo antes de --aplicar")

    if not args.aplicar:
        print("Sin --aplicar no se llama al modelo.")
        return 0

    clave_openai()  # falla rápido y claro si falta la llave, antes de journalear nada
    bruto = pedir_generacion(prompt)
    ruta_lamina = SALIDA / nombre_lamina
    ruta_lamina.write_bytes(bruto)
    print(f"lámina en {ruta_lamina}")

    lamina = Image.open(ruta_lamina)
    casillas = recortar_casillas(lamina, cantidad=2, escala_independiente=(args.pose == "marcha"))
    ASSETS.mkdir(parents=True, exist_ok=True)
    for i, casilla in enumerate(casillas):
        destino = ASSETS / f"{args.pose}_{i:02d}.webp"
        casilla.save(destino, "WEBP", lossless=False, quality=90)
        print(f"casilla {i} -> {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
