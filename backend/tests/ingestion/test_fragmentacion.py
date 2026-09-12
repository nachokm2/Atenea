"""Troceado por estructura y tamaño (§3.3 `document_chunks`, §5.8 `ingestion.chunk`).

La regla que estas pruebas defienden es pedagógica antes que técnica: **una consulta SQL
partida por la mitad genera lecciones y preguntas erróneas, y una tabla sin su cabecera
deja de significar nada**. Por eso el bloque de código y la tabla son atómicos aunque
superen `max_tokens`.
"""

from __future__ import annotations

from app.models.enums import ChunkType
from app.modules.ingestion import fragmentacion
from app.modules.ingestion.extraccion import RangoPagina

#: Parámetros literales de `ingestion.chunk` (§5.8).
PARAMETROS = fragmentacion.parametros_de(
    {"target_tokens": 450, "max_tokens": 800, "min_tokens": 80, "overlap_pct": 0.12}
)

CODIGO_SQL = """```sql
SELECT c.nombre,
       COUNT(p.id) AS pedidos
  FROM clientes c
  LEFT JOIN pedidos p ON p.cliente_id = c.id
 WHERE c.activo = true
 GROUP BY c.nombre
 ORDER BY pedidos DESC;
```"""

TABLA = """| Tipo de JOIN | Filas de la izquierda | Filas de la derecha |
| --- | --- | --- |
| INNER JOIN | solo coincidencias | solo coincidencias |
| LEFT JOIN | todas | solo coincidencias |
| RIGHT JOIN | solo coincidencias | todas |
| FULL JOIN | todas | todas |"""


def _relleno(palabras: int, semilla: str) -> str:
    """Párrafo de prosa con el número de palabras pedido."""
    return " ".join(f"{semilla}{indice % 29}" for indice in range(palabras))


# ---------------------------------------------------------------------------
# Análisis estructural
# ---------------------------------------------------------------------------


def test_analiza_encabezados_codigo_tabla_y_listas() -> None:
    """Cada construcción del documento se reconoce con su tipo y su pila de encabezados."""
    texto = (
        "# Capitulo 5. JOINs\n\n"
        "## LEFT JOIN\n\n"
        "Un LEFT JOIN conserva todas las filas de la izquierda.\n\n"
        f"{CODIGO_SQL}\n\n"
        f"{TABLA}\n\n"
        "- primer punto\n- segundo punto\n"
    )
    bloques = fragmentacion.analizar_bloques(texto)
    tipos = [bloque.tipo for bloque in bloques]
    assert ChunkType.CODE in tipos
    assert ChunkType.TABLE in tipos
    assert ChunkType.LIST in tipos

    codigo = next(bloque for bloque in bloques if bloque.tipo == ChunkType.CODE)
    assert codigo.atomico is True
    assert codigo.encabezados == ["Capitulo 5. JOINs", "LEFT JOIN"]


def test_sql_sin_vallas_tambien_es_bloque_atomico() -> None:
    """Una racha de líneas SQL sin vallas se protege igual: no se parte."""
    texto = (
        "Ejemplo de consulta:\n\n"
        "SELECT nombre, total\n"
        "  FROM ventas\n"
        " WHERE anio = 2026\n"
        " ORDER BY total DESC;\n"
    )
    bloques = fragmentacion.analizar_bloques(texto)
    codigo = [bloque for bloque in bloques if bloque.tipo == ChunkType.CODE]
    assert len(codigo) == 1
    assert codigo[0].atomico is True
    assert "ORDER BY total DESC;" in codigo[0].texto


# ---------------------------------------------------------------------------
# LAS pruebas exigidas: código y tablas íntegros
# ---------------------------------------------------------------------------


def test_el_bloque_de_codigo_llega_integro_a_un_unico_fragmento() -> None:
    """El bloque de código aparece **completo** y en **un solo** fragmento."""
    texto = (
        "# Consultas\n\n"
        + _relleno(600, "alfa")
        + "\n\n"
        + CODIGO_SQL
        + "\n\n"
        + _relleno(600, "beta")
    )
    fragmentos = fragmentacion.fragmentar(texto, parametros=PARAMETROS)

    con_codigo = [f for f in fragmentos if "SELECT c.nombre," in f.texto]
    assert len(con_codigo) == 1, "el código debe vivir en un único fragmento"
    fragmento = con_codigo[0]
    for linea in CODIGO_SQL.splitlines():
        assert linea in fragmento.texto
    assert fragmento.chunk_type == ChunkType.CODE
    # Y ningún otro fragmento se queda con un trozo suelto de la consulta.
    assert sum(1 for f in fragmentos if "LEFT JOIN pedidos p" in f.texto) == 1


def test_la_tabla_llega_integra_con_su_cabecera() -> None:
    """La tabla conserva cabecera, separador y todas sus filas en el mismo fragmento."""
    texto = (
        "# Comparativa\n\n" + _relleno(600, "gamma") + "\n\n" + TABLA + "\n\n" + _relleno(600, "delta")
    )
    fragmentos = fragmentacion.fragmentar(texto, parametros=PARAMETROS)

    con_tabla = [f for f in fragmentos if "| Tipo de JOIN |" in f.texto]
    assert len(con_tabla) == 1
    fragmento = con_tabla[0]
    for linea in TABLA.splitlines():
        assert linea in fragmento.texto
    assert fragmento.chunk_type == ChunkType.TABLE


def test_un_bloque_atomico_mas_grande_que_el_maximo_no_se_parte() -> None:
    """Aunque supere `max_tokens`, el bloque atómico viaja entero: partirlo lo invalida."""
    enorme = "```python\n" + "\n".join(f"linea_{i} = {i} * 2  # comentario" for i in range(400)) + "\n```"
    fragmentos = fragmentacion.fragmentar(enorme, parametros=PARAMETROS)
    assert len(fragmentos) == 1
    assert fragmentos[0].chunk_type == ChunkType.CODE
    assert fragmentos[0].token_count > PARAMETROS.max_tokens
    assert "linea_0 = 0" in fragmentos[0].texto
    assert "linea_399 = 399" in fragmentos[0].texto


# ---------------------------------------------------------------------------
# Tamaño, solapamiento y trazabilidad
# ---------------------------------------------------------------------------


def test_la_prosa_respeta_el_maximo_de_tokens() -> None:
    """Ningún fragmento de prosa pasa de `max_tokens`."""
    fragmentos = fragmentacion.fragmentar(_relleno(4000, "epsilon"), parametros=PARAMETROS)
    assert len(fragmentos) > 1
    assert all(f.token_count <= PARAMETROS.max_tokens for f in fragmentos)
    assert all(f.chunk_type == ChunkType.PROSE for f in fragmentos)


def test_hay_solapamiento_entre_fragmentos_de_prosa() -> None:
    """La cola del fragmento anterior se arrastra al siguiente (`overlap_pct`)."""
    parrafos = "\n\n".join(_relleno(200, f"tema{indice}") for indice in range(12))
    fragmentos = fragmentacion.fragmentar(parrafos, parametros=PARAMETROS)
    assert len(fragmentos) >= 2
    cola_anterior = fragmentos[0].texto.split()[-5:]
    assert " ".join(cola_anterior) in fragmentos[1].texto


def test_no_se_solapa_hacia_un_fragmento_con_bloque_atomico() -> None:
    """Un fragmento que contiene código no repite la cola del fragmento anterior.

    El código puede compartir fragmento con la prosa que lo introduce —eso da contexto—,
    pero **no** se le antepone el solapamiento: duplicar texto alrededor de un bloque
    atómico ensucia la recuperación sin aportar nada.
    """
    texto = _relleno(600, "zeta") + "\n\n" + CODIGO_SQL
    fragmentos = fragmentacion.fragmentar(texto, parametros=PARAMETROS)
    codigo = next(f for f in fragmentos if f.chunk_type == ChunkType.CODE)
    assert "```sql" in codigo.texto
    assert "ORDER BY pedidos DESC;" in codigo.texto

    anterior = fragmentos[fragmentos.index(codigo) - 1]
    cola_anterior = " ".join(anterior.texto.split()[-6:])
    assert not codigo.texto.startswith(cola_anterior)


def test_cada_fragmento_lleva_su_ruta_de_encabezados_y_su_hash() -> None:
    """`heading_path` viaja con el fragmento y el hash deduplica contenido repetido."""
    texto = (
        "# Capitulo 5. JOINs\n\n## LEFT JOIN\n\n"
        + _relleno(500, "eta")
        + "\n\n## RIGHT JOIN\n\n"
        + _relleno(500, "theta")
    )
    fragmentos = fragmentacion.fragmentar(texto, parametros=PARAMETROS)
    rutas = {tuple(f.heading_path) for f in fragmentos}
    assert ("Capitulo 5. JOINs", "LEFT JOIN") in rutas
    assert ("Capitulo 5. JOINs", "RIGHT JOIN") in rutas
    assert len({f.content_hash for f in fragmentos}) == len(fragmentos)
    assert [f.chunk_index for f in fragmentos] == list(range(len(fragmentos)))


def test_asigna_paginas_a_partir_de_los_rangos_del_pdf() -> None:
    """La trazabilidad de página sobrevive al troceado (hoja «Fuente» de la app)."""
    pagina_uno = _relleno(300, "iota")
    pagina_dos = _relleno(300, "kappa")
    texto = pagina_uno + "\n\n" + pagina_dos
    rangos = [
        RangoPagina(numero=1, char_start=0, char_end=len(pagina_uno) + 2),
        RangoPagina(numero=2, char_start=len(pagina_uno) + 2, char_end=len(texto)),
    ]
    fragmentos = fragmentacion.fragmentar(texto, parametros=PARAMETROS, paginas=rangos)
    assert fragmentos[0].page_start == 1
    assert {f.page_start for f in fragmentos} <= {1, 2}


def test_texto_para_embeber_antepone_los_encabezados() -> None:
    """§3.3: la ruta de encabezados se antepone al texto antes de calcular el embedding."""
    fragmento = fragmentacion.Fragmento(
        chunk_index=0,
        chunk_type=ChunkType.PROSE,
        heading_path=["Capitulo 5. JOINs", "LEFT JOIN"],
        texto="Conserva todas las filas de la izquierda.",
        token_count=10,
        char_start=0,
        char_end=40,
        content_hash="x" * 64,
    )
    assert fragmentacion.texto_para_embeber(fragmento).startswith(
        "Capitulo 5. JOINs > LEFT JOIN\n\n"
    )


def test_parametros_de_usa_el_respaldo_documentado() -> None:
    """Sin configuración sembrada se usan los valores del contrato, no números mágicos."""
    parametros = fragmentacion.parametros_de(None)
    assert parametros.target_tokens == 450
    assert parametros.max_tokens == 800
    assert parametros.min_tokens == 80
    assert parametros.tokens_solape == 54  # round(450 · 0,12)
