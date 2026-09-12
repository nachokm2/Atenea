"""Sandbox de SQL: DuckDB embebido sobre datasets sintéticos, determinista y de coste 0.

Corrige los ejercicios `sql_exercise` sin gastar un solo token: se valida la consulta
con `sqlglot` **antes** de ejecutarla, se ejecuta en una base en memoria creada al
vuelo con el `schema_sql` y el `seed_data` de la pregunta, y se compara con la consulta
de referencia.

Garantías (parámetros en `ai.sql_sandbox`, CONTRACT.md §5.8):

- **Solo lectura**: únicamente `SELECT` y `WITH`; cualquier DDL o DML (`DROP`, `INSERT`,
  `UPDATE`, `ATTACH`, `COPY`, `PRAGMA`, `INSTALL`…) se rechaza en la validación previa.
- **Una sola sentencia**: nada de `;` encadenados.
- **Sin acceso externo**: se desactiva el acceso al sistema de archivos y a la red.
- **Límite de tiempo** (`timeout_ms`) y **de filas** (`max_rows`), más el límite de
  memoria del motor.
- **Comparación independiente del orden**, salvo que el enunciado pida un orden
  concreto (`body.ordered = true`).
"""

from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

import duckdb
import sqlglot
from sqlglot import exp

from app.modules.gamification.servicio_config import ServicioConfig

# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------


class ErrorSandbox(Exception):
    """Fallo al evaluar una consulta en el sandbox (nunca llega crudo al usuario)."""


class SQLNoPermitido(ErrorSandbox):
    """La consulta no es de solo lectura o usa construcciones prohibidas."""


class TiempoAgotado(ErrorSandbox):
    """La consulta superó el límite de tiempo del sandbox."""


class LimiteFilas(ErrorSandbox):
    """La consulta devolvió más filas de las permitidas."""


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigSandbox:
    """Límites del sandbox tomados de `ai.sql_sandbox`."""

    engine: str = "duckdb"
    timeout_ms: int = 2_000
    memory_limit_mb: int = 256
    max_rows: int = 10_000
    max_tables: int = 5
    max_rows_per_table: int = 200


def config_sandbox(cfg: ServicioConfig | None) -> ConfigSandbox:
    """Lee `ai.sql_sandbox` de `game_configs`; sin configuración usa los mínimos seguros."""
    if cfg is None:
        return ConfigSandbox()
    crudo = cfg.obtener_json("ai.sql_sandbox", {}) or {}
    base = ConfigSandbox()
    return ConfigSandbox(
        engine=str(crudo.get("engine", base.engine)),
        timeout_ms=int(crudo.get("timeout_ms", base.timeout_ms)),
        memory_limit_mb=int(crudo.get("memory_limit_mb", base.memory_limit_mb)),
        max_rows=int(crudo.get("max_rows", base.max_rows)),
        max_tables=int(crudo.get("max_tables", base.max_tables)),
        max_rows_per_table=int(crudo.get("max_rows_per_table", base.max_rows_per_table)),
    )


# ---------------------------------------------------------------------------
# Validación previa con sqlglot
# ---------------------------------------------------------------------------

#: Nodos que jamás pueden aparecer en la consulta de un estudiante.
_PROHIBIDOS: Final[tuple[type[exp.Expression], ...]] = (
    exp.Create,
    exp.Drop,
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Alter,
    exp.Command,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Use,
    exp.Set,
    exp.Merge,
)

#: Funciones de DuckDB que abren el sistema de archivos o la red.
_FUNCIONES_PROHIBIDAS: Final[frozenset[str]] = frozenset(
    {
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "read_json",
        "read_json_auto",
        "read_text",
        "read_blob",
        "glob",
        "copy",
        "install",
        "load",
        "attach",
        "httpfs",
        "parquet_scan",
        "csv_scan",
        "sniff_csv",
        "getenv",
    }
)


def validar_sql(sql: str) -> exp.Expression:
    """Valida que la consulta sea **una** sentencia de solo lectura.

    Devuelve el árbol ya parseado (evita parsear dos veces) o lanza `SQLNoPermitido`.
    """
    texto = (sql or "").strip()
    if not texto:
        raise SQLNoPermitido("La consulta está vacía.")
    try:
        sentencias = [s for s in sqlglot.parse(texto, dialect="duckdb") if s is not None]
    except Exception as error:  # sqlglot.ParseError y derivados
        raise SQLNoPermitido(f"No pudimos entender la consulta: {error}") from error
    if len(sentencias) != 1:
        raise SQLNoPermitido("Envía una sola sentencia SQL, sin punto y coma encadenado.")

    arbol = sentencias[0]
    if not isinstance(arbol, (exp.Select, exp.Union, exp.Subquery, exp.With)):
        raise SQLNoPermitido("Solo se admiten consultas de lectura (SELECT).")
    for prohibido in _PROHIBIDOS:
        if list(arbol.find_all(prohibido)):
            raise SQLNoPermitido("Esa instrucción no está permitida: el sandbox es de solo lectura.")
    for anonima in arbol.find_all(exp.Anonymous):
        nombre = str(anonima.this or "").lower()
        if nombre in _FUNCIONES_PROHIBIDAS:
            raise SQLNoPermitido(f"La función {nombre} no está permitida en el sandbox.")
    for funcion in arbol.find_all(exp.Func):
        nombre = getattr(funcion, "sql_name", lambda: "")()
        if str(nombre).lower() in _FUNCIONES_PROHIBIDAS:
            raise SQLNoPermitido(f"La función {nombre} no está permitida en el sandbox.")
    return arbol


def validar_preparacion(sentencias: list[str], limites: ConfigSandbox) -> None:
    """Valida el `schema_sql` y el `seed_data` de la pregunta (solo CREATE e INSERT)."""
    tablas = 0
    inserciones = 0
    for crudo in sentencias:
        for sentencia in sqlglot.parse(crudo or "", dialect="duckdb"):
            if sentencia is None:
                continue
            if isinstance(sentencia, exp.Create):
                tablas += 1
            elif isinstance(sentencia, exp.Insert):
                inserciones += 1
            else:
                raise SQLNoPermitido(
                    "La preparación del ejercicio solo admite CREATE TABLE e INSERT."
                )
    if tablas > limites.max_tables:
        raise SQLNoPermitido(f"El ejercicio define más de {limites.max_tables} tablas.")
    if inserciones > limites.max_tables * limites.max_rows_per_table:
        raise SQLNoPermitido("El ejercicio inserta demasiadas filas.")


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ResultadoConsulta:
    """Resultado de ejecutar una consulta en el sandbox."""

    columns: list[str] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    elapsed_ms: int = 0
    truncated: bool = False


def _normalizar_valor(valor: Any) -> Any:
    """Normaliza el valor para comparar sin depender del tipo exacto del motor."""
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (dt.date, dt.datetime)):
        return valor.isoformat()
    if isinstance(valor, float):
        return round(valor, 6)
    if isinstance(valor, bytes):  # pragma: no cover - poco frecuente
        return valor.decode("utf-8", "replace")
    return valor


def _normalizar_filas(filas: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    """Aplica `_normalizar_valor` a toda la matriz de resultados."""
    return [tuple(_normalizar_valor(v) for v in fila) for fila in filas]


def _preparar_conexion(
    schema_sql: str, seed_data: list[str], limites: ConfigSandbox
) -> duckdb.DuckDBPyConnection:
    """Crea la base en memoria, la puebla y la deja sin acceso al exterior."""
    conexion = duckdb.connect(database=":memory:")
    for ajuste in (
        f"SET memory_limit='{max(16, limites.memory_limit_mb)}MB'",
        "SET threads=1",
        "SET enable_external_access=false",
    ):
        try:
            conexion.execute(ajuste)
        except Exception:  # pragma: no cover - ajuste no soportado por la versión
            continue
    if schema_sql:
        conexion.execute(schema_sql)
    for sentencia in seed_data:
        if sentencia and sentencia.strip():
            conexion.execute(sentencia)
    return conexion


def ejecutar_consulta(
    conexion: duckdb.DuckDBPyConnection, sql: str, limites: ConfigSandbox
) -> ResultadoConsulta:
    """Ejecuta una consulta ya validada con límite de tiempo y de filas.

    El límite de tiempo se aplica interrumpiendo la conexión desde otro hilo: DuckDB no
    ofrece un tope por consulta, pero sí `interrupt()`.
    """
    resultado = ResultadoConsulta()
    error: list[BaseException] = []
    interrumpida = threading.Event()

    def _correr() -> None:
        try:
            cursor = conexion.execute(sql)
            filas = cursor.fetchmany(limites.max_rows + 1)
            resultado.columns = [descripcion[0] for descripcion in (cursor.description or [])]
            if len(filas) > limites.max_rows:
                resultado.truncated = True
                filas = filas[: limites.max_rows]
            resultado.rows = _normalizar_filas([tuple(fila) for fila in filas])
        except BaseException as fallo:  # noqa: BLE001 - se reenvía al hilo llamante
            error.append(fallo)

    inicio = dt.datetime.now(dt.UTC)
    hilo = threading.Thread(target=_correr, daemon=True)
    hilo.start()
    hilo.join(timeout=max(0.05, limites.timeout_ms / 1000))
    if hilo.is_alive():
        interrumpida.set()
        try:
            conexion.interrupt()
        except Exception:  # pragma: no cover - la conexión puede estar ya cerrada
            pass
        hilo.join(timeout=2.0)
    resultado.elapsed_ms = int((dt.datetime.now(dt.UTC) - inicio).total_seconds() * 1000)

    if interrumpida.is_set():
        raise TiempoAgotado(
            f"La consulta superó el límite de {limites.timeout_ms} ms."
        )
    if error:
        fallo = error[0]
        if isinstance(fallo, duckdb.InterruptException):  # pragma: no cover
            raise TiempoAgotado(f"La consulta superó el límite de {limites.timeout_ms} ms.")
        raise ErrorSandbox(str(fallo))
    if resultado.truncated:
        raise LimiteFilas(f"La consulta devolvió más de {limites.max_rows} filas.")
    return resultado


def ejecutar(
    sql: str,
    *,
    schema_sql: str = "",
    seed_data: list[str] | None = None,
    limites: ConfigSandbox | None = None,
) -> ResultadoConsulta:
    """Valida y ejecuta una consulta de lectura sobre un dataset sintético."""
    reglas = limites or ConfigSandbox()
    validar_sql(sql)
    conexion = _preparar_conexion(schema_sql, list(seed_data or []), reglas)
    try:
        return ejecutar_consulta(conexion, sql, reglas)
    finally:
        conexion.close()


# ---------------------------------------------------------------------------
# Comparación y evaluación del ejercicio
# ---------------------------------------------------------------------------


def comparar_resultados(
    obtenido: ResultadoConsulta, esperado: ResultadoConsulta, *, ordenado: bool = False
) -> tuple[bool, str]:
    """Compara dos resultados; ignora el orden salvo que el enunciado lo exija."""
    if len(obtenido.columns) != len(esperado.columns):
        return False, "El número de columnas no coincide con lo que pide el enunciado."
    if ordenado:
        igual = obtenido.rows == esperado.rows
        motivo = "" if igual else "Las filas no están en el orden pedido o no coinciden."
        return igual, motivo
    igual = sorted(obtenido.rows, key=repr) == sorted(esperado.rows, key=repr)
    motivo = "" if igual else "El conjunto de filas devuelto no coincide con el esperado."
    return igual, motivo


@dataclass(slots=True)
class ResultadoSandbox:
    """Veredicto determinista de un ejercicio `sql_exercise`."""

    is_correct: bool
    partial_score: float
    message: str
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    elapsed_ms: int = 0
    error_code: str | None = None

    def como_dict(self) -> dict[str, Any]:
        """Representación serializable para `question_attempts.judge_payload`."""
        return {
            "is_correct": self.is_correct,
            "partial_score": self.partial_score,
            "message": self.message,
            "columns": self.columns,
            "row_count": self.row_count,
            "elapsed_ms": self.elapsed_ms,
            "error_code": self.error_code,
        }


def evaluar_ejercicio(
    cfg: ServicioConfig | None,
    *,
    body: dict[str, Any],
    answer_key: dict[str, Any],
    consulta_usuario: str,
    muestra_filas: int = 20,
) -> ResultadoSandbox:
    """Corrige un ejercicio de SQL: valida, ejecuta las dos consultas y compara.

    Nunca lanza: cualquier fallo se traduce a un veredicto incorrecto con un mensaje en
    español apto para mostrar al estudiante.
    """
    limites = config_sandbox(cfg)
    schema_sql = str(body.get("schema_sql") or "")
    seeds = [str(s) for s in (body.get("seed_data") or [])]
    ordenado = bool(body.get("ordered", False))
    referencia = str(answer_key.get("reference_sql") or "")

    if not referencia:
        return ResultadoSandbox(
            is_correct=False,
            partial_score=0.0,
            message="Este ejercicio no tiene consulta de referencia; lo revisaremos.",
            error_code="missing_reference",
        )
    try:
        validar_preparacion([schema_sql, *seeds], limites)
        validar_sql(consulta_usuario)
    except SQLNoPermitido as error:
        return ResultadoSandbox(
            is_correct=False,
            partial_score=0.0,
            message=str(error),
            error_code="not_allowed",
        )

    conexion = _preparar_conexion(schema_sql, seeds, limites)
    try:
        esperado = ejecutar_consulta(conexion, referencia, limites)
    except ErrorSandbox:  # pragma: no cover - referencia rota en el catálogo
        conexion.close()
        return ResultadoSandbox(
            is_correct=False,
            partial_score=0.0,
            message="Este ejercicio tiene un problema; lo revisaremos.",
            error_code="broken_reference",
        )
    try:
        obtenido = ejecutar_consulta(conexion, consulta_usuario, limites)
    except TiempoAgotado as error:
        return ResultadoSandbox(
            is_correct=False, partial_score=0.0, message=str(error), error_code="timeout"
        )
    except LimiteFilas as error:
        return ResultadoSandbox(
            is_correct=False, partial_score=0.0, message=str(error), error_code="too_many_rows"
        )
    except ErrorSandbox as error:
        return ResultadoSandbox(
            is_correct=False,
            partial_score=0.0,
            message=f"Tu consulta no se pudo ejecutar: {error}",
            error_code="execution_error",
        )
    finally:
        conexion.close()

    correcto, motivo = comparar_resultados(obtenido, esperado, ordenado=ordenado)
    parcial = 100.0 if correcto else 0.0
    if not correcto and not ordenado:
        # Mismo conjunto de valores en otro orden de columnas: crédito parcial.
        valores_obtenidos = sorted((sorted(map(repr, fila)) for fila in obtenido.rows), key=repr)
        valores_esperados = sorted((sorted(map(repr, fila)) for fila in esperado.rows), key=repr)
        if valores_obtenidos == valores_esperados and valores_esperados:
            parcial = 50.0
            motivo = "Los datos son los correctos, pero el orden de las columnas no coincide."
    return ResultadoSandbox(
        is_correct=correcto,
        partial_score=parcial,
        message="¡Consulta correcta!" if correcto else motivo,
        columns=obtenido.columns,
        rows=[list(fila) for fila in obtenido.rows[:muestra_filas]],
        row_count=len(obtenido.rows),
        elapsed_ms=obtenido.elapsed_ms,
    )


__all__ = [
    "ConfigSandbox",
    "ErrorSandbox",
    "LimiteFilas",
    "ResultadoConsulta",
    "ResultadoSandbox",
    "SQLNoPermitido",
    "TiempoAgotado",
    "comparar_resultados",
    "config_sandbox",
    "ejecutar",
    "ejecutar_consulta",
    "evaluar_ejercicio",
    "validar_preparacion",
    "validar_sql",
]
