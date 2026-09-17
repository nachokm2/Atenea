"""Le quita a cada arma el puño que trae dibujado y la lleva a la mano.

## Por qué

Cada pieza empuñada del catálogo trae su propio puño. El modelo lo añadió porque
el estilo obligatorio le prohibía tocar las manos existentes y a la vez se le
pedía un arma empuñada: obedecer a las dos cosas solo se puede dibujando una mano
nueva. En pantalla salen **dos**, y así lo encontró el primer aprendiz que equipó
una espada.

Apagar la del cuerpo no basta, y se comprobó componiendo la pila fuera de la
aplicación y mirándola. Dos razones:

1. **El puño no cae donde está la mano.** Hace falta mover la pieza entre 133 px
   hacia arriba y 184 px hacia abajo según cuál sea, y no hay constante posible:
   cada una lo puso donde quiso. Apagar sin mover deja el antebrazo cortado en
   seco con el puño flotando aparte.
2. **Ese puño no se tiñe.** Va pintado dentro del arma, así que se queda naranja
   elija el aprendiz el tono de piel que elija. Sobre «Ébano» es un puño naranja
   en un brazo marrón oscuro, y los seis tonos volverían a ser seis tonos que no
   se aplican del todo.

Lo que hace este guion es quitar el puño dibujado y mover la pieza para que la
empuñadura quede donde está la mano del cuerpo. Entonces agarra esa —que sí se
tiñe, y que es la de esta figura— y no hay nada que apagar.

No gasta ninguna llamada a la API. El arte que ya se pagó se recorta y se coloca.

## Cómo distingue un puño de un palo

Por la forma, no por el color. El color no vale: el predicado de piel da 78 % de
«piel» en `baston_aprendiz` y 66 % en `arco_fresno`, porque la madera clara es
del mismo color que la piel. Borrar por color destruiría el bastón y el arco.

Pero un puño es **compacto** y una vara es **alargada**, y ahí no hay solape:

    puños medidos     42-50 px de ancho, alargamiento 1,16 a 1,45
    madera y metal    alargamiento 1,63 a 12,25

## Lo que no toca

Una pieza a la que no se le encuentra puño se deja **exactamente como está** y se
dice por qué. Es el caso de `arco_bosque_antiguo`, que parece no llevar ninguno.
Vale más una pieza sin tocar que una pieza rota.

Los originales se guardan en `_con_puno/` dentro de la misma carpeta, así que el
guion se puede repetir sin degradar nada: siempre parte del original.

Uso:

    python scripts/quitar_punos.py            # las 30 piezas, y una hoja de contactos
    python scripts/quitar_punos.py --simular  # dice qué haría y no escribe
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

RAIZ = pathlib.Path(__file__).resolve().parent.parent

#: El taller, que es de donde exporta `exportar_capas.py`.
TALLER = RAIZ / "arte" / "capas"

#: Los cuerpos ya exportados, de donde se lee dónde está la mano.
CUERPOS = RAIZ / "app" / "assets" / "arte" / "capas" / "cuerpos"

#: Dónde se dejan las hojas de contactos para mirarlas.
DIAGNOSTICO = RAIZ / "arte" / "diagnostico"

#: Las dos figuras sobre las que se dibujó cada pieza.
#:
#: Las piezas son por familia, no por figura: las otras dos de cada familia usan
#: las mismas y el cliente las ajusta con `AjusteDeFigura`. Así que el puño hay
#: que llevarlo a la mano de **estas**, que son las canónicas.
CANONICAS = ("base_masculino_002", "base_femenino_002")

#: Qué ranura va en qué mano, desde quien mira.
EN_LA_MANO = {"weapon": "right", "offhand": "left"}

#: Los archivos de trabajo que acompañan a cada capa y no son la capa.
#:
#: Los mismos que filtra `exportar_capas.py`. Si no se filtran aquí también, el
#: guion trabaja sobre las máscaras y los brutos —no rompe nada, porque no los
#: exporta nadie, pero enseña setenta y cinco líneas donde hay quince—.
INTERMEDIOS = ("partida_", "mascara_", "control_", "bruto_", "prueba_")
VISTAS = ("_sola", "_puesta")

#: Un píxel cuenta como dibujo a partir de esta opacidad.
OPACO = 40

#: Un trozo más pequeño que esto no es un puño, es una salpicadura.
PUNO_MINIMO = 400

#: Un puño es compacto. Por encima de esto es una vara, una hoja o una correa.
#:
#: Los siete puños medidos van de 1,16 a 1,45 y lo siguiente empieza en 1,63, así
#: que el corte cae en un hueco ancho y no en mitad de una nube de puntos.
ALARGAMIENTO_MAXIMO = 1.55

#: Y tiene el ancho de una mano. Descarta trozos compactos pero diminutos.
ANCHO_MINIMO = 35

#: Para el caso del arco, donde la empuñadura parte el puño en varios trozos.
#:
#: Se admiten piezas menos compactas y más pequeñas, pero solo si juntas vuelven
#: a formar algo con forma de puño y están pegadas entre sí.
FRAGMENTO_MINIMO = 300
FRAGMENTO_ALARGAMIENTO = 2.2
FRAGMENTO_DISTANCIA = 60

#: Y juntos tienen que dar una mano, no una uña.
#:
#: Sin este suelo, `arco_bosque_antiguo` juntaba 656 px de sombras sueltas, los
#: tomaba por un puño y borraba un trozo del arco. Se vio en la hoja de
#: contactos: el arco salía convertido en una raya.
FRAGMENTO_JUNTOS_MINIMO = 900

#: Lo que queda pegado al puño y también es la mano que dibujó el modelo.
#:
#: Junto al puño suele quedar un trozo de muñeca suelto, más alargado que un
#: puño, que el filtro de forma no recoge: en la hoja de contactos son astillas
#: naranjas al lado de la empuñadura. Se borran las que estén pegadas al puño
#: **y sean pequeñas**. El tamaño es lo que salva la madera: la rama del arco
#: mide 3.873 px y la vara del bastón 6.144, así que ninguna entra aquí.
ASTILLA_MAXIMA = 1200
ASTILLA_DISTANCIA = 25

#: Y solo en las piezas donde el color signifique algo.
#:
#: Este paso borra por color lo pequeño que esté pegado al puño, y en una pieza
#: de madera «lo pequeño de color de piel» puede ser un tramo de la vara. Pasó:
#: con el borrado subido, el arco `fresno`, el bastón y `escudo_primer_desafio`
#: salieron partidos por la mitad en la hoja de contactos.
#:
#: Donde el color de piel pasa de esta parte de la pieza es que la pieza **es**
#: de ese color, y entonces solo se toca lo que la forma confirmó que es un puño.
#: Medido: 15-23 % en las espadas y cetros, 41 % en un arco, 66 % en el otro,
#: 78 % en el bastón.
PIEL_QUE_YA_NO_INFORMA = 0.40

#: Las piezas de la mano secundaria no se mueven, solo se les quita la mano.
#:
#: Un escudo va atado al antebrazo, no agarrado en el centro de la mano, así que
#: llevar su puño al centro de la mano es justo lo que no hay que hacer:
#: `escudo_blason_reino` se iba medio fuera del cuadro por la izquierda. Se vio
#: en la hoja de contactos. Sin mover, los cinco escudos caen donde caían, que
#: es donde estaban bien.
NO_SE_MUEVEN = ("offhand",)


def _piel(a: np.ndarray) -> np.ndarray:
    """Los píxeles de color de piel. También los de madera clara, y por eso no basta."""
    r = a[:, :, 0].astype(int)
    g = a[:, :, 1].astype(int)
    b = a[:, :, 2].astype(int)
    return (a[:, :, 3] > OPACO) & (r > 150) & (r > b + 35) & (g > b + 10) & (g < r)


def _forma(mascara: np.ndarray) -> dict[str, float]:
    ys, xs = np.where(mascara)
    alto = int(ys.max() - ys.min() + 1)
    ancho = int(xs.max() - xs.min() + 1)
    return {
        "px": int(mascara.sum()),
        "ancho": ancho,
        "alto": alto,
        "alargamiento": max(alto, ancho) / max(1, min(alto, ancho)),
        "cx": float(xs.mean()),
        "cy": float(ys.mean()),
        "x0": int(xs.min()),
        "x1": int(xs.max()),
        "y0": int(ys.min()),
        "y1": int(ys.max()),
    }


def _distancia(a: dict[str, float], b: dict[str, float]) -> float:
    """Cuánto se separan dos trozos; cero si sus rectángulos se tocan."""
    dx = max(0, max(a["x0"], b["x0"]) - min(a["x1"], b["x1"]))
    dy = max(0, max(a["y0"], b["y0"]) - min(a["y1"], b["y1"]))
    return float(max(dx, dy))


def puno_de(a: np.ndarray) -> tuple[np.ndarray, str] | None:
    """La máscara del puño dibujado, o `None` si la pieza no lleva ninguno."""
    etiquetas, cuantas = ndimage.label(_piel(a))
    trozos: list[tuple[np.ndarray, dict[str, float]]] = []
    for i in range(1, cuantas + 1):
        m = etiquetas == i
        if m.sum() < FRAGMENTO_MINIMO:
            continue
        trozos.append((m, _forma(m)))

    compactos = [
        (m, f)
        for m, f in trozos
        if f["px"] >= PUNO_MINIMO
        and f["alargamiento"] <= ALARGAMIENTO_MAXIMO
        and f["ancho"] >= ANCHO_MINIMO
    ]
    if compactos:
        mejor = max(compactos, key=lambda par: par[1]["px"])
        return mejor[0], "de una pieza"

    # El arco: la empuñadura envuelta parte el puño en dedos sueltos. Se juntan
    # los trozos medio compactos que están pegados y se mira si el conjunto
    # vuelve a tener forma de puño.
    sueltos = [
        (m, f) for m, f in trozos if f["alargamiento"] <= FRAGMENTO_ALARGAMIENTO and f["ancho"] >= 25
    ]
    for semilla_m, semilla_f in sorted(sueltos, key=lambda par: -par[1]["px"]):
        junta = semilla_m.copy()
        forma = semilla_f
        for otro_m, otro_f in sueltos:
            if otro_f is semilla_f:
                continue
            if _distancia(forma, otro_f) <= FRAGMENTO_DISTANCIA:
                junta |= otro_m
                forma = _forma(junta)
        if (
            junta.sum() >= FRAGMENTO_JUNTOS_MINIMO
            and forma["alargamiento"] <= 1.8
            and forma["ancho"] >= ANCHO_MINIMO
        ):
            return junta, "juntando dedos sueltos"

    return None


def con_astillas(a: np.ndarray, puno: np.ndarray) -> np.ndarray:
    """El puño más los restos de muñeca que le quedan pegados.

    Ver [ASTILLA_MAXIMA]: se añade lo pequeño y pegado, nunca lo grande, que es
    donde viven la rama del arco y la vara del bastón.
    """
    piel = _piel(a)
    dibujo = int((a[:, :, 3] > OPACO).sum())
    if dibujo and piel.sum() / dibujo > PIEL_QUE_YA_NO_INFORMA:
        return puno

    cerca = ndimage.binary_dilation(puno, np.ones((3, 3)), iterations=ASTILLA_DISTANCIA)
    etiquetas, cuantas = ndimage.label(piel)
    junto = puno.copy()
    for i in range(1, cuantas + 1):
        trozo = etiquetas == i
        if (trozo & puno).any():
            continue
        if trozo.sum() <= ASTILLA_MAXIMA and (trozo & cerca).any():
            junto |= trozo
    return junto


def centro_de_la_mano(figura: str, lado: str) -> tuple[float, float]:
    ruta = CUERPOS / f"{figura}_hand_{lado}.webp"
    if not ruta.exists():
        raise SystemExit(f"falta {ruta}: ejecuta antes scripts/separar_manos.py")
    a = np.array(Image.open(ruta).convert("RGBA"))
    ys, xs = np.where(a[:, :, 3] > 0)
    return float(xs.mean()), float(ys.mean())


def _mover(a: np.ndarray, dx: int, dy: int) -> np.ndarray | None:
    """Corre el dibujo. Devuelve `None` si algo se saldría del lienzo."""
    alto, ancho = a.shape[:2]
    ys, xs = np.where(a[:, :, 3] > 0)
    if not len(xs):
        return a
    if not (0 <= xs.min() + dx and xs.max() + dx < ancho):
        return None
    if not (0 <= ys.min() + dy and ys.max() + dy < alto):
        return None
    movido = np.zeros_like(a)
    oy0, oy1 = max(0, dy), min(alto, alto + dy)
    ox0, ox1 = max(0, dx), min(ancho, ancho + dx)
    movido[oy0:oy1, ox0:ox1] = a[oy0 - dy : oy1 - dy, ox0 - dx : ox1 - dx]
    return movido


def procesar(origen: pathlib.Path, figura: str, simular: bool) -> dict[str, object]:
    ranura = origen.stem.rsplit("_", 1)[-1]
    lado = EN_LA_MANO[ranura]

    # Siempre se parte del original, para que repetir no degrade.
    guardado = origen.parent / "_con_puno" / origen.name
    if guardado.exists():
        fuente = guardado
    else:
        fuente = origen
        if not simular:
            guardado.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origen, guardado)

    a = np.array(Image.open(fuente).convert("RGBA"))
    hallazgo = puno_de(a)
    if hallazgo is None:
        return {"pieza": origen.stem, "estado": "sin puño; se deja como está"}

    puno, como = hallazgo
    # El sitio se toma del puño solo: es lo que agarra. Las astillas de muñeca se
    # borran también, pero moverían el centro hacia el codo si contaran.
    f = _forma(puno)
    mascara = con_astillas(a, puno)
    if ranura in NO_SE_MUEVEN:
        dx = dy = 0
    else:
        hx, hy = centro_de_la_mano(figura, lado)
        dx, dy = int(round(hx - f["cx"])), int(round(hy - f["cy"]))

    # Se borra el puño y su contorno de tinta, que va pegado a la piel y sin él
    # quedaría el dibujo de la mano sin relleno.
    limpia = a.copy()
    fuera = ndimage.binary_dilation(mascara, np.ones((3, 3)), iterations=5)
    limpia[:, :, 3] = np.where(fuera, 0, a[:, :, 3])

    movida = _mover(limpia, dx, dy)
    if movida is None:
        return {
            "pieza": origen.stem,
            "estado": f"no cabe movida ({dx:+d},{dy:+d}); se deja como está",
        }

    if not simular:
        Image.fromarray(movida).save(origen)
    return {
        "pieza": origen.stem,
        "estado": f"puño {f['px']:.0f} px {como}, movida ({dx:+d},{dy:+d})",
        "hecha": True,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--simular", action="store_true", help="dice qué haría y no escribe")
    args = p.parse_args(argv)

    if not TALLER.is_dir():
        print(f"No encuentro {TALLER}. Este guion trabaja sobre el taller, no sobre los recursos.")
        return 1

    hechas = 0
    for figura in CANONICAS:
        carpeta = TALLER / figura
        if not carpeta.is_dir():
            print(f"{figura}: no hay carpeta en el taller; se salta")
            continue
        piezas = sorted(
            f
            for f in carpeta.glob("*.png")
            if f.stem.rsplit("_", 1)[-1] in EN_LA_MANO
            and not f.stem.startswith(INTERMEDIOS)
            and not f.stem.endswith(VISTAS)
        )
        print(f"\n=== {figura} — {len(piezas)} piezas empuñadas ===")
        for pieza in piezas:
            r = procesar(pieza, figura, args.simular)
            hechas += bool(r.get("hecha"))
            print(f"  {r['pieza']:34} {r['estado']}")

    print(f"\n{hechas} piezas sin puño y colocadas.")
    if not args.simular:
        print("Ahora: python scripts/exportar_capas.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
