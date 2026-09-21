"""Saca a capa aparte la mano que cada arma trae dibujada, para poder teñirla.

## Por qué

Cada pieza empuñada del catálogo trae su propio puño. El modelo lo añadió porque
el estilo obligatorio le prohibía tocar las manos existentes y a la vez se le
pedía un arma empuñada: obedecer a las dos cosas solo se puede dibujando una mano
nueva. En pantalla salen **dos**, y así lo encontró el primer aprendiz que equipó
una espada.

## Dos caminos que se probaron, se midieron y no valen

Se dejan escritos porque son el motivo de que el bueno sea el tercero, y porque
los dos parecen razonables hasta que se miden.

1. **Borrar el puño del arma** y dejar que agarre la mano del cuerpo. Abre un
   hueco en la pieza, y la mano del cuerpo —que tendría que taparlo— es **más
   pequeña que el puño dibujado**: asomaban entre 434 y 2.204 px del hueco en las
   dieciocho armas. Una revisión pieza a pieza los llamó mordiscos en el gavilán
   y en la hoja.
2. **Taparlo**, dibujando la mano del cuerpo por encima sin borrar nada. Mejor
   —de 114 a 1.071 px— pero lo que queda a la vista es un filo naranja alrededor
   de una mano oscura, y se ve.

## El que sí

Ese puño **ya agarra el arma**: se dibujó agarrándola, con los dedos cerrados
sobre la empuñadura, que es algo que la mano en reposo del cuerpo no sabe hacer.
Lo único que le faltaba era ser del color del aprendiz.

Así que se saca a su propia capa, normalizada como la piel del cuerpo para que el
cliente pueda teñirla, y se borra de la pieza —sin dejar hueco, porque la capa
vuelve exactamente encima—. La pieza se corre además hasta la mano de la figura,
que es lo que hace que el brazo acabe donde empieza el puño. El cliente tiñe esa
capa y apaga la mano del cuerpo de ese lado.

No gasta ninguna llamada a la API: el arte que ya se pagó se recorta y se coloca.

## Cómo distingue un puño de un palo

Por la forma, no por el color. El color no vale: el predicado de piel da 78 % de
«piel» en `baston_aprendiz` y 66 % en `arco_fresno`, porque la madera clara es
del mismo color que la piel.

Pero un puño es **compacto** y una vara es **alargada**, y ahí no hay solape:

    puños medidos     42-50 px de ancho, alargamiento 1,16 a 1,45
    madera y metal    alargamiento 1,63 a 12,25

## Lo que no toca

**Nada de la mano secundaria.** Un escudo tapa el brazo, así que la mano que el
modelo le dibujó encima no compite con ninguna otra: no hay nada que arreglar. Y
tocarla salía caro —en un escudo la mano va pintada sobre la cara y debajo no hay
nada, así que sacarla dejaba el agujero a la vista—.

**Ni las piezas que quedarían peor.** Si a una no se le encuentra puño, o si el
que tiene dejaría demasiada muñeca al aire al apagar la mano del cuerpo, se deja
**exactamente como está** y se dice por qué. Son dos de las dieciocho. Vale más
una pieza sin tocar que una pieza rota, y eso hay que decírselo al cliente: por
eso el guion termina emitiendo la lista de las que sí tienen puño propio, que es
la que va en `Arte.conPunoPropio`.

Los originales se guardan en `_con_puno/` dentro de la misma carpeta, y el guion
**restaura desde ahí en cada ejecución antes de decidir nada**. Así, endurecer un
criterio no deja detrás el recorte que hizo la versión anterior: una pieza que el
guion decide no tocar queda como si el guion no existiera.

Uso:

    python scripts/quitar_punos.py            # las armas de las dos familias
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
#: Doscientos cuarenta, y el número tiene dueño: `arco_bosque_antiguo`
#: masculino. Su mano quedó partida en cuatro dedos de 209 a 328 px por la
#: cuerda y el vendaje del arco, así que con el umbral en 300 se descartaban dos
#: y los otros dos no llegaban al mínimo conjunto. Era la última pieza de las
#: dieciocho que seguía enseñando dos manos. Bajarlo a 240 no toca ninguna otra:
#: se comprobó comparando el puño de las dieciocho antes y después.
FRAGMENTO_MINIMO = 240
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
#: Alargamiento máximo del conjunto ya juntado, que es más permisivo que el de
#: una pieza sola (`ALARGAMIENTO_MAXIMO`) por una razón medida: un puño partido
#: en dorso y dedos se vuelve a juntar en una forma más alargada que el puño
#: entero, porque los dedos salen hacia el arma. Medido sobre las cuatro piezas
#: que pasan por aquí: 1,74 · 1,78 · 1,86 · 1,90. El tope está por encima de la
#: última.
#:
#: **No se sube `ALARGAMIENTO_MAXIMO` en su lugar**, y está probado: con 1,85 el
#: arco de fresno masculino pasa de un puño bueno de 1.936 px a un trozo de 789,
#: y el `arco_bosque_antiguo` femenino —que hoy funciona— deja de tener mano y
#: se queda como está. La madera del arco es del color de la piel, así que
#: relajar el filtro de pieza suelta deja entrar el brazo del arco.
JUNTOS_ALARGAMIENTO = 1.95

#: Tamaño máximo de un trozo suelto que todavía se considera parte del puño.
#:
#: Subido de 1.200 a 2.200 con la medida delante. A 1.200 se quedaban fuera dos
#: antebrazos: 2.038 px en `arco_bosque_antiguo` femenino y 1.628 px en
#: `cetro_bigquery` femenino. Eran justo los dos «restos pálidos» que se veían
#: en pantalla como una banda clara cruzando el muslo —clara y no del tono del
#: aprendiz, porque lo que no entra en la capa no se tiñe—.
#:
#: **Lo que hace segura la subida no es el número, es que la otra guarda hace el
#: trabajo.** Medido pieza a pieza: subir el tope solo absorbe esos dos trozos,
#: y los dos están a distancia de color 25 y 2 del puño, o sea que son piel. En
#: las otras dieciséis no entra nada nuevo: las cuatro de madera —`baston`, los
#: dos `arco_fresno`, `arco_bosque_antiguo` masculino— ni siquiera llegan aquí,
#: porque `PIEL_QUE_YA_NO_INFORMA` las corta antes; y en las demás, todo lo que
#: el tamaño dejaba pasar ya lo paraba el color. El envoltorio de la empuñadura
#: del arco —595 y 420 px, pegados al puño— sigue fuera por color, que es lo que
#: lo salva.
ASTILLA_MAXIMA = 2200

#: Y a qué distancia del puño se deja de buscar.
#:
#: Sesenta y no veinticinco: con el radio corto se quedaba fuera un trozo de
#: antebrazo que el modelo dibujó separado de los dedos, y se veía como una curva
#: naranja al lado de la mano —naranja en los seis tonos de piel, porque lo que
#: no entra en la capa no se tiñe—. De 25 a 60 se recogen 2.800 px más en las
#: dieciséis piezas, unos 175 por pieza. Por encima de 60 ya no aparece casi
#: nada: a 90 solo son 330 px más en total.
ASTILLA_DISTANCIA = 60

#: Y a qué distancia de color del puño deja de ser parte del puño.
#:
#: Distancia euclídea en RGB entre el tono medio del trozo y el del puño. Sesenta
#: separa el naranja plano de la mano del filo cálido de una hoja y del latón de
#: una vara, que es lo que se estaba comiendo.
ASTILLA_COLOR = 60.0

#: Cuánto se crece la mano para llevarse la tinta con que está dibujada.
#:
#: El perfil y las sombras de un puño no son piel —son más oscuros— así que el
#: recorte por color se lleva el relleno y deja el dibujo. Y lo que se queda en
#: la pieza no se tiñe: se veía como una curva naranja junto a la mano.
CONTORNO_CRECE = 5

#: Y qué cuenta como tinta de la mano y no del arma.
#:
#: El perfil de una mano es marrón: su canal rojo va bastante por encima del
#: azul. El acero de una guarda tiene los tres canales juntos, así que se queda.
TINTA_CALIDA = 25

#: El puño no se borra ni se tapa: se **saca a su propia capa y se tiñe**.
#:
#: Las dos primeras ideas están medidas y descartadas, y las medidas se dejan
#: escritas porque son el motivo:
#:
#: - **Borrarlo** abre un hueco en la pieza que tendría que tapar la mano del
#:   cuerpo, y la mano es más pequeña que el puño dibujado: entre 434 y 2.204 px
#:   del hueco asomaban en las dieciocho armas. Una revisión pieza a pieza los
#:   llamó mordiscos en el gavilán y en la hoja.
#: - **Taparlo** con la mano del cuerpo por encima deja a la vista de 114 a
#:   1.071 px de puño naranja alrededor de una mano oscura. Mejor, pero se ve.
#:
#: Lo que sí sale bien es reconocer que ese puño **ya está donde tiene que
#: estar**: agarra el arma, porque se dibujó agarrándola. Lo único que le falta
#: es ser del color del aprendiz. Así que se saca a una capa aparte, se
#: normaliza como la piel del cuerpo, y el cliente la tiñe y apaga la mano del
#: cuerpo de ese lado. No queda hueco —la capa vuelve exactamente encima— ni
#: fleco —no hay dos manos que solapen— y no se gasta arte nuevo.
#:
#: La pieza se sigue moviendo hasta la mano, y eso importa: es lo que hace que
#: el brazo acabe donde empieza el puño.

#: Cuánta muñeca se tolera al aire.
#:
#: Apagada la mano del cuerpo, el antebrazo acaba en un corte que tiene que tapar
#: el puño del arma. Medido, quedan de 0 a 204 px en quince de las dieciséis; la
#: que se pasa —`espada_entrenamiento` masculina, con 712— se queda sin tocar,
#: porque su puño es la mitad de grande que los demás.
MUNON_AL_AIRE = 260

#: Qué parte de la mano cuenta como muñeca, desde su borde superior.
ALTO_DE_LA_MUNECA = 45

#: Cuánto agujero se tolera cuando la salida es borrar en vez de teñir.
#:
#: Y se mide **solo donde se ve**: un agujero en el arma que cae sobre el cuerpo
#: deja ver el brazo, que es justo lo que se quiere; solo canta el que cae sobre
#: el fondo. Tardé en darme cuenta y estuve descartando esta vía con el número
#: equivocado.
#:
#: Mil cien porque `espada_entrenamiento` masculina deja 873 y, mirada a tamaño
#: real, no se le nota nada. Las demás piezas ni llegan aquí: se arreglan por la
#: vía buena, la de teñir.
HUECO_QUE_SE_VE = 1100

#: Un puño que deja muñeca al aire todavía puede hacer de mano **si es al menos
#: tan grande como la que sustituye**. Medido como fracción de la mano del
#: cuerpo de esa figura.
#:
#: Sale de mirar las dos piezas que pasan de `MUNON_AL_AIRE` y comparar sus
#: composiciones ampliadas, que es lo único que decide esto:
#:
#: * `arco_fresno` femenino — puño de 3.365 px, **1,77** veces la mano del
#:   cuerpo, 397 px de muñeca. Sacado se ve bien: una sola mano agarrando el
#:   arco. Dejado como estaba se ven **dos manos**, que es el fallo original.
#: * `espada_entrenamiento` masculino — puño de 954 px, **0,41**, 380 px de
#:   muñeca. Sacado se ve peor que antes: el puño sale roto en trozos y con un
#:   hueco entre el brazo y la mano.
#:
#: Quince píxeles de muñeca separan a esas dos —397 contra 380—, así que el tope
#: de muñeca no puede distinguirlas: eso sería afinar una constante a una
#: ventana en la que cabe cualquier pieza futura. El tamaño sí las separa, con
#: un factor cuatro de margen, y además significa algo: un puño pequeño con la
#: muñeca al aire se lee como un muñón.
PUNO_QUE_SUSTITUYE = 1.0

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

#: La mano secundaria no se toca. Nada de nada.
#:
#: Aquí borrar el puño **agujerea la pieza**, y es por dónde está dibujado. En un
#: arma el puño va delante de la empuñadura: al quitarlo aparece la empuñadura,
#: que ya estaba pintada debajo. En un escudo la mano va pintada **sobre la cara
#: del escudo**, y debajo no hay nada, así que queda el hueco. Ampliadas se ve
#: perfectamente: `escudo_blason_reino` salía con un agujero de lado a lado,
#: `escudo_primer_desafio` sin un trozo del borde y `tomo_erudito` con un hueco
#: blanco. Los tres estaban mejor antes.
#:
#: Y no hace falta tocarlos: un escudo tapa el brazo, así que la mano que el
#: modelo dibujó encima no compite con ninguna otra. El problema de las dos manos
#: es de las armas.
NO_SE_TOCAN = ("offhand",)

#: Piezas cuyo puño dibujado no puede hacer de mano y **toman prestado el de
#: otra pieza de la misma figura**.
#:
#: `espada_entrenamiento` masculina es el único caso, y llegó aquí después de
#: agotar las dos salidas del guion: su puño mide 954 px, el 0,41 de la mano del
#: cuerpo, así que sacarlo deja un muñón —compuesto y mirado: el puño sale roto
#: y con un hueco entre brazo y mano—; y borrarlo entero deja 2.685 px de
#: agujero contra el fondo, porque sobresale de la silueta de la mano.
#:
#: Prestar funciona porque **todos los puños acaban en el mismo sitio**: cada
#: capa se mueve para que su centro caiga en `centro_de_la_mano`, así que el
#: puño de una espada cae exactamente donde está la empuñadura de la otra. Se
#: compusieron los tres candidatos masculinos y se miraron: `espada_corta_acero`
#: es el que se asienta bajo el gavilán dejando ver el pomo. Mide 2.177 px, el
#: 0,93 de la mano del cuerpo, y tapa 127 de los 181 px de tinta que el borrado
#: deja dentro de la huella; quedan 54 px, que a tamaño de móvil son dos.
#:
#: Es prestado y no copiado a mano: el día que se redibuje la pieza, se quita
#: esta línea y su propio puño vuelve a mandar.
PUNO_PRESTADO: dict[tuple[str, str], str] = {
    ("base_masculino_002", "espada_entrenamiento_weapon"): "espada_corta_acero_weapon",
}


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


def _sin_huecos(mascara: np.ndarray) -> np.ndarray:
    """La máscara cerrada: lo que quede rodeado de mano, es mano.

    Las rayas que separan los dedos no son color piel, así que el etiquetado no
    las incluye y el borrado las dejaba en la pieza. En pantalla eso eran unos
    trazos marrones curvos flotando junto a la empuñadura, que es como se veía
    la espada de entrenamiento masculina.

    Es una corrección pequeña y acotada por su propia forma: solo puede añadir
    píxeles **encerrados** por el puño, nunca extenderlo hacia fuera. Medido en
    las dieciocho piezas: entre 0 y 270 px, y ninguna cambia de camino.
    """
    return ndimage.binary_fill_holes(mascara)


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
        return _sin_huecos(mejor[0]), "de una pieza"

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
            and forma["alargamiento"] <= JUNTOS_ALARGAMIENTO
            and forma["ancho"] >= ANCHO_MINIMO
        ):
            return _sin_huecos(junta), "juntando dedos sueltos"

    return None


def con_astillas(a: np.ndarray, puno: np.ndarray) -> np.ndarray:
    """El puño más los restos de muñeca que le quedan pegados.

    Ver [ASTILLA_MAXIMA]: se añade lo pequeño y pegado, nunca lo grande, que es
    donde viven la rama del arco y la vara del bastón.
    """
    piel = _piel(a)

    # Y solo donde el color signifique algo. En una pieza de madera clara «lo que
    # tiene color de piel» puede ser la propia vara: `baston_aprendiz` da 78 % y
    # `arco_fresno` 66 %. Se probó sin esta guarda y el bastón perdió un tramo
    # entero de la empuñadura tallada —el 11,9 % de la pieza—, visto comparando
    # el antes y el después. Ahí, solo el puño que la forma confirmó.
    dibujo = int((a[:, :, 3] > OPACO).sum())
    if dibujo and piel.sum() / dibujo > PIEL_QUE_YA_NO_INFORMA:
        return puno

    # Y del **mismo color** que el puño, no solo de color de piel.
    #
    # «Color de piel» es un abanico ancho: dentro caen el filo cálido de una hoja
    # y el latón de una vara, y si están pegados al puño se los llevaba por
    # delante. Se dibujó lo que se borraba —rojo el puño, cian lo añadido— y ahí
    # se vio: el cian mordía el gavilán de `espada_entrenamiento` y un tramo de
    # la vara de `cetro_bigquery`. El puño, en cambio, es un naranja plano, así
    # que exigir que el trozo tenga su mismo color deja fuera al metal.
    tono = a[puno][:, :3].astype(float).mean(axis=0)

    cerca = ndimage.binary_dilation(puno, np.ones((3, 3)), iterations=ASTILLA_DISTANCIA)
    etiquetas, cuantas = ndimage.label(piel)
    junto = puno.copy()
    for i in range(1, cuantas + 1):
        trozo = etiquetas == i
        if (trozo & puno).any():
            continue
        if trozo.sum() > ASTILLA_MAXIMA or not (trozo & cerca).any():
            continue
        if np.linalg.norm(a[trozo][:, :3].astype(float).mean(axis=0) - tono) > ASTILLA_COLOR:
            continue
        junto |= trozo
    return junto


#: Percentil de luminancia que se lleva al blanco al normalizar, como en
#: `separar_piel_y_pelo.py`: el cliente tiñe multiplicando, así que solo puede
#: oscurecer, y sin llevar los brillos al blanco el tono elegido saldría apagado.
BRILLO = 95


def _normalizar(rgb: np.ndarray, mascara: np.ndarray) -> np.ndarray:
    """Lleva los brillos de la región al blanco conservando el sombreado."""
    salida = rgb.astype(np.float32).copy()
    zona = rgb[mascara].astype(np.float32)
    if zona.size == 0:
        return rgb
    referencia = np.maximum(np.percentile(zona, BRILLO, axis=0), 12.0)
    salida[mascara] = np.clip(zona / referencia * 255.0, 0, 255)
    return salida.astype(np.uint8)


def _silueta(figura: str, lado: str) -> np.ndarray:
    """Lo que hay dibujado detrás del arma: el cuerpo y la mano de ese lado.

    Un agujero en la pieza que caiga aquí no se ve —deja ver el brazo—, así que
    esto es lo que separa un agujero real de uno inofensivo.
    """
    cuerpo = np.array(Image.open(CUERPOS / f"{figura}_sin_manos.webp").convert("RGBA"))
    return (cuerpo[:, :, 3] > OPACO) | mascara_de_la_mano(figura, lado)


def _banda_de_muneca(figura: str, lado: str) -> np.ndarray:
    """La parte alta de la mano del cuerpo: si queda al aire, se ve el corte."""
    mano = mascara_de_la_mano(figura, lado)
    arriba = int(np.where(mano)[0].min())
    banda = mano.copy()
    banda[arriba + ALTO_DE_LA_MUNECA :, :] = False
    return banda


def mascara_de_la_mano(figura: str, lado: str) -> np.ndarray:
    """La mano suelta del cuerpo, que es la que tapará el hueco."""
    ruta = CUERPOS / f"{figura}_hand_{lado}.webp"
    if not ruta.exists():
        raise SystemExit(f"falta {ruta}: ejecuta antes scripts/separar_manos.py")
    return np.array(Image.open(ruta).convert("RGBA"))[:, :, 3] > OPACO


def _correr(m: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """La misma máscara, movida: donde acabará el hueco una vez colocada la pieza."""
    alto, ancho = m.shape
    fuera = np.zeros_like(m)
    oy0, oy1 = max(0, dy), min(alto, alto + dy)
    ox0, ox1 = max(0, dx), min(ancho, ancho + dx)
    if oy0 < oy1 and ox0 < ox1:
        fuera[oy0:oy1, ox0:ox1] = m[oy0 - dy : oy1 - dy, ox0 - dx : ox1 - dx]
    return fuera


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


def con_su_contorno(a: np.ndarray, mano: np.ndarray) -> np.ndarray:
    """La mano más la tinta con que está dibujada: su perfil y sus sombras.

    Sin esto, la piel se lleva el relleno y **el dibujo se queda**: el perfil del
    pulgar seguía en la capa del arma, en naranja, y como lo que no entra en la
    capa no se tiñe, se veía una curva naranja al lado de la mano en los seis
    tonos de piel. Se localizó separando la pila capa a capa y mirándolas.

    Crece solo sobre tinta **cálida** —el perfil de una mano es marrón, no gris—
    para no llevarse el acero de la guarda, que tiene los tres canales juntos.
    Da igual pasarse un poco: lo que entra aquí no se borra, se tiñe, así que el
    peor caso es un píxel del arma del color de la piel, no un agujero.
    """
    r = a[:, :, 0].astype(int)
    b = a[:, :, 2].astype(int)
    calido = (a[:, :, 3] > 0) & (r > b + TINTA_CALIDA)
    crecida = ndimage.binary_dilation(mano, np.ones((3, 3)), iterations=CONTORNO_CRECE)
    return mano | (crecida & calido)


def _original(origen: pathlib.Path, simular: bool) -> pathlib.Path:
    """Devuelve la pieza a su estado original y dice de dónde leerla.

    Restaurar **siempre**, y no solo leer del respaldo, es lo que hace que
    cambiar las reglas no deje basura detrás. Costó un susto: al endurecer el
    criterio, `arco_bosque_antiguo` pasó a estar en la lista de las que no se
    tocan, y se quedó con el recorte que le había hecho la versión anterior del
    guion, porque saltarla significaba no volver a escribirla. Una pieza que el
    guion decide no tocar tiene que quedar como si el guion no existiera.
    """
    guardado = origen.parent / "_con_puno" / origen.name
    if not guardado.exists():
        if not simular:
            guardado.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origen, guardado)
        return origen
    if not simular:
        shutil.copy2(guardado, origen)
    return guardado


def procesar(origen: pathlib.Path, figura: str, simular: bool) -> dict[str, object]:
    ranura = origen.stem.rsplit("_", 1)[-1]
    fuente = _original(origen, simular)
    if ranura in NO_SE_TOCAN:
        return {"pieza": origen.stem, "estado": "mano secundaria; no se toca"}
    lado = EN_LA_MANO[ranura]

    a = np.array(Image.open(fuente).convert("RGBA"))
    hallazgo = puno_de(a)
    if hallazgo is None:
        return {"pieza": origen.stem, "estado": "sin puño; se deja como está"}

    puno, como = hallazgo
    f = _forma(puno)

    # Dos destinos distintos, y confundirlos fue el fallo que más tardó en verse.
    #
    # A la **capa teñible** va solo el puño y la tinta con que está dibujado: es
    # la mano que agarra, y es lo que sustituye a la del cuerpo.
    #
    # Lo demás que el modelo dibujó de piel alrededor —muñeca, un trozo de
    # antebrazo, un pedazo de manga— **se borra**. No es que estorbe: es que el
    # cuerpo ya tiene su antebrazo, y además la pieza se mueve, así que ese
    # segundo antebrazo acaba cruzado en diagonal por encima del pantalón. Se vio
    # montando la pila paso a paso: aparecía justo al añadir la capa del puño.
    mano = con_su_contorno(a, puno)
    de_sobra = con_astillas(a, puno) & ~mano

    hx, hy = centro_de_la_mano(figura, lado)
    dx, dy = int(round(hx - f["cx"])), int(round(hy - f["cy"]))

    # La capa de la mano del cuerpo se apaga cuando esta pieza está puesta, así
    # que el puño tiene que tapar la muñeca que queda al aire. Se comprueba, y
    # contando solo lo que de verdad va a quedar dibujado.
    queda = _correr((a[:, :, 3] > OPACO) & ~de_sobra, dx, dy)
    munon = int((_banda_de_muneca(figura, lado) & ~_correr(mano, dx, dy) & ~queda).sum())

    movida = _mover(a, dx, dy)
    if movida is None:
        return {
            "pieza": origen.stem,
            "estado": f"no cabe movida ({dx:+d},{dy:+d}); se deja como está",
        }

    mano_del_cuerpo = int(mascara_de_la_mano(figura, lado).sum())
    bastante_grande = mano_del_cuerpo > 0 and puno.sum() >= PUNO_QUE_SUSTITUYE * mano_del_cuerpo
    prestado = PUNO_PRESTADO.get((figura, origen.stem))
    if prestado and munon > MUNON_AL_AIRE and not bastante_grande:
        # El puño de otra pieza hace de mano. Se borra el propio igual que en el
        # camino de abajo —es el que no sirve— y la capa prestada lo sustituye.
        # No se comprueba el agujero: quien lo tapa ya no es la mano del cuerpo
        # sino la capa prestada, que se pinta encima y en el mismo sitio.
        fuente_puno = origen.parent / f"{prestado}_puno.png"
        if not fuente_puno.is_file():
            return {
                "pieza": origen.stem,
                "estado": f"quería el puño de {prestado} y no está; se deja como está",
            }
        if not simular:
            borrada = movida.copy()
            borrada[:, :, 3] = np.where(_correr(mano | de_sobra, dx, dy), 0, borrada[:, :, 3])
            Image.fromarray(borrada).save(origen)
            shutil.copyfile(fuente_puno, origen.parent / f"{origen.stem}_puno.png")
        return {
            "pieza": origen.stem,
            "estado": (
                f"su puño de {int(puno.sum())} px no sirve ({munon} px de muñeca al "
                f"aire); toma prestado el de {prestado}, movida ({dx:+d},{dy:+d})"
            ),
            "hecha": True,
        }

    if munon > MUNON_AL_AIRE and not bastante_grande:
        # Su puño es demasiado pequeño para hacer de mano: apagar la del cuerpo
        # dejaría el brazo cortado. Pero **al revés sí funciona**: si el dibujo
        # es pequeño se borra entero y lo tapa la mano del cuerpo, que en ese
        # caso se sigue pintando —y va encima del arma, que es lo que hace falta
        # para que parezca que la agarra—.
        #
        # El agujero que deja el borrado solo se ve donde cae sobre el fondo:
        # donde hay cuerpo detrás, deja ver el brazo, que es lo que se quiere.
        # Ese es el número que decide, y no el tamaño del agujero.
        visible = int((_correr(mano | de_sobra, dx, dy) & ~_silueta(figura, lado)).sum())
        if visible > HUECO_QUE_SE_VE:
            return {
                "pieza": origen.stem,
                "estado": (
                    f"su puño no puede hacer de mano ({munon} px de muñeca al aire) "
                    f"y borrarlo deja {visible} px de agujero a la vista; se deja como está"
                ),
            }
        if not simular:
            borrada = movida.copy()
            borrada[:, :, 3] = np.where(_correr(mano | de_sobra, dx, dy), 0, borrada[:, :, 3])
            Image.fromarray(borrada).save(origen)
        return {
            "pieza": origen.stem,
            "estado": (
                f"puño {int(puno.sum())} px, demasiado pequeño para hacer de mano: "
                f"se borra y la tapa la del cuerpo, agujero a la vista {visible} px, "
                f"movida ({dx:+d},{dy:+d})"
            ),
            "hecha": True,
        }

    # El puño sale a su propia capa, normalizado para poder teñirlo, y se borra
    # de la pieza. No queda hueco: la capa vuelve exactamente encima.
    capa = np.zeros_like(a)
    capa[mano] = a[mano]
    capa[:, :, :3] = _normalizar(capa[:, :, :3], mano)
    capa_movida = _mover(capa, dx, dy)
    # Y de la pieza se quita el puño —que vuelve en la capa— y también lo que
    # sobraba, que no vuelve en ninguna parte.
    movida[:, :, 3] = np.where(_correr(mano | de_sobra, dx, dy), 0, movida[:, :, 3])
    if not simular:
        Image.fromarray(capa_movida).save(origen.parent / f"{origen.stem}_puno.png")
    como = f"{como}, sobraban {int(de_sobra.sum())} px de brazo, muñeca al aire {munon} px"

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
            and not f.stem.endswith("_puno")
        )
        print(f"\n=== {figura} — {len(piezas)} piezas empuñadas ===")
        for pieza in piezas:
            r = procesar(pieza, figura, args.simular)
            hechas += bool(r.get("hecha"))
            print(f"  {r['pieza']:34} {r['estado']}")

    print(f"\n{hechas} piezas con el puño sacado a capa y colocadas.")

    # El cliente necesita saber cuáles traen puño propio **antes** de dibujar,
    # porque de eso depende que apague o no la mano del cuerpo, y preguntárselo
    # al disco en mitad de un `build` no se puede. Así que la lista se emite
    # aquí y se pega en `Arte.conPunoPropio`: este es el único sitio que la sabe.
    # Y **por familia**, no en una lista sola: tres piezas tienen puño en una
    # familia y no en la otra —a una no se le encuentra y a otra le quedaría
    # demasiada muñeca al aire—. Con una lista común, el cliente apagaría la mano
    # del cuerpo de la figura equivocada y le dejaría el brazo cortado.
    print("\nPara `Arte.conPunoPropio` en app/lib/design/arte.dart:\n")
    for figura in CANONICAS:
        familia = "masculino" if "masculino" in figura else "femenino"
        nombres = sorted(f.stem[: -len("_puno")] for f in (TALLER / figura).glob("*_puno.png"))
        print(f"    '{familia}': <String>{{  // {len(nombres)}")
        for nombre in nombres:
            print(f"      '{nombre}',")
        print("    },")
    if not args.simular:
        print("\nAhora: python scripts/exportar_capas.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
