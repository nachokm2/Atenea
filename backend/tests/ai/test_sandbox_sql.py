"""Sandbox de SQL: acepta el SELECT correcto, rechaza el DROP y respeta el tiempo."""

from __future__ import annotations

import pytest

from app.modules.ai import sandbox_sql

ESQUEMA = "CREATE TABLE clientes (id INTEGER, nombre VARCHAR, ciudad VARCHAR);"
SEMILLA = [
    "INSERT INTO clientes VALUES (1, 'Ada', 'Santiago');",
    "INSERT INTO clientes VALUES (2, 'Alan', 'Valparaíso');",
    "INSERT INTO clientes VALUES (3, 'Grace', 'Santiago');",
]
CUERPO = {"schema_sql": ESQUEMA, "seed_data": SEMILLA, "ordered": False}
CLAVE = {"reference_sql": "SELECT nombre FROM clientes WHERE ciudad = 'Santiago'"}


def test_acepta_select_correcto() -> None:
    """Una consulta equivalente a la de referencia se da por correcta."""
    resultado = sandbox_sql.evaluar_ejercicio(
        None,
        body=CUERPO,
        answer_key=CLAVE,
        consulta_usuario="SELECT nombre FROM clientes WHERE ciudad = 'Santiago'",
    )
    assert resultado.is_correct is True
    assert resultado.partial_score == 100.0
    assert resultado.row_count == 2
    assert resultado.error_code is None


def test_ignora_el_orden_salvo_que_se_pida() -> None:
    """El mismo conjunto de filas en otro orden sigue siendo correcto."""
    resultado = sandbox_sql.evaluar_ejercicio(
        None,
        body=CUERPO,
        answer_key=CLAVE,
        consulta_usuario="SELECT nombre FROM clientes WHERE ciudad = 'Santiago' ORDER BY nombre DESC",
    )
    assert resultado.is_correct is True


def test_exige_el_orden_cuando_el_enunciado_lo_pide() -> None:
    """Con `ordered = true`, el orden forma parte de la respuesta correcta."""
    cuerpo = {**CUERPO, "ordered": True}
    clave = {"reference_sql": "SELECT nombre FROM clientes WHERE ciudad='Santiago' ORDER BY nombre"}
    correcta = sandbox_sql.evaluar_ejercicio(
        None,
        body=cuerpo,
        answer_key=clave,
        consulta_usuario="SELECT nombre FROM clientes WHERE ciudad='Santiago' ORDER BY nombre ASC",
    )
    invertida = sandbox_sql.evaluar_ejercicio(
        None,
        body=cuerpo,
        answer_key=clave,
        consulta_usuario="SELECT nombre FROM clientes WHERE ciudad='Santiago' ORDER BY nombre DESC",
    )
    assert correcta.is_correct is True
    assert invertida.is_correct is False


def test_rechaza_drop() -> None:
    """El sandbox es de solo lectura: un DROP no llega ni a ejecutarse."""
    resultado = sandbox_sql.evaluar_ejercicio(
        None, body=CUERPO, answer_key=CLAVE, consulta_usuario="DROP TABLE clientes"
    )
    assert resultado.is_correct is False
    assert resultado.error_code == "not_allowed"
    with pytest.raises(sandbox_sql.SQLNoPermitido):
        sandbox_sql.validar_sql("DROP TABLE clientes")


@pytest.mark.parametrize(
    "consulta",
    [
        "INSERT INTO clientes VALUES (9, 'X', 'Y')",
        "UPDATE clientes SET ciudad = 'Santiago'",
        "DELETE FROM clientes",
        "CREATE TABLE otra (id INTEGER)",
        "SELECT 1; SELECT 2",
        "SELECT * FROM read_csv('/etc/passwd')",
    ],
)
def test_rechaza_todo_lo_que_no_sea_lectura(consulta: str) -> None:
    """DDL, DML, varias sentencias y acceso a ficheros quedan fuera."""
    with pytest.raises(sandbox_sql.SQLNoPermitido):
        sandbox_sql.validar_sql(consulta)


def test_respeta_el_limite_de_tiempo() -> None:
    """Una consulta desbocada se interrumpe y se traduce a un error de tiempo."""
    limites = sandbox_sql.ConfigSandbox(timeout_ms=300)
    with pytest.raises(sandbox_sql.TiempoAgotado):
        sandbox_sql.ejecutar(
            "SELECT count(*) FROM range(100000000000) t(x) WHERE x % 7 = 3",
            schema_sql=ESQUEMA,
            seed_data=SEMILLA,
            limites=limites,
        )


def test_el_limite_de_tiempo_tambien_aplica_al_corregir(monkeypatch: pytest.MonkeyPatch) -> None:
    """`evaluar_ejercicio` nunca lanza: traduce el corte a `error_code = timeout`."""
    monkeypatch.setattr(
        sandbox_sql, "config_sandbox", lambda _cfg: sandbox_sql.ConfigSandbox(timeout_ms=300)
    )
    resultado = sandbox_sql.evaluar_ejercicio(
        None,
        body=CUERPO,
        answer_key=CLAVE,
        consulta_usuario="SELECT count(*) FROM range(100000000000) t(x) WHERE x % 7 = 3",
    )
    assert resultado.is_correct is False
    assert resultado.error_code == "timeout"


def test_una_consulta_equivocada_no_puntua() -> None:
    """Otro conjunto de filas es simplemente incorrecto, sin error técnico."""
    resultado = sandbox_sql.evaluar_ejercicio(
        None,
        body=CUERPO,
        answer_key=CLAVE,
        consulta_usuario="SELECT nombre FROM clientes WHERE ciudad = 'Valparaíso'",
    )
    assert resultado.is_correct is False
    assert resultado.partial_score == 0.0
    assert resultado.error_code is None


def test_lee_los_limites_de_game_configs(cfg) -> None:  # noqa: ANN001 - fixture tipada en conftest
    """Los límites salen de `ai.sql_sandbox`, nunca de un literal en el código."""
    limites = sandbox_sql.config_sandbox(cfg)
    assert limites.engine == "duckdb"
    assert limites.timeout_ms == 2000
    assert limites.max_rows == 10000
    assert limites.max_tables == 5
