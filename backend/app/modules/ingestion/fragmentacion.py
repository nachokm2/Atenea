"""Troceado por estructura y tamaño con solapamiento (§3.3 `document_chunks`, §5.8).

El troceador de Atenea no corta cada N caracteres: primero **entiende la estructura**
del documento y solo después empaqueta por tamaño. La razón es pedagógica antes que
técnica: una consulta SQL partida por la mitad genera lecciones y preguntas erróneas,
y una tabla sin su cabecera deja de significar nada.

Reglas, todas leídas de `ingestion.chunk` en `game_configs`
(`{"target_tokens": 450, "max_tokens": 800, "min_tokens": 80, "overlap_pct": 0.12}`):

1. **Bloques atómicos**: un bloque de código (vallas ``` o ~~~), una consulta SQL o una
   tabla **nunca se parten**, aunque superen `max_tokens`. Van en su propio fragmento
   si no caben en el que se está llenando.
2. **Prosa**: los párrafos se agrupan hasta acercarse a `target_tokens` y nunca pasan de
   `max_tokens`; un párrafo gigante se parte por frases, jamás a mitad de palabra.
3. **Solapamiento**: entre fragmentos de prosa consecutivos se arrastra la cola del
   anterior (`overlap_pct` del objetivo) para que una idea a caballo entre dos
   fragmentos siga siendo recuperable. No se solapa hacia un bloque atómico ni desde él.
4. **Mínimo**: un fragmento final por debajo de `min_tokens` se funde con el anterior,
   salvo que sea atómico.
5. `heading_path` guarda la pila de encabezados vigente (`["Capítulo 5. JOINs",
   "LEFT JOIN"]`), que el módulo de embeddings antepone al texto antes de embeber.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.enums import ChunkType
from app.modules.ingestion.almacenamiento import hash_texto
from app.modules.ingestion.extraccion import RangoPagina, estimar_tokens

#: Valores de respaldo de `ingestion.chunk` (§5.8) por si la configuración no está cargada.
CHUNK_POR_DEFECTO: dict[str, float] = {
    "target_tokens": 450,
    "max_tokens": 800,
    "min_tokens": 80,
    "overlap_pct": 0.12,
}

_ENCABEZADO = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
_ENCABEZADO_SUBRAYADO = re.compile(r"^(=+|-+)\s*$")
_VALLA = re.compile(r"^\s{0,3}(```+|~~~+)(.*)$")
_LISTA = re.compile(r"^\s*([-*+]\s+|\d+[.)]\s+)")
_FRASE = re.compile(r"(?<=[.!?:;])\s+(?=[^\s])|\n")

#: Palabras clave con las que empieza una sentencia SQL. Una racha de líneas así se
#: trata como bloque de código aunque el autor no la haya puesto entre vallas.
_SQL_INICIAL = re.compile(
    r"^\s*(select|insert\s+into|update|delete\s+from|create\s+(table|view|index|schema|database)"
    r"|alter\s+table|drop\s+(table|view|index)|with|from|where|join|left\s+join|right\s+join"
    r"|inner\s+join|full\s+join|group\s+by|order\s+by|having|union|values|set|on|and|or"
    r"|limit|offset|begin|commit|rollback|explain)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class Bloque:
    """Unidad estructural del documento antes de empaquetarla en fragmentos."""

    tipo: ChunkType
    texto: str
    char_start: int
    char_end: int
    encabezados: list[str] = field(default_factory=list)
    #: `True` cuando el bloque no se puede partir bajo ningún concepto.
    atomico: bool = False
    tokens: int = 0
    #: `True` si el bloque es la línea de un encabezado (no es contenido propiamente dicho).
    es_encabezado: bool = False


@dataclass(slots=True)
class Fragmento:
    """Fragmento listo para persistir en `document_chunks`."""

    chunk_index: int
    chunk_type: ChunkType
    heading_path: list[str]
    texto: str
    token_count: int
    char_start: int
    char_end: int
    content_hash: str
    page_start: int | None = None
    page_end: int | None = None


# ---------------------------------------------------------------------------
# Parámetros
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ParametrosTroceo:
    """Parámetros efectivos de `ingestion.chunk`."""

    target_tokens: int
    max_tokens: int
    min_tokens: int
    overlap_pct: float

    @property
    def tokens_solape(self) -> int:
        """Tokens que se arrastran de un fragmento de prosa al siguiente."""
        return max(0, round(self.target_tokens * self.overlap_pct))


def parametros_de(configuracion: dict | None) -> ParametrosTroceo:
    """Construye los parámetros a partir del mapa `ingestion.chunk` de `game_configs`."""
    datos = dict(CHUNK_POR_DEFECTO)
    datos.update({clave: valor for clave, valor in (configuracion or {}).items() if valor is not None})
    objetivo = max(1, int(datos["target_tokens"]))
    maximo = max(objetivo, int(datos["max_tokens"]))
    minimo = max(0, min(int(datos["min_tokens"]), objetivo))
    solape = min(0.9, max(0.0, float(datos["overlap_pct"])))
    return ParametrosTroceo(
        target_tokens=objetivo, max_tokens=maximo, min_tokens=minimo, overlap_pct=solape
    )


# ---------------------------------------------------------------------------
# Fase 1: estructura del documento
# ---------------------------------------------------------------------------


def _linea_de_tabla(linea: str) -> bool:
    """Una línea de tabla Markdown tiene al menos dos tuberías."""
    return linea.count("|") >= 2


def _fin_de_linea(texto: str, posicion: int) -> int:
    """Offset del final de la línea que empieza en `posicion` (incluido el salto)."""
    fin = texto.find("\n", posicion)
    return len(texto) if fin == -1 else fin + 1


def analizar_bloques(texto: str) -> list[Bloque]:
    """Parte el texto en bloques estructurales conservando sus offsets exactos.

    Reconoce encabezados Markdown (con `#` y subrayados `===` / `---`), bloques de
    código entre vallas, rachas de SQL sin vallas, tablas de tuberías, listas y
    párrafos de prosa. Cada bloque recuerda la pila de encabezados vigente.
    """
    bloques: list[Bloque] = []
    pila: list[str] = []
    lineas: list[tuple[str, int, int]] = []
    posicion = 0
    for linea in texto.splitlines(keepends=True):
        lineas.append((linea.rstrip("\n"), posicion, posicion + len(linea)))
        posicion += len(linea)

    def anadir(
        tipo: ChunkType, desde: int, hasta: int, *, atomico: bool, encabezado: bool = False
    ) -> None:
        crudo = texto[desde:hasta]
        contenido = crudo.strip("\n")
        if not contenido.strip():
            return
        recorte_inicial = len(crudo) - len(crudo.lstrip("\n"))
        bloques.append(
            Bloque(
                tipo=tipo,
                texto=contenido,
                char_start=desde + recorte_inicial,
                char_end=desde + recorte_inicial + len(contenido),
                encabezados=list(pila),
                atomico=atomico,
                tokens=estimar_tokens(contenido),
                es_encabezado=encabezado,
            )
        )

    indice = 0
    total = len(lineas)
    while indice < total:
        contenido, inicio, fin = lineas[indice]
        recortada = contenido.strip()

        if not recortada:
            indice += 1
            continue

        # --- Encabezado ATX (`## Título`) -------------------------------------
        encabezado = _ENCABEZADO.match(recortada)
        if encabezado:
            nivel = len(encabezado.group(1))
            titulo = encabezado.group(2).strip()
            del pila[nivel - 1 :]
            while len(pila) < nivel - 1:
                pila.append("")
            pila.append(titulo)
            anadir(ChunkType.PROSE, inicio, fin, atomico=False, encabezado=True)
            indice += 1
            continue

        # --- Encabezado subrayado (`Título` + `=====`) ------------------------
        if indice + 1 < total and _ENCABEZADO_SUBRAYADO.match(lineas[indice + 1][0].strip()):
            nivel = 1 if lineas[indice + 1][0].strip().startswith("=") else 2
            del pila[nivel - 1 :]
            while len(pila) < nivel - 1:
                pila.append("")
            pila.append(recortada)
            anadir(
                ChunkType.PROSE, inicio, lineas[indice + 1][2], atomico=False, encabezado=True
            )
            indice += 2
            continue

        # --- Bloque de código entre vallas (atómico) --------------------------
        valla = _VALLA.match(contenido)
        if valla:
            marca = valla.group(1)
            cierre = indice + 1
            while cierre < total:
                candidata = _VALLA.match(lineas[cierre][0])
                if candidata and candidata.group(1)[0] == marca[0] and len(
                    candidata.group(1)
                ) >= len(marca):
                    break
                cierre += 1
            fin_bloque = lineas[min(cierre, total - 1)][2]
            anadir(ChunkType.CODE, inicio, fin_bloque, atomico=True)
            indice = cierre + 1
            continue

        # --- Tabla de tuberías (atómica) --------------------------------------
        if _linea_de_tabla(contenido):
            cierre = indice
            while cierre < total and _linea_de_tabla(lineas[cierre][0]):
                cierre += 1
            if cierre - indice >= 2:
                anadir(ChunkType.TABLE, inicio, lineas[cierre - 1][2], atomico=True)
                indice = cierre
                continue

        # --- Racha de SQL sin vallas (atómica) --------------------------------
        if _SQL_INICIAL.match(contenido):
            cierre = indice
            while cierre < total and lineas[cierre][0].strip():
                cierre += 1
            tramo = [lineas[fila][0] for fila in range(indice, cierre)]
            con_sql = sum(1 for linea in tramo if _SQL_INICIAL.match(linea))
            tiene_final = any(";" in linea for linea in tramo)
            if len(tramo) >= 2 and (con_sql * 2 >= len(tramo) or tiene_final):
                anadir(ChunkType.CODE, inicio, lineas[cierre - 1][2], atomico=True)
                indice = cierre
                continue

        # --- Lista -------------------------------------------------------------
        if _LISTA.match(contenido):
            cierre = indice
            while cierre < total and (
                _LISTA.match(lineas[cierre][0]) or lineas[cierre][0].startswith((" ", "\t"))
            ):
                cierre += 1
            anadir(ChunkType.LIST, inicio, lineas[cierre - 1][2], atomico=False)
            indice = cierre
            continue

        # --- Párrafo de prosa ---------------------------------------------------
        cierre = indice
        while cierre < total:
            siguiente = lineas[cierre][0]
            if not siguiente.strip():
                break
            if cierre > indice and (
                _ENCABEZADO.match(siguiente.strip())
                or _VALLA.match(siguiente)
                or _LISTA.match(siguiente)
                or _linea_de_tabla(siguiente)
            ):
                break
            cierre += 1
        anadir(ChunkType.PROSE, inicio, lineas[cierre - 1][2], atomico=False)
        indice = cierre

    return bloques


# ---------------------------------------------------------------------------
# Fase 2: empaquetado por tamaño
# ---------------------------------------------------------------------------


def _unidades_de_corte(texto: str, maximo: int) -> list[str]:  # noqa: ARG001 - firma fijada por quien llama
    """Unidades por las que se puede partir un párrafo: frases y, si no hay, palabras.

    Un PDF mal extraído produce párrafos kilométricos sin un solo punto. Cortarlos por
    frases es imposible, así que se cae a palabras: se sigue respetando la regla de
    «nunca a mitad de palabra», que es la que importa para no romper el significado.
    """
    frases = [pieza for pieza in _FRASE.split(texto) if pieza and pieza.strip()]
    if len(frases) > 1:
        return frases
    palabras = texto.split()
    return palabras if len(palabras) > 1 else ([texto] if texto else [])


def _partir_prosa(bloque: Bloque, maximo: int) -> list[Bloque]:
    """Parte un párrafo demasiado grande por frases (o por palabras), nunca a mitad de palabra.

    El empaquetado se mide en **caracteres** y no sumando el coste de cada unidad: la
    estimación de tokens es `len(texto) / 4`, así que sumar `estimar_tokens` frase a
    frase pierde los espacios de unión y acaba produciendo piezas por encima del tope.
    El límite efectivo es `maximo · 4` caracteres, que es exactamente `maximo` tokens.
    """
    if bloque.tokens <= maximo:
        return [bloque]
    unidades = _unidades_de_corte(bloque.texto, maximo)
    if len(unidades) <= 1:
        return [bloque]

    piezas: list[Bloque] = []
    limite = max(1, maximo) * 4
    actual: list[str] = []
    caracteres = 0
    desplazamiento = 0

    def cerrar() -> None:
        """Emite la pieza acumulada y avanza el offset dentro del bloque original."""
        nonlocal actual, caracteres, desplazamiento
        if not actual:
            return
        texto = " ".join(actual)
        piezas.append(
            Bloque(
                tipo=bloque.tipo,
                texto=texto,
                char_start=bloque.char_start + desplazamiento,
                char_end=min(
                    bloque.char_end, bloque.char_start + desplazamiento + len(texto)
                ),
                encabezados=list(bloque.encabezados),
                atomico=False,
                tokens=estimar_tokens(texto),
                es_encabezado=bloque.es_encabezado,
            )
        )
        desplazamiento += len(texto) + 1
        actual = []
        caracteres = 0

    for unidad in unidades:
        pieza = unidad.strip()
        if not pieza:
            continue
        coste = len(pieza) + (1 if actual else 0)
        if actual and caracteres + coste > limite:
            cerrar()
            coste = len(pieza)
        actual.append(pieza)
        caracteres += coste
    cerrar()
    return piezas


def _cola_para_solape(texto: str, tokens: int) -> str:
    """Devuelve la cola del texto que se arrastra al fragmento siguiente."""
    if tokens <= 0 or not texto:
        return ""
    caracteres = tokens * 4
    if len(texto) <= caracteres:
        return texto
    recorte = texto[-caracteres:]
    espacio = recorte.find(" ")
    return recorte[espacio + 1 :] if espacio != -1 else recorte


def _tipo_del_grupo(grupo: list[Bloque]) -> ChunkType:
    """Tipo del fragmento: manda el bloque atómico; si no, el tipo dominante."""
    for bloque in grupo:
        if bloque.atomico:
            return bloque.tipo
    tipos = {bloque.tipo for bloque in grupo}
    if tipos == {ChunkType.LIST}:
        return ChunkType.LIST
    return ChunkType.PROSE


def _encabezados_del_grupo(grupo: list[Bloque]) -> list[str]:
    """Ruta de encabezados que etiqueta al fragmento (§3.3 `heading_path`).

    Se toma la del primer bloque **de contenido**, no la del primer bloque a secas: un
    fragmento que empieza con la línea «# Capítulo 5» y sigue con el texto de «## LEFT
    JOIN» trata sobre LEFT JOIN, y así es como debe recuperarse y citarse.
    """
    for bloque in grupo:
        if not bloque.es_encabezado:
            return [titulo for titulo in bloque.encabezados if titulo]
    return [titulo for titulo in grupo[-1].encabezados if titulo]


def _texto_del_grupo(grupo: list[Bloque]) -> str:
    """Une los bloques de un fragmento respetando la separación de párrafos."""
    return "\n\n".join(bloque.texto for bloque in grupo).strip()


def fragmentar(
    texto: str,
    *,
    parametros: ParametrosTroceo,
    paginas: list[RangoPagina] | None = None,
) -> list[Fragmento]:
    """Convierte el texto extraído en la lista de fragmentos que se persistirá.

    Devuelve fragmentos ya numerados, con su `heading_path`, su tipo, sus offsets y su
    hash de contenido. Los fragmentos duplicados (mismo hash) se descartan: un pie de
    página repetido no debe inundar la recuperación.
    """
    bloques: list[Bloque] = []
    for bloque in analizar_bloques(texto):
        if bloque.atomico:
            bloques.append(bloque)
        else:
            bloques.extend(_partir_prosa(bloque, parametros.max_tokens))

    grupos: list[list[Bloque]] = []
    actual: list[Bloque] = []
    tokens = 0
    for bloque in bloques:
        cabe = tokens + bloque.tokens <= parametros.max_tokens
        # Un bloque atómico que no cabe abre fragmento propio; nunca se parte.
        if actual and (not cabe or (bloque.atomico and tokens >= parametros.target_tokens)):
            grupos.append(actual)
            actual = []
            tokens = 0
        actual.append(bloque)
        tokens += bloque.tokens
        if tokens >= parametros.target_tokens and not bloque.atomico:
            grupos.append(actual)
            actual = []
            tokens = 0
    if actual:
        grupos.append(actual)

    # Un último grupo demasiado corto se funde con el anterior si el tamaño lo permite.
    if len(grupos) >= 2:
        ultimo = grupos[-1]
        tokens_ultimo = sum(bloque.tokens for bloque in ultimo)
        tokens_previo = sum(bloque.tokens for bloque in grupos[-2])
        if (
            tokens_ultimo < parametros.min_tokens
            and tokens_ultimo + tokens_previo <= parametros.max_tokens
        ):
            grupos[-2] = grupos[-2] + ultimo
            grupos.pop()

    fragmentos: list[Fragmento] = []
    vistos: set[str] = set()
    solape_pendiente = ""
    for grupo in grupos:
        if not grupo:
            continue
        tipo = _tipo_del_grupo(grupo)
        cuerpo = _texto_del_grupo(grupo)
        if not cuerpo:
            solape_pendiente = ""
            continue
        hay_atomico = any(bloque.atomico for bloque in grupo)
        # El solapamiento nunca puede empujar el fragmento por encima de `max_tokens`
        # (§3.3: «objetivo 450, máx. 800»): se recorta la cola a lo que quepa, y si no
        # cabe nada, este fragmento simplemente no lleva solape.
        margen = parametros.max_tokens - estimar_tokens(cuerpo) - 1
        solape = (
            _cola_para_solape(solape_pendiente, min(parametros.tokens_solape, margen))
            if solape_pendiente and not hay_atomico and margen > 0
            else ""
        )
        completo = f"{solape}\n\n{cuerpo}".strip() if solape else cuerpo

        huella = hash_texto(completo)
        if huella in vistos:
            solape_pendiente = ""
            continue
        vistos.add(huella)

        inicio = min(bloque.char_start for bloque in grupo)
        fin = max(bloque.char_end for bloque in grupo)
        fragmento = Fragmento(
            chunk_index=len(fragmentos),
            chunk_type=tipo,
            heading_path=_encabezados_del_grupo(grupo),
            texto=completo,
            token_count=estimar_tokens(completo),
            char_start=inicio,
            char_end=fin,
            content_hash=huella,
        )
        if paginas:
            fragmento.page_start = _pagina_de(paginas, inicio)
            fragmento.page_end = _pagina_de(paginas, max(inicio, fin - 1))
        fragmentos.append(fragmento)

        # La cola que se arrastra al siguiente fragmento es la del **cuerpo** de este,
        # nunca la del solape que arrastró: así el texto no se propaga en cadena.
        solape_pendiente = (
            "" if hay_atomico else _cola_para_solape(cuerpo, parametros.tokens_solape)
        )

    return fragmentos


def _pagina_de(paginas: list[RangoPagina], posicion: int) -> int | None:
    """Página que contiene un offset de carácter del texto extraído."""
    for rango in paginas:
        if rango.char_start <= posicion < rango.char_end:
            return rango.numero
    return paginas[-1].numero if paginas else None


def texto_para_embeber(fragmento: Fragmento) -> str:
    """Antepone la ruta de encabezados al texto antes de calcular el embedding (§3.3)."""
    if not fragmento.heading_path:
        return fragmento.texto
    return " > ".join(fragmento.heading_path) + "\n\n" + fragmento.texto


__all__ = [
    "CHUNK_POR_DEFECTO",
    "Bloque",
    "Fragmento",
    "ParametrosTroceo",
    "analizar_bloques",
    "fragmentar",
    "parametros_de",
    "texto_para_embeber",
]
