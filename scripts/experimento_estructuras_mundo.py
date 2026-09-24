"""Fase T4 del terreno ilustrado (Parte A, `docs/planes/mundo-caminable.md`).

Rodrigo, viendo el terreno ya wireado (Fase T1): "me agrada el fondo, podemos
agregar castillos o algo donde llega el personaje?". Genera las estructuras
ilustradas que reemplazan, con arte real, al círculo + ícono Material que hoy
dibuja `_ParadaSpike` en `experimento_mundo.dart` (`_iconoDeReino`) — una por
cada `EstiloNodo` (`bloqueado`, `enConstruccion`, `disponible`, `actual`,
`completado`) más el tesoro final (`TipoParada.tesoro`), 6 en total.

## Qué distingue a cada estado (decisión, no catálogo de opciones)

La lectura tiene que sobrevivir en escala de grises, sin depender del color
del estado (`colorDeNodo`) para leerse:

- `bloqueado`: una torre en ruinas, envuelta en niebla, portón tapiado con
  tablones y cadenas, sin bandera — lejana y cerrada por FORMA, no solo por
  el gris de `p.textoSecundario`.
- `enConstruccion`: una torre a medio levantar, con andamios de madera y una
  fragua encendida a su base — la escena se ve activa, a medio terminar.
- `disponible`: un puesto de avanzada chico y bajo, portón abierto, una sola
  bandera modesta — abierto pero sin nada grande todavía.
- `actual`: NO es un edificio — el caminante real ya ocupa ese punto
  (`CaminanteEnSenda`), así que dibujar otra figura ahí compite con él. Es un
  asta con estandarte ondeando y un brasero encendido a su base: la marca de
  "acá, ahora mismo" sin duplicar al personaje.
- `completado`: una torre completa, en pie, sin daños, bandera grande
  desplegada en lo alto, ventanas iluminadas — el opuesto exacto de la
  arruinada.
- `tesoro` (`TipoParada.tesoro`, hoy con `Icons.emoji_events_rounded`,
  siempre el mismo trofeo sin importar el estado del nodo): un castillo
  grande, con varias torres, banderas grandes y detalles dorados —
  deliberadamente el único landmark de otra escala, mucho más grande y
  elaborado que cualquiera de los cinco de arriba.

## Por qué una lámina para los 5 estados, y el tesoro aparte

Misma razón ya documentada para el personaje (`experimento_figura_mundo.py`):
pedirle al modelo un dibujo por llamada arriesga que cada uno salga en un
estilo o paleta ligeramente distinta; una rejilla en una sola llamada
mantiene coherencia entre los 5 estados, que tienen que leerse como el mismo
"lenguaje visual del Reino". El tesoro se pide en una llamada aparte a
propósito: si compartiera celda con los otros 5, quedaría forzado al mismo
tamaño de celda que ellos, y el punto entero es que se vea claramente más
grande e importante — el único landmark verdaderamente distinto.

## Por qué esto usa el pipeline del personaje, no el del terreno

`experimento_terreno_mundo.py` genera sobre lienzo opaco, sin recortar nada,
a propósito: es una textura de fondo que se repite sin límite, y su propio
docstring dice explícitamente que NO dibuja "ningún objeto grande, único o
repetido de forma obvia" porque un elemento así desentonaría al repetirse.
Una estructura es exactamente eso: un objeto grande, único y discreto,
posicionado en un punto exacto de la senda (la parada), igual que el
caminante. Por eso este script reusa el pipeline de
`experimento_figura_mundo.py`: fondo magenta (`vestir.FONDO`), recorte a la
silueta con transparencia real (`vestir.solo_fondo`), sin `solo_fondo` en
modo terreno ni nada de `pintor_senda.dart`.

## Qué NO hace este script

No decide dónde ni a qué tamaño se pinta cada estructura sobre la senda
(`Positioned`, `Stack`, anclaje al `centro` de la parada) — eso es trabajo
de Flutter y lo hace otro diseñador en paralelo. Tampoco registra las
carpetas nuevas en `pubspec.yaml` (`assets/arte/mundo/estructuras/`) — hace
falta agregarlas ahí, mismo patrón que las entradas ya existentes de
`assets/arte/mundo/masculino/acero/` y `assets/arte/mundo/terreno/`, antes
de que Flutter pueda cargar estos archivos.

## Uso

    python scripts/experimento_estructuras_mundo.py                      # nada, valida el entorno
    python scripts/experimento_estructuras_mundo.py --aplicar                     # los 5 estados, cuesta céntimos
    python scripts/experimento_estructuras_mundo.py --aplicar --lamina tesoro     # el castillo, aparte
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "arte" / "experimentos_mundo"
ASSETS = RAIZ / "app" / "assets" / "arte" / "mundo" / "estructuras"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vestir import FONDO, clave_openai, solo_fondo  # noqa: E402 - tras el sys.path.insert

LIENZO = 1024

#: Mismo lenguaje visual ya aprobado para el personaje y el terreno
#: (`experimento_figura_mundo.py.ESTILO_SIN_IMAGEN_DE_PARTIDA`,
#: `experimento_terreno_mundo.py.ESTILO`): esta también es una generación de
#: cero, sin imagen de partida que preservar.
ESTILO = (
    "Estilo de ilustración: contorno de tinta oscura de grosor constante "
    "alrededor de cada forma, sombreado plano en dos o tres tonos planos por "
    "celdas, sin aerógrafo, sin degradados suaves y sin brillos especulares. "
    "Vista de frente, ligeramente elevada, la misma perspectiva que un mapa "
    "de nivel de videojuego móvil (como los mapas de Candy Crush o Clash "
    "Royale). Sin ningún texto, número ni etiqueta dibujado en la lámina."
)

#: La rejilla de los 5 `EstiloNodo` (orden fila por fila, izquierda a
#: derecha): 2 filas × 3 columnas, la celda 6 vacía. El orden sigue el viaje
#: real del aprendiz —cerrado, en obra, abierto, aquí, superado— para que sea
#: fácil de verificar a ojo contra la lámina cruda antes de recortar.
PROMPT_ESTADOS = (
    "Una lámina de ilustraciones sobre fondo {fondo}: una rejilla de 2 filas "
    "por 3 columnas, seis celdas iguales en tamaño separadas por líneas "
    "finas, cada estructura apoyada sobre el borde inferior de su propia "
    "celda (aunque cada una tenga su propia altura — no fuerces la misma "
    "altura en las seis). "
    "Fila superior, de izquierda a derecha: "
    "Celda 1: una torre de piedra en ruinas, mitad derrumbada, envuelta en "
    "niebla, sin bandera, con el portón tapiado con tablones cruzados y "
    "una cadena — se lee lejana, abandonada y cerrada. "
    "Celda 2: una torre de piedra a medio construir, rodeada de andamios de "
    "madera, con una fragua encendida y un yunque a su base y chispas "
    "naranjas saltando del fuego — se lee a medio terminar, activa. "
    "Celda 3: un puesto de avanzada pequeño y bajo, de madera y piedra, con "
    "el portón abierto de par en par y una sola bandera pequeña ondeando en "
    "un mástil corto — se lee abierto pero modesto, recién empezado. "
    "Fila inferior, de izquierda a derecha: "
    "Celda 4: SOLO un asta de madera clavada en el suelo con un estandarte "
    "largo ondeando al viento y, a su base, un brasero de hierro encendido "
    "con una llama alta — nada de edificio ni de figura, solo el asta y el "
    "fuego, como una marca de campamento. "
    "Celda 5: una torre de piedra completa y en perfecto estado, sin ningún "
    "daño, con su bandera grande completamente desplegada en lo más alto y "
    "las ventanas iluminadas por dentro con luz cálida — se lee conquistada, "
    "en pie con orgullo. "
    "Celda 6: vacía, del mismo color de fondo que las otras cinco, sin "
    "ningún dibujo dentro. "
    "{estilo}"
).format(fondo=FONDO, estilo=ESTILO)

#: El tesoro, en su propia llamada: el único landmark de otra escala.
PROMPT_TESORO = (
    "Una ilustración sobre fondo {fondo}: un castillo grande e imponente, "
    "con al menos tres torres de distinta altura, muros almenados, un "
    "portón principal grande y dos banderas grandes ondeando en las torres "
    "más altas, ventanas iluminadas con luz cálida y remates dorados en las "
    "puntas de las torres y el portón — claramente el edificio más grande, "
    "elaborado e importante de todos, mucho más grande que un puesto de "
    "avanzada o una sola torre. Apoyado sobre una única línea de base cerca "
    "del borde inferior del lienzo, ocupando la mayor parte del alto "
    "disponible, sin nada más dibujado alrededor. "
    "{estilo}"
).format(fondo=FONDO, estilo=ESTILO)

#: Nombre de archivo final por celda de `PROMPT_ESTADOS`, en el mismo orden
#: fila-por-fila del prompt. `None` = la celda 6, vacía, se descarta.
#: El nombre de archivo es una decisión de este script, no del otro
#: diseñador: usa el valor del enum `EstiloNodo` en snake_case
#: (`app/lib/pantallas/aventura/widgets/nodos_mapa.dart`) para que mapear
#: estado -> archivo sea un `switch` directo del lado Flutter.
ARCHIVOS_ESTADOS = (
    "bloqueado",
    "en_construccion",
    "disponible",
    "actual",
    "completado",
    None,
)

#: El modelo dibuja un marco negro alrededor de la lámina entera (y las
#: líneas que separan las celdas) de unos 6px — mismo fallo ya documentado en
#: `experimento_figura_mundo.py.MARGEN_BORDE`: sin recortarlo antes, ese
#: marco cuenta como "figura" y la silueta sale del tamaño de la celda
#: entera.
MARGEN_BORDE = 14

#: Alto final (dentro del lienzo maestro de 1024, antes de que Flutter lo
#: reescale a los ~80-140dp de pantalla) de la estructura más alta de la
#: lámina de estados (`completado`, la torre en pie) — el resto de las
#: celdas comparten esta misma escala (no se reescala cada una por separado
#: a este alto), así que una torre en ruinas más baja o un puesto más chico
#: SIGUEN viéndose más chicos: la diferencia de tamaño real es parte de la
#: lectura, igual que ya decide `recortar_casillas(..., escala_independiente=False)`
#: para el reposo del personaje.
ALTO_ESTRUCTURA_MAYOR = 460

#: El tesoro se genera y escala aparte, más alto que cualquier estructura de
#: la lámina de estados — el punto es que se note "más grande" incluso antes
#: de que el otro diseñador decida el tamaño final en dp.
ALTO_TESORO = 760

#: Misma línea de base para las 6 estructuras dentro del lienzo maestro,
#: dejando margen abajo para una sombra o base de terreno — mismo rol que
#: `vestir.BASE_Y` para el personaje, con un valor propio porque estas
#: estructuras no comparten el ancla de pies del personaje.
BASE_Y = 980


def pedir_generacion(prompt: str) -> bytes:
    """Generación de imágenes, sin base ni máscara — ninguna estructura tiene
    identidad previa que preservar."""
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


def _recortar_a_silueta(cruda: Image.Image) -> Image.Image:
    """La silueta real de un lienzo COMPLETO (1024×1024), fondo transparente,
    sin escalar — mismo procedimiento que
    `experimento_figura_mundo.py._recortar_a_silueta`. Solo para `recortar_tesoro`:
    `recortar_estados` NO puede llamar a esto por celda, ver `_bbox_ya_con_alfa`."""
    sin_marco = cruda.crop((MARGEN_BORDE, MARGEN_BORDE, cruda.width - MARGEN_BORDE, cruda.height - MARGEN_BORDE))
    alfa = (~solo_fondo(sin_marco)).astype("uint8") * 255
    con_alfa = sin_marco.copy()
    con_alfa.putalpha(Image.fromarray(alfa, mode="L"))
    bbox = con_alfa.split()[3].getbbox()
    if bbox is None:
        raise SystemExit("No se encontró estructura sobre el fondo en esta celda.")
    return con_alfa.crop(bbox)


def _bbox_ya_con_alfa(celda_con_alfa: Image.Image) -> Image.Image:
    """Recorta una celda que YA tiene el canal alfa resuelto a su bbox real
    — sin volver a llamar a `solo_fondo`. Ver el comentario en
    `recortar_estados` sobre por qué el fondo se separa antes de partir en
    celdas, no celda por celda."""
    bbox = celda_con_alfa.split()[3].getbbox()
    if bbox is None:
        raise SystemExit("No se encontró estructura sobre el fondo en esta celda.")
    return celda_con_alfa.crop(bbox)


def _pegar_centrado(silueta: Image.Image, alto_final: int) -> Image.Image:
    """La silueta reescalada a `alto_final` y pegada en un lienzo
    1024×1024 transparente, con la base en `BASE_Y` — mismo anclaje que
    `Caminante` espera del personaje (pies en una línea fija, no centrado)."""
    escala = alto_final / silueta.height
    redimensionada = silueta.resize(
        (max(1, round(silueta.width * escala)), alto_final), Image.LANCZOS
    )
    hoja = Image.new("RGBA", (LIENZO, LIENZO), (0, 0, 0, 0))
    hoja.paste(redimensionada, ((LIENZO - redimensionada.width) // 2, BASE_Y - alto_final), redimensionada)
    return hoja


def recortar_estados(lamina: Image.Image) -> dict[str, Image.Image]:
    """Las 5 estructuras nombradas de la rejilla 2×3, ya recortadas, a
    escala compartida (medida en la celda de `completado`) y pegadas al
    lienzo maestro. La celda 6 (vacía) se descarta sola, por `ARCHIVOS_ESTADOS`.

    El fondo se separa UNA SOLA VEZ, sobre la lámina entera (1024×1024) —
    NO celda por celda. `solo_fondo` decide qué método usar comparando el
    área de magenta contra un 10% de un lienzo de referencia 1024×1024
    (`vestir.LIENZO`); pasarle una celda mucho más chica, con una
    estructura grande que deja menos del 10% de ESA celda en magenta (así
    tenga de sobra, proporcionalmente, para leerse a ojo como "la mayoría
    del fondo"), hace que caiga a su rama de respaldo —pixeles oscuros
    pegados al borde—, que no reconoce un fondo magenta en absoluto: el
    resultado es una celda entera opaca, magenta incluido. Bug real,
    encontrado recién al medir el canal alfa con Pillow, no a ojo: cuatro
    de las cinco celdas salían con un rectángulo magenta opaco detrás de la
    estructura antes de este arreglo.
    """
    lamina_rgba = lamina.convert("RGBA")
    alfa_completa = (~solo_fondo(lamina_rgba)).astype("uint8") * 255
    con_alfa_completa = lamina_rgba.copy()
    con_alfa_completa.putalpha(Image.fromarray(alfa_completa, mode="L"))

    ancho_celda = lamina.width // 3
    alto_celda = lamina.height // 2
    siluetas: dict[str, Image.Image] = {}
    for i, nombre in enumerate(ARCHIVOS_ESTADOS):
        if nombre is None:
            continue
        fila, columna = divmod(i, 3)
        celda = con_alfa_completa.crop(
            (columna * ancho_celda, fila * alto_celda, (columna + 1) * ancho_celda, (fila + 1) * alto_celda)
        )
        # Recién acá se descarta el marco/línea divisoria entre celdas —
        # con el alfa ya resuelto sobre la lámina entera, este recorte es
        # solo para tirar el borde, no para volver a separar fondo de figura.
        sin_marco = celda.crop(
            (MARGEN_BORDE, MARGEN_BORDE, celda.width - MARGEN_BORDE, celda.height - MARGEN_BORDE)
        )
        siluetas[nombre] = _bbox_ya_con_alfa(sin_marco)

    escala_compartida = ALTO_ESTRUCTURA_MAYOR / siluetas["completado"].height
    return {
        nombre: _pegar_centrado(silueta, round(silueta.height * escala_compartida))
        for nombre, silueta in siluetas.items()
    }


def recortar_tesoro(lamina: Image.Image) -> Image.Image:
    """El castillo, recortado del lienzo entero (una sola "celda") y
    reescalado a `ALTO_TESORO` — independiente de la escala de los estados,
    a propósito: tiene que verse más grande que cualquiera de ellos."""
    silueta = _recortar_a_silueta(lamina.convert("RGBA"))
    return _pegar_centrado(silueta, ALTO_TESORO)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--aplicar", action="store_true", help="Llama al modelo. Cuesta dinero.")
    p.add_argument(
        "--lamina",
        choices=("estados", "tesoro"),
        default="estados",
        help="Qué lámina pedir y procesar: los 5 EstiloNodo, o el tesoro aparte.",
    )
    args = p.parse_args(argv)

    prompt = PROMPT_ESTADOS if args.lamina == "estados" else PROMPT_TESORO

    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / f"prompt_estructuras_{args.lamina}.txt").write_text(prompt, encoding="utf-8")
    print(f"prompt escrito en {SALIDA / f'prompt_estructuras_{args.lamina}.txt'} — revísalo antes de --aplicar")

    if not args.aplicar:
        print("Sin --aplicar no se llama al modelo.")
        return 0

    clave_openai()  # falla rápido y claro si falta la llave, antes de journalear nada
    bruto = pedir_generacion(prompt)
    ruta_lamina = SALIDA / f"lamina_estructuras_{args.lamina}.png"
    ruta_lamina.write_bytes(bruto)
    print(f"lámina en {ruta_lamina}")

    lamina = Image.open(ruta_lamina)
    ASSETS.mkdir(parents=True, exist_ok=True)
    if args.lamina == "estados":
        for nombre, estructura in recortar_estados(lamina).items():
            destino = ASSETS / f"{nombre}.webp"
            estructura.save(destino, "WEBP", lossless=False, quality=90)
            print(f"{nombre} -> {destino}")
    else:
        destino = ASSETS / "tesoro.webp"
        recortar_tesoro(lamina).save(destino, "WEBP", lossless=False, quality=90)
        print(f"tesoro -> {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
