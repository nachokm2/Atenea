"""Ruta del Reino de SQL: la primera impresión del producto, escrita a mano.

Contrato §9: no existe fuente previa para este contenido, **se escribe nuevo** y con
calidad pedagógica real. Es la ruta que un usuario recién registrado puede empezar sin
subir un solo archivo y sin que intervenga la IA: por eso todo su contenido está aquí,
completo y curado, y no se genera en ejecución.

Forma de la ruta (jerarquía normativa del contrato §1.1)::

    Conocimiento `sql`  =  Castillo de las Consultas
      └── Ruta «El Castillo de las Consultas»
            ├── Módulo 1 · Salón de las Puertas      → SELECT/FROM, WHERE/ORDER BY
            ├── Módulo 2 · Torre de los Escribas     → agregación, GROUP BY/HAVING
            └── Módulo 3 · Puente de las Uniones     → INNER JOIN, LEFT JOIN y NULL

Cifras: 3 módulos · 6 temas · 6 lecciones · **24 preguntas** · 3 evaluaciones. Cada
lección lleva explicación, ejemplo ejecutable, caso comentado, una pregunta intercalada
y un resumen. Los siete tipos de pregunta del MVP (`content.mvp_question_types`) están
representados, y cada `answer_key` cumple la forma que valida
`app.modules.ai.esquemas_salida.SalidaPregunta.clave_completa()` y que corrigen los
correctores deterministas de `app.modules.content.correccion`.

Los ejercicios `sql_exercise` comparten un único esquema de dos tablas (`reinos` y
`caballeros`) para que el estudiante no tenga que reaprender el mundo en cada ejercicio.
Ese esquema incluye a propósito un caballero sin reino y un reino sin caballeros: son
los dos casos que hacen visible la diferencia entre `JOIN` y `LEFT JOIN` en el módulo 3.

`user_id` es nulo y `origin = SEED`: es una **Ruta del Reino** compartida por todos los
usuarios. El progreso de cada persona vive en `user_*_progress`, nunca aquí (§5.9 D17).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.enums import (
    ContentStatus,
    CoverageLevel,
    CoveragePolicy,
    DeclaredLevel,
    DifficultyLevel,
    LessonBlockType,
    PathOrigin,
    PathSourceMode,
    PathStatus,
    ProvenanceOrigin,
    QuestionType,
)

__all__ = [
    "ESQUEMA_SQL",
    "RUTA",
    "SEMILLA_SQL",
    "BloqueSemilla",
    "LeccionSemilla",
    "ModuloSemilla",
    "PreguntaSemilla",
    "RutaSemilla",
    "TemaSemilla",
    "banco_de_evaluacion",
    "preguntas_de_modulo",
    "todas_las_preguntas",
]


# ---------------------------------------------------------------------------
# Mundo compartido por los ejercicios de SQL
# ---------------------------------------------------------------------------

#: Esquema del sandbox: dos tablas, suficientes para enseñar filtrado, agregación y uniones.
ESQUEMA_SQL = (
    "CREATE TABLE reinos ("
    "id INTEGER, nombre VARCHAR, region VARCHAR, fundado INTEGER); "
    "CREATE TABLE caballeros ("
    "id INTEGER, nombre VARCHAR, reino_id INTEGER, rango VARCHAR, victorias INTEGER)"
)

#: Datos de ejemplo. Selvana no tiene caballeros y Hilde no tiene reino: los dos casos
#: que separan `JOIN` de `LEFT JOIN` y que el módulo 3 explota deliberadamente.
SEMILLA_SQL = [
    "INSERT INTO reinos VALUES "
    "(1, 'Valdoria', 'Norte', 1187), "
    "(2, 'Marlen', 'Costa', 1203), "
    "(3, 'Ostgard', 'Norte', 1150), "
    "(4, 'Selvana', 'Bosque', 1290)",
    "INSERT INTO caballeros VALUES "
    "(1, 'Aldric', 1, 'capitan', 12), "
    "(2, 'Brenna', 1, 'escudero', 3), "
    "(3, 'Corvin', 2, 'capitan', 9), "
    "(4, 'Dalia', 2, 'caballero', 7), "
    "(5, 'Edric', 3, 'caballero', 15), "
    "(6, 'Fiora', 3, 'escudero', 2), "
    "(7, 'Garen', 1, 'caballero', 6), "
    "(8, 'Hilde', NULL, 'errante', 4)",
]


def cuerpo_sql(*, ordenado: bool = False) -> dict[str, Any]:
    """`body` de un ejercicio `sql_exercise` sobre el mundo compartido."""
    return {"schema_sql": ESQUEMA_SQL, "seed_data": list(SEMILLA_SQL), "ordered": ordenado}


# ---------------------------------------------------------------------------
# Estructuras de la semilla
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PreguntaSemilla:
    """Una fila de `questions` con su clave de corrección y su explicación."""

    code: str
    """Código estable (`m1-t1-q1`); genera el `id` con `uuid5`."""

    question_type: QuestionType
    difficulty: DifficultyLevel
    stem: str
    body: dict[str, Any]
    answer_key: dict[str, Any]
    """**Nunca** se serializa al cliente: la corrección ocurre siempre en el servidor."""

    explanation: str
    learning_objective: str
    estimated_seconds: int = 45
    inline: bool = False
    """`True` si además se intercala en la lección del tema."""


@dataclass(frozen=True, slots=True)
class BloqueSemilla:
    """Una fila de `lesson_blocks`."""

    position: int
    block_type: LessonBlockType
    body: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    question_code: str | None = None
    """Pregunta intercalada; `ejecutar.py` resuelve su `id` en `payload.question_id`."""


@dataclass(frozen=True, slots=True)
class LeccionSemilla:
    """Una fila de `lessons` con sus bloques ordenados."""

    code: str
    position: int
    title: str
    summary: str
    estimated_seconds: int
    bloques: tuple[BloqueSemilla, ...]
    coverage_report: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class TemaSemilla:
    """Una fila de `topics` con su lección y su pool de preguntas."""

    code: str
    position: int
    title: str
    learning_objectives: tuple[str, ...]
    difficulty: DifficultyLevel
    estimated_minutes: int
    lecciones: tuple[LeccionSemilla, ...]
    preguntas: tuple[PreguntaSemilla, ...]

    @property
    def suggested_question_types(self) -> list[str]:
        """Tipos presentes en el pool, en el orden en que aparecen."""
        vistos: list[str] = []
        for pregunta in self.preguntas:
            if pregunta.question_type.value not in vistos:
                vistos.append(pregunta.question_type.value)
        return vistos


@dataclass(frozen=True, slots=True)
class ModuloSemilla:
    """Una fila de `path_modules` con sus temas y su evaluación de cierre."""

    code: str
    position: int
    title: str
    flavor_name: str
    summary: str
    difficulty: DifficultyLevel
    estimated_minutes: int
    temas: tuple[TemaSemilla, ...]
    assessment_title: str
    assessment_question_count: int
    """Preguntas que se presentan en cada intento; el banco es el pool del módulo."""


@dataclass(frozen=True, slots=True)
class RutaSemilla:
    """Una fila de `learning_paths`: la Ruta del Reino completa."""

    code: str
    area_slug: str
    title: str
    goal_text: str
    summary: str
    declared_level: DeclaredLevel
    estimated_minutes: int
    modulos: tuple[ModuloSemilla, ...]
    origin: PathOrigin = PathOrigin.SEED
    status: PathStatus = PathStatus.ACTIVE
    source_mode: PathSourceMode = PathSourceMode.WITHOUT_SOURCE
    coverage_policy: CoveragePolicy = CoveragePolicy.MODEL_KNOWLEDGE
    content_status: ContentStatus = ContentStatus.READY
    provenance: ProvenanceOrigin = ProvenanceOrigin.MODEL_KNOWLEDGE
    coverage: CoverageLevel = CoverageLevel.FULL
    language: str = "es"
    is_public: bool = True


# ---------------------------------------------------------------------------
# Módulo 1 · Salón de las Puertas
# ---------------------------------------------------------------------------

_M1T1_PREGUNTAS: tuple[PreguntaSemilla, ...] = (
    PreguntaSemilla(
        code="m1-t1-q1",
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=DifficultyLevel.EASY,
        stem="¿Qué devuelve la consulta `SELECT nombre, region FROM reinos`?",
        body={
            "options": [
                {"key": "a", "text": "Todas las columnas de la tabla reinos."},
                {"key": "b", "text": "Las columnas nombre y region de todas las filas de reinos."},
                {"key": "c", "text": "Una sola fila con el nombre y la región del primer reino."},
                {"key": "d", "text": "El número de reinos que hay en la tabla."},
            ]
        },
        answer_key={"correct_option": "b", "correct_option_id": "b"},
        explanation=(
            "`SELECT` elige **columnas** y `FROM` elige la **tabla**. Sin `WHERE` no se "
            "descarta ninguna fila, así que la consulta devuelve dos columnas de todas "
            "las filas. Para traer todas las columnas se usaría `SELECT *`, y para "
            "contar filas haría falta `COUNT(*)`, que llega en el módulo 2."
        ),
        learning_objective="Distinguir qué selecciona SELECT y qué selecciona FROM.",
        estimated_seconds=40,
        inline=True,
    ),
    PreguntaSemilla(
        code="m1-t1-q2",
        question_type=QuestionType.TRUE_FALSE,
        difficulty=DifficultyLevel.EASY,
        stem="Decide si la afirmación es verdadera o falsa.",
        body={
            "statement": (
                "El orden en que escribes las columnas después de SELECT determina el "
                "orden de las columnas del resultado."
            )
        },
        answer_key={"correct": True, "answer": True},
        explanation=(
            "Verdadero. `SELECT region, nombre` y `SELECT nombre, region` devuelven los "
            "mismos datos, pero con las columnas en distinto orden. Es una de las pocas "
            "cosas en SQL donde el orden que escribes se respeta tal cual; el orden de "
            "las **filas**, en cambio, no está garantizado sin `ORDER BY`."
        ),
        learning_objective="Reconocer que la lista de SELECT fija el orden de las columnas.",
        estimated_seconds=30,
    ),
    PreguntaSemilla(
        code="m1-t1-q3",
        question_type=QuestionType.FILL_BLANK,
        difficulty=DifficultyLevel.EASY,
        stem=(
            "Completa la consulta que muestra el nombre de cada reino con la etiqueta "
            "«reino»: `SELECT nombre ___ reino ___ reinos`"
        ),
        body={
            "template": "SELECT nombre {{0}} reino {{1}} reinos",
            "blanks": [
                {"index": 0, "hint": "palabra que renombra una columna"},
                {"index": 1, "hint": "palabra que indica la tabla"},
            ],
        },
        answer_key={"blanks": [{"accepted": ["AS", "as"]}, {"accepted": ["FROM", "from"]}]},
        explanation=(
            "`AS` da un alias a la columna (el nombre con el que aparece en el resultado) "
            "y `FROM` indica de qué tabla salen los datos. El alias es puramente "
            "cosmético para quien lee el resultado, pero se vuelve imprescindible cuando "
            "dos tablas traen columnas con el mismo nombre, como verás en el módulo 3."
        ),
        learning_objective="Usar AS para renombrar una columna y FROM para nombrar la tabla.",
        estimated_seconds=50,
    ),
    PreguntaSemilla(
        code="m1-t1-q4",
        question_type=QuestionType.SQL_EXERCISE,
        difficulty=DifficultyLevel.EASY,
        stem=(
            "El archivero del Castillo te pide el censo básico de reinos. Escribe una "
            "consulta que devuelva el **nombre** y el **año de fundación** de todos los "
            "reinos, en ese orden de columnas."
        ),
        body=cuerpo_sql(),
        answer_key={"reference_sql": "SELECT nombre, fundado FROM reinos"},
        explanation=(
            "Basta con nombrar las dos columnas separadas por coma y la tabla de origen: "
            "`SELECT nombre, fundado FROM reinos`. No hace falta `WHERE` porque se piden "
            "todos los reinos, ni `ORDER BY` porque el enunciado no exige un orden."
        ),
        learning_objective="Escribir una consulta SELECT … FROM sobre una sola tabla.",
        estimated_seconds=120,
    ),
)

_M1T1 = TemaSemilla(
    code="m1-t1",
    position=1,
    title="SELECT y FROM: pedirle columnas a una tabla",
    learning_objectives=(
        "Explicar qué hace SELECT y qué hace FROM en una consulta.",
        "Escribir una consulta que devuelva columnas concretas de una tabla.",
        "Renombrar una columna del resultado con AS.",
    ),
    difficulty=DifficultyLevel.EASY,
    estimated_minutes=9,
    lecciones=(
        LeccionSemilla(
            code="m1-t1-l1",
            position=1,
            title="Tu primera consulta",
            summary=(
                "Qué es una tabla, qué hace SELECT, qué hace FROM y cómo pedir "
                "exactamente las columnas que necesitas."
            ),
            estimated_seconds=540,
            bloques=(
                BloqueSemilla(
                    position=1,
                    block_type=LessonBlockType.EXPLANATION,
                    body=(
                        "En el Castillo de las Consultas, cada **tabla** es un salón: filas "
                        "que son registros y columnas que son atributos. La tabla `reinos` "
                        "tiene una fila por reino y las columnas `id`, `nombre`, `region` y "
                        "`fundado`.\n\n"
                        "Una consulta SQL responde a una pregunta sobre esos salones, y la "
                        "más simple tiene dos partes:\n\n"
                        "- **`SELECT`** dice *qué columnas* quieres ver.\n"
                        "- **`FROM`** dice *de qué tabla* salen.\n\n"
                        "Se lee al revés de como se escribe: primero la base de datos va a "
                        "la tabla del `FROM` y después se queda con las columnas del "
                        "`SELECT`. Por eso una consulta sin `FROM` casi nunca tiene sentido.\n\n"
                        "`SELECT *` trae todas las columnas. Es cómodo para explorar, pero "
                        "en cuanto sabes qué necesitas conviene nombrarlo: el resultado es "
                        "más legible, más barato y no se rompe si mañana alguien añade una "
                        "columna nueva a la tabla."
                    ),
                ),
                BloqueSemilla(
                    position=2,
                    block_type=LessonBlockType.CODE_EXAMPLE,
                    body=(
                        "-- Todas las columnas de todos los reinos\n"
                        "SELECT * FROM reinos;\n\n"
                        "-- Solo lo que interesa, y con un nombre más claro en el resultado\n"
                        "SELECT nombre AS reino, fundado AS anio_fundacion\n"
                        "FROM reinos;"
                    ),
                    payload={"language": "sql"},
                ),
                BloqueSemilla(
                    position=3,
                    block_type=LessonBlockType.EXAMPLE,
                    body=(
                        "Sobre los cuatro reinos del mapa, `SELECT nombre, fundado FROM "
                        "reinos` devuelve:\n\n"
                        "| nombre | fundado |\n"
                        "|---|---|\n"
                        "| Valdoria | 1187 |\n"
                        "| Marlen | 1203 |\n"
                        "| Ostgard | 1150 |\n"
                        "| Selvana | 1290 |\n\n"
                        "Fíjate en dos cosas. Primera: hay **cuatro filas**, tantas como "
                        "reinos, porque no hemos filtrado nada. Segunda: salieron en el "
                        "orden en que estaban guardadas, no ordenadas por año. SQL no "
                        "promete ningún orden hasta que se lo pides con `ORDER BY`, y "
                        "confiar en el orden «natural» es uno de los errores más comunes "
                        "de quien empieza."
                    ),
                ),
                BloqueSemilla(
                    position=4,
                    block_type=LessonBlockType.INLINE_QUESTION,
                    question_code="m1-t1-q1",
                ),
                BloqueSemilla(
                    position=5,
                    block_type=LessonBlockType.SUMMARY,
                    body=(
                        "- `SELECT` elige columnas; `FROM` elige la tabla.\n"
                        "- `SELECT *` trae todo; nombrar las columnas es más claro y más robusto.\n"
                        "- `AS` renombra una columna en el resultado.\n"
                        "- Sin `ORDER BY` no hay orden de filas garantizado."
                    ),
                ),
            ),
            coverage_report=(
                {"objective": "Explicar qué hace SELECT y qué hace FROM en una consulta.", "status": "full"},
                {
                    "objective": "Escribir una consulta que devuelva columnas concretas de una tabla.",
                    "status": "full",
                },
                {"objective": "Renombrar una columna del resultado con AS.", "status": "full"},
            ),
        ),
    ),
    preguntas=_M1T1_PREGUNTAS,
)


_M1T2_PREGUNTAS: tuple[PreguntaSemilla, ...] = (
    PreguntaSemilla(
        code="m1-t2-q1",
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=DifficultyLevel.MEDIUM,
        stem=(
            "Quieres los caballeros del reino 1 **que además** tengan más de 5 victorias. "
            "¿Cuál es la cláusula `WHERE` correcta?"
        ),
        body={
            "options": [
                {"key": "a", "text": "WHERE reino_id = 1 OR victorias > 5"},
                {"key": "b", "text": "WHERE reino_id = 1 AND victorias > 5"},
                {"key": "c", "text": "WHERE reino_id = 1, victorias > 5"},
                {"key": "d", "text": "WHERE reino_id == 1 AND victorias >= 5"},
            ]
        },
        answer_key={"correct_option": "b", "correct_option_id": "b"},
        explanation=(
            "«Y además» es `AND`: la fila debe cumplir las dos condiciones. `OR` "
            "devolvería también caballeros de otros reinos; la coma no es un operador "
            "lógico en `WHERE`; y en SQL la igualdad se escribe con un solo `=` (además, "
            "`>= 5` incluiría al que tiene exactamente 5, que el enunciado excluye)."
        ),
        learning_objective="Combinar condiciones con AND y OR en un WHERE.",
        estimated_seconds=50,
        inline=True,
    ),
    PreguntaSemilla(
        code="m1-t2-q2",
        question_type=QuestionType.TRUE_FALSE,
        difficulty=DifficultyLevel.MEDIUM,
        stem="Decide si la afirmación es verdadera o falsa.",
        body={
            "statement": (
                "La condición `WHERE reino_id = NULL` devuelve las filas de los "
                "caballeros que no tienen reino asignado."
            )
        },
        answer_key={"correct": False, "answer": False},
        explanation=(
            "Falso, y es la trampa clásica. `NULL` significa «valor desconocido», y "
            "comparar algo con lo desconocido no da ni verdadero ni falso: da `NULL`, "
            "que `WHERE` descarta. La consulta no devolvería **ninguna** fila. Para "
            "buscar ausencias hay que escribir `WHERE reino_id IS NULL`."
        ),
        learning_objective="Usar IS NULL en lugar de = NULL para detectar valores ausentes.",
        estimated_seconds=40,
    ),
    PreguntaSemilla(
        code="m1-t2-q3",
        question_type=QuestionType.ORDERING,
        difficulty=DifficultyLevel.MEDIUM,
        stem=("Ordena las cláusulas tal como deben escribirse en una consulta de una sola tabla."),
        body={
            "items": [
                {"key": "orderby", "text": "ORDER BY victorias DESC"},
                {"key": "select", "text": "SELECT nombre, victorias"},
                {"key": "where", "text": "WHERE reino_id = 1"},
                {"key": "from", "text": "FROM caballeros"},
            ]
        },
        answer_key={"order": ["select", "from", "where", "orderby"]},
        explanation=(
            "El orden de escritura es fijo: `SELECT` → `FROM` → `WHERE` → `ORDER BY`. "
            "Conviene recordar que el orden en que la base de datos **ejecuta** las "
            "cláusulas es otro (primero `FROM`, luego `WHERE`, luego `SELECT` y al final "
            "`ORDER BY`), y eso explica por qué un alias creado en el `SELECT` sí se "
            "puede usar en `ORDER BY` pero no en `WHERE`."
        ),
        learning_objective="Colocar SELECT, FROM, WHERE y ORDER BY en el orden correcto.",
        estimated_seconds=60,
    ),
    PreguntaSemilla(
        code="m1-t2-q4",
        question_type=QuestionType.SQL_EXERCISE,
        difficulty=DifficultyLevel.MEDIUM,
        stem=(
            "El maestro de armas quiere la lista de veteranos. Devuelve el **nombre** de "
            "los caballeros con **más de 5 victorias**, ordenados de más victorias a "
            "menos. El orden de las filas importa."
        ),
        body=cuerpo_sql(ordenado=True),
        answer_key={
            "reference_sql": "SELECT nombre FROM caballeros WHERE victorias > 5 ORDER BY victorias DESC"
        },
        explanation=(
            "`WHERE victorias > 5` deja fuera a Brenna (3), Fiora (2) y Hilde (4); "
            "`ORDER BY victorias DESC` coloca primero a Edric (15), luego a Aldric (12), "
            "Corvin (9), Dalia (7) y Garen (6). Cuidado con `>=`: incluiría a quien tenga "
            "exactamente 5 victorias, y el enunciado dice «más de»."
        ),
        learning_objective="Filtrar con WHERE y ordenar el resultado con ORDER BY … DESC.",
        estimated_seconds=150,
    ),
)

_M1T2 = TemaSemilla(
    code="m1-t2",
    position=2,
    title="WHERE y ORDER BY: filtrar filas y ordenarlas",
    learning_objectives=(
        "Filtrar filas con WHERE usando comparaciones, AND y OR.",
        "Detectar valores ausentes con IS NULL.",
        "Ordenar el resultado con ORDER BY, ascendente y descendente.",
    ),
    difficulty=DifficultyLevel.MEDIUM,
    estimated_minutes=10,
    lecciones=(
        LeccionSemilla(
            code="m1-t2-l1",
            position=1,
            title="Filtrar el caudal",
            summary=(
                "Cómo quedarse solo con las filas que importan y cómo decidir en qué "
                "orden se presentan, incluido el caso especial de los valores nulos."
            ),
            estimated_seconds=600,
            bloques=(
                BloqueSemilla(
                    position=1,
                    block_type=LessonBlockType.EXPLANATION,
                    body=(
                        "Una tabla entera rara vez responde una pregunta útil. **`WHERE`** "
                        "aplica una condición a cada fila y conserva solo las que la "
                        "cumplen.\n\n"
                        "Los operadores habituales son `=`, `<>` (distinto), `<`, `>`, "
                        "`<=`, `>=`, `BETWEEN`, `IN` y `LIKE`. Se combinan con `AND` "
                        "(deben cumplirse todas) y `OR` (basta una), y los paréntesis "
                        "deciden quién manda cuando mezclas ambos.\n\n"
                        "Hay un caso que merece su propio párrafo: **`NULL`**. No es cero "
                        "ni cadena vacía, es «no se sabe». Cualquier comparación con "
                        "`NULL` devuelve desconocido, y `WHERE` descarta lo desconocido. "
                        "Por eso `= NULL` no encuentra nunca nada y hay que escribir "
                        "`IS NULL` o `IS NOT NULL`.\n\n"
                        "**`ORDER BY`** se aplica al final, sobre las filas que "
                        "sobrevivieron al filtro. `ASC` es ascendente (el valor por "
                        "defecto) y `DESC`, descendente. Se puede ordenar por varias "
                        "columnas: la segunda desempata a la primera."
                    ),
                ),
                BloqueSemilla(
                    position=2,
                    block_type=LessonBlockType.CODE_EXAMPLE,
                    body=(
                        "-- Caballeros del reino 1 con más de 5 victorias\n"
                        "SELECT nombre, victorias\n"
                        "FROM caballeros\n"
                        "WHERE reino_id = 1 AND victorias > 5\n"
                        "ORDER BY victorias DESC;\n\n"
                        "-- Quién no tiene reino asignado\n"
                        "SELECT nombre\n"
                        "FROM caballeros\n"
                        "WHERE reino_id IS NULL;\n\n"
                        "-- Dos criterios de orden: primero por rango, y dentro de cada\n"
                        "-- rango, de más victorias a menos\n"
                        "SELECT nombre, rango, victorias\n"
                        "FROM caballeros\n"
                        "ORDER BY rango ASC, victorias DESC;"
                    ),
                    payload={"language": "sql"},
                ),
                BloqueSemilla(
                    position=3,
                    block_type=LessonBlockType.EXAMPLE,
                    body=(
                        "La primera consulta devuelve una sola fila: **Aldric, 12**. "
                        "Garen también es del reino 1, pero tiene 6 victorias… y sí, 6 es "
                        "mayor que 5, así que Garen también aparece. El resultado real es:\n\n"
                        "| nombre | victorias |\n"
                        "|---|---|\n"
                        "| Aldric | 12 |\n"
                        "| Garen | 6 |\n\n"
                        "Brenna queda fuera con sus 3 victorias. Si hubiéramos escrito "
                        "`OR` en lugar de `AND`, habrían entrado además Corvin, Dalia y "
                        "Edric, que no son del reino 1: un error silencioso que no "
                        "provoca ningún mensaje de la base de datos y que solo se detecta "
                        "leyendo el resultado con calma."
                    ),
                ),
                BloqueSemilla(
                    position=4,
                    block_type=LessonBlockType.INLINE_QUESTION,
                    question_code="m1-t2-q1",
                ),
                BloqueSemilla(
                    position=5,
                    block_type=LessonBlockType.SUMMARY,
                    body=(
                        "- `WHERE` filtra filas; `AND` exige todo, `OR` se conforma con una.\n"
                        "- `NULL` es «desconocido»: se busca con `IS NULL`, nunca con `= NULL`.\n"
                        "- `ORDER BY` ordena al final; `DESC` invierte y varias columnas desempatan.\n"
                        "- Un `OR` mal puesto no da error: da un resultado equivocado."
                    ),
                ),
            ),
            coverage_report=(
                {"objective": "Filtrar filas con WHERE usando comparaciones, AND y OR.", "status": "full"},
                {"objective": "Detectar valores ausentes con IS NULL.", "status": "full"},
                {
                    "objective": "Ordenar el resultado con ORDER BY, ascendente y descendente.",
                    "status": "full",
                },
            ),
        ),
    ),
    preguntas=_M1T2_PREGUNTAS,
)


_MODULO_1 = ModuloSemilla(
    code="m1",
    position=1,
    title="Primeras consultas",
    flavor_name="Salón de las Puertas",
    summary=(
        "El salón donde cada puerta se abre solo ante la pregunta bien formulada. Aquí "
        "aprendes a pedir columnas, a filtrar filas y a decidir en qué orden se presentan."
    ),
    difficulty=DifficultyLevel.EASY,
    estimated_minutes=25,
    temas=(_M1T1, _M1T2),
    assessment_title="Prueba del Salón de las Puertas",
    assessment_question_count=6,
)


# ---------------------------------------------------------------------------
# Módulo 2 · Torre de los Escribas
# ---------------------------------------------------------------------------

_M2T1_PREGUNTAS: tuple[PreguntaSemilla, ...] = (
    PreguntaSemilla(
        code="m2-t1-q1",
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=DifficultyLevel.MEDIUM,
        stem=(
            "La tabla `caballeros` tiene 8 filas, y una de ellas tiene `reino_id` nulo. "
            "¿Qué devuelve `SELECT COUNT(reino_id) FROM caballeros`?"
        ),
        body={
            "options": [
                {"key": "a", "text": "8, porque cuenta todas las filas."},
                {"key": "b", "text": "7, porque COUNT de una columna ignora los NULL."},
                {"key": "c", "text": "1, porque cuenta solo la fila con NULL."},
                {"key": "d", "text": "NULL, porque hay un valor nulo en la columna."},
            ]
        },
        answer_key={"correct_option": "b", "correct_option_id": "b"},
        explanation=(
            "`COUNT(columna)` cuenta **valores presentes**, no filas: los `NULL` no se "
            "cuentan. Por eso da 7. `COUNT(*)` sí cuenta filas y daría 8. Esa diferencia "
            "es una fuente clásica de informes que no cuadran: conviene elegir a "
            "conciencia entre contar filas y contar valores."
        ),
        learning_objective="Diferenciar COUNT(*) de COUNT(columna) ante valores nulos.",
        estimated_seconds=55,
        inline=True,
    ),
    PreguntaSemilla(
        code="m2-t1-q2",
        question_type=QuestionType.FILL_BLANK,
        difficulty=DifficultyLevel.EASY,
        stem=(
            "Completa la consulta que devuelve la victoria más alta y el promedio de "
            "victorias: `SELECT ___(victorias), ___(victorias) FROM caballeros`"
        ),
        body={
            "template": "SELECT {{0}}(victorias), {{1}}(victorias) FROM caballeros",
            "blanks": [
                {"index": 0, "hint": "el valor más alto"},
                {"index": 1, "hint": "el promedio"},
            ],
        },
        answer_key={"blanks": [{"accepted": ["MAX", "max"]}, {"accepted": ["AVG", "avg"]}]},
        explanation=(
            "`MAX` devuelve el valor mayor y `AVG` el promedio. Las cinco funciones de "
            "agregación básicas son `COUNT`, `SUM`, `AVG`, `MIN` y `MAX`, y todas "
            "resumen muchas filas en un solo valor. Ojo con `AVG`: ignora los `NULL`, "
            "así que promedia sobre los valores presentes, no sobre todas las filas."
        ),
        learning_objective="Aplicar las funciones de agregación básicas sobre una columna.",
        estimated_seconds=50,
    ),
    PreguntaSemilla(
        code="m2-t1-q3",
        question_type=QuestionType.MATCHING,
        difficulty=DifficultyLevel.EASY,
        stem="Relaciona cada función de agregación con lo que devuelve.",
        body={
            "left": [
                {"key": "count", "text": "COUNT(*)"},
                {"key": "sum", "text": "SUM(victorias)"},
                {"key": "avg", "text": "AVG(victorias)"},
                {"key": "min", "text": "MIN(fundado)"},
            ],
            "right": [
                {"key": "filas", "text": "Cuántas filas hay"},
                {"key": "total", "text": "El total acumulado de la columna"},
                {"key": "promedio", "text": "El promedio de la columna"},
                {"key": "menor", "text": "El valor más pequeño de la columna"},
            ],
        },
        answer_key={
            "pairs": [
                {"left": "count", "right": "filas"},
                {"left": "sum", "right": "total"},
                {"left": "avg", "right": "promedio"},
                {"left": "min", "right": "menor"},
            ]
        },
        explanation=(
            "`COUNT(*)` cuenta filas, `SUM` acumula, `AVG` promedia, `MIN` y `MAX` "
            "devuelven los extremos. `MIN(fundado)` sobre los reinos da 1150, el año del "
            "más antiguo: Ostgard."
        ),
        learning_objective="Asociar cada función de agregación con el resumen que produce.",
        estimated_seconds=60,
    ),
    PreguntaSemilla(
        code="m2-t1-q4",
        question_type=QuestionType.SQL_EXERCISE,
        difficulty=DifficultyLevel.MEDIUM,
        stem=(
            "El senescal quiere una sola línea de resumen: cuántos caballeros hay en "
            "total y cuántas victorias suman entre todos. Devuelve dos columnas, el "
            "recuento primero y la suma después."
        ),
        body=cuerpo_sql(),
        answer_key={
            "reference_sql": (
                "SELECT COUNT(*) AS total_caballeros, SUM(victorias) AS total_victorias FROM caballeros"
            )
        },
        explanation=(
            "Una consulta con funciones de agregación y sin `GROUP BY` colapsa toda la "
            "tabla en **una sola fila**: 8 caballeros y 58 victorias. Usar `COUNT(*)` en "
            "vez de `COUNT(reino_id)` es lo correcto aquí, porque se pide cuántos "
            "caballeros hay, no cuántos tienen reino."
        ),
        learning_objective="Resumir una tabla entera con COUNT y SUM en una sola fila.",
        estimated_seconds=140,
    ),
)

_M2T1 = TemaSemilla(
    code="m2-t1",
    position=1,
    title="Funciones de agregación: COUNT, SUM, AVG, MIN y MAX",
    learning_objectives=(
        "Resumir muchas filas en un solo valor con funciones de agregación.",
        "Distinguir COUNT(*) de COUNT(columna) cuando hay valores nulos.",
        "Combinar varias agregaciones en una misma consulta.",
    ),
    difficulty=DifficultyLevel.MEDIUM,
    estimated_minutes=9,
    lecciones=(
        LeccionSemilla(
            code="m2-t1-l1",
            position=1,
            title="Contar, sumar y promediar",
            summary=(
                "Las cinco funciones que convierten una tabla entera en una sola fila de "
                "respuesta, y la trampa de los nulos al contar."
            ),
            estimated_seconds=540,
            bloques=(
                BloqueSemilla(
                    position=1,
                    block_type=LessonBlockType.EXPLANATION,
                    body=(
                        "Hasta ahora cada fila de la tabla producía, como mucho, una fila "
                        "de resultado. Las **funciones de agregación** rompen esa relación: "
                        "leen muchas filas y devuelven **un solo valor**.\n\n"
                        "Son cinco y se aprenden en un minuto:\n\n"
                        "- `COUNT(*)` — cuántas filas hay.\n"
                        "- `COUNT(columna)` — cuántos valores **no nulos** hay en esa columna.\n"
                        "- `SUM(columna)` — el total acumulado.\n"
                        "- `AVG(columna)` — el promedio.\n"
                        "- `MIN(columna)` y `MAX(columna)` — los extremos.\n\n"
                        "La distinción entre `COUNT(*)` y `COUNT(columna)` parece un "
                        "detalle y es la causa número uno de informes que no cuadran. "
                        "`SUM` y `AVG` también ignoran los nulos, así que el promedio se "
                        "calcula sobre los valores que existen, no sobre todas las filas.\n\n"
                        "Regla importante: si en el `SELECT` hay una función de agregación "
                        "y **no** hay `GROUP BY`, toda la tabla se resume en una única "
                        "fila. Por eso no puedes mezclar `SUM(victorias)` con `nombre` sin "
                        "explicarle a la base de datos por qué nombre elegir; eso es "
                        "justo lo que resuelve el tema siguiente."
                    ),
                ),
                BloqueSemilla(
                    position=2,
                    block_type=LessonBlockType.CODE_EXAMPLE,
                    body=(
                        "-- Resumen de toda la tabla en una sola fila\n"
                        "SELECT COUNT(*)        AS caballeros,\n"
                        "       SUM(victorias)  AS victorias_totales,\n"
                        "       AVG(victorias)  AS victorias_media,\n"
                        "       MAX(victorias)  AS mejor_marca\n"
                        "FROM caballeros;\n\n"
                        "-- Contar filas frente a contar valores presentes\n"
                        "SELECT COUNT(*) AS filas, COUNT(reino_id) AS con_reino\n"
                        "FROM caballeros;"
                    ),
                    payload={"language": "sql"},
                ),
                BloqueSemilla(
                    position=3,
                    block_type=LessonBlockType.EXAMPLE,
                    body=(
                        "La segunda consulta devuelve `filas = 8` y `con_reino = 7`. La "
                        "diferencia es Hilde, la caballera errante, cuyo `reino_id` es "
                        "`NULL`.\n\n"
                        "Imagina que el informe del Reino dice «7 caballeros» porque "
                        "alguien escribió `COUNT(reino_id)` pensando que contaba "
                        "personas. Nadie recibiría un error; simplemente falta una "
                        "caballera en el censo. Cuando escribas un `COUNT`, pregúntate "
                        "siempre: ¿estoy contando **filas** o **valores**?"
                    ),
                ),
                BloqueSemilla(
                    position=4,
                    block_type=LessonBlockType.INLINE_QUESTION,
                    question_code="m2-t1-q1",
                ),
                BloqueSemilla(
                    position=5,
                    block_type=LessonBlockType.SUMMARY,
                    body=(
                        "- Agregar es convertir muchas filas en un valor.\n"
                        "- `COUNT(*)` cuenta filas; `COUNT(columna)` cuenta valores no nulos.\n"
                        "- `SUM` y `AVG` también ignoran los nulos.\n"
                        "- Sin `GROUP BY`, la tabla entera se resume en una sola fila."
                    ),
                ),
            ),
            coverage_report=(
                {
                    "objective": "Resumir muchas filas en un solo valor con funciones de agregación.",
                    "status": "full",
                },
                {
                    "objective": "Distinguir COUNT(*) de COUNT(columna) cuando hay valores nulos.",
                    "status": "full",
                },
                {"objective": "Combinar varias agregaciones en una misma consulta.", "status": "full"},
            ),
        ),
    ),
    preguntas=_M2T1_PREGUNTAS,
)


_M2T2_PREGUNTAS: tuple[PreguntaSemilla, ...] = (
    PreguntaSemilla(
        code="m2-t2-q1",
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=DifficultyLevel.HARD,
        stem=(
            "Quieres los rangos con más de 10 victorias sumadas, contando solo a los "
            "caballeros que tienen reino. ¿Qué consulta lo hace bien?"
        ),
        body={
            "options": [
                {
                    "key": "a",
                    "text": (
                        "SELECT rango, SUM(victorias) FROM caballeros "
                        "WHERE SUM(victorias) > 10 GROUP BY rango"
                    ),
                },
                {
                    "key": "b",
                    "text": (
                        "SELECT rango, SUM(victorias) FROM caballeros "
                        "WHERE reino_id IS NOT NULL GROUP BY rango HAVING SUM(victorias) > 10"
                    ),
                },
                {
                    "key": "c",
                    "text": (
                        "SELECT rango, SUM(victorias) FROM caballeros "
                        "GROUP BY rango HAVING reino_id IS NOT NULL"
                    ),
                },
                {
                    "key": "d",
                    "text": (
                        "SELECT rango, SUM(victorias) FROM caballeros "
                        "HAVING reino_id IS NOT NULL AND SUM(victorias) > 10"
                    ),
                },
            ]
        },
        answer_key={"correct_option": "b", "correct_option_id": "b"},
        explanation=(
            "`WHERE` filtra **filas antes** de agrupar y `HAVING` filtra **grupos "
            "después** de agrupar. La condición sobre `reino_id` mira una fila, así que "
            "va en `WHERE`; la condición sobre `SUM(victorias)` mira un grupo entero, así "
            "que va en `HAVING`. La opción (a) pone una agregación en `WHERE`, que es un "
            "error de sintaxis, y (c) y (d) usan `HAVING` con una columna que ya no "
            "existe una vez agrupadas las filas."
        ),
        learning_objective="Decidir si una condición va en WHERE o en HAVING.",
        estimated_seconds=90,
        inline=True,
    ),
    PreguntaSemilla(
        code="m2-t2-q2",
        question_type=QuestionType.TRUE_FALSE,
        difficulty=DifficultyLevel.MEDIUM,
        stem="Decide si la afirmación es verdadera o falsa.",
        body={
            "statement": (
                "Toda columna que aparece en el SELECT sin estar dentro de una función "
                "de agregación debe aparecer también en el GROUP BY."
            )
        },
        answer_key={"correct": True, "answer": True},
        explanation=(
            "Verdadero, y es la regla que explica casi todos los errores de `GROUP BY`. "
            "Si agrupas por `rango`, cada fila del resultado representa a un grupo "
            "entero; pedir `nombre` sin agregarlo no tiene respuesta única, porque en el "
            "grupo hay varios nombres. O agrupas por esa columna, o la resumes con una "
            "función."
        ),
        learning_objective="Aplicar la regla que liga las columnas del SELECT con el GROUP BY.",
        estimated_seconds=45,
    ),
    PreguntaSemilla(
        code="m2-t2-q3",
        question_type=QuestionType.OPEN_SHORT,
        difficulty=DifficultyLevel.HARD,
        stem=(
            "Explica con tus palabras, en dos o tres frases, la diferencia entre WHERE y "
            "HAVING, y da un ejemplo de una condición que solo pueda ir en HAVING."
        ),
        body={
            "rubric": {
                "criteria": [
                    {
                        "key": "momento",
                        "text": "Indica que WHERE actúa antes de agrupar y HAVING después.",
                    },
                    {
                        "key": "unidad",
                        "text": "Señala que WHERE filtra filas individuales y HAVING filtra grupos.",
                    },
                    {
                        "key": "ejemplo",
                        "text": "Da una condición con función de agregación, como COUNT(*) > 2.",
                    },
                ],
                "max_words": 90,
            }
        },
        answer_key={
            "reference_answer": (
                "WHERE se evalúa sobre cada fila antes de formar los grupos, así que solo "
                "puede usar columnas de la tabla. HAVING se evalúa después de agrupar y "
                "filtra grupos completos, por lo que puede usar funciones de agregación. "
                "Una condición como HAVING COUNT(*) >= 2 solo puede ir en HAVING, porque "
                "antes de agrupar ese recuento todavía no existe."
            ),
            "key_points": [
                "WHERE antes de agrupar, HAVING después",
                "WHERE filtra filas, HAVING filtra grupos",
                "HAVING admite funciones de agregación",
            ],
        },
        explanation=(
            "La respuesta debe dejar claro el **momento** (antes o después de agrupar) y "
            "la **unidad** que se filtra (fila o grupo). El ejemplo canónico es "
            "`HAVING COUNT(*) >= 2`: ese recuento no existe hasta que las filas se han "
            "agrupado, de modo que no cabe en `WHERE`."
        ),
        learning_objective="Explicar la diferencia entre filtrar filas y filtrar grupos.",
        estimated_seconds=180,
    ),
    PreguntaSemilla(
        code="m2-t2-q4",
        question_type=QuestionType.SQL_EXERCISE,
        difficulty=DifficultyLevel.HARD,
        stem=(
            "El heraldo prepara el desfile por rangos. Devuelve el **rango** y **cuántos "
            "caballeros** hay en él, pero solo para los rangos con al menos 2 caballeros. "
            "Llama `cuantos` a la segunda columna."
        ),
        body=cuerpo_sql(),
        answer_key={
            "reference_sql": (
                "SELECT rango, COUNT(*) AS cuantos FROM caballeros GROUP BY rango HAVING COUNT(*) >= 2"
            )
        },
        explanation=(
            "Se agrupa por `rango`, se cuenta cada grupo y se descartan los grupos "
            "pequeños con `HAVING`. Quedan `capitan` (2), `escudero` (2) y `caballero` "
            "(3); `errante` se queda fuera con uno solo. Poner esa condición en `WHERE` "
            "daría error: `COUNT(*)` todavía no existe cuando `WHERE` se evalúa."
        ),
        learning_objective="Agrupar con GROUP BY y filtrar grupos con HAVING.",
        estimated_seconds=180,
    ),
)

_M2T2 = TemaSemilla(
    code="m2-t2",
    position=2,
    title="GROUP BY y HAVING: resumir por categorías",
    learning_objectives=(
        "Agrupar filas por una columna y calcular un resumen por grupo.",
        "Aplicar la regla que liga las columnas del SELECT con el GROUP BY.",
        "Elegir entre WHERE y HAVING según lo que se quiera filtrar.",
    ),
    difficulty=DifficultyLevel.HARD,
    estimated_minutes=12,
    lecciones=(
        LeccionSemilla(
            code="m2-t2-l1",
            position=1,
            title="Un resumen por cada grupo",
            summary=(
                "Cómo pedir un resumen por categoría con GROUP BY y cómo filtrar grupos "
                "enteros con HAVING sin confundirlo con WHERE."
            ),
            estimated_seconds=660,
            bloques=(
                BloqueSemilla(
                    position=1,
                    block_type=LessonBlockType.EXPLANATION,
                    body=(
                        "`SUM(victorias)` sobre toda la tabla da un número. Pero la "
                        "pregunta interesante casi nunca es «cuántas victorias hay», sino "
                        "«cuántas victorias hay **por rango**». Eso es **`GROUP BY`**.\n\n"
                        "`GROUP BY rango` parte la tabla en montones, uno por cada valor "
                        "distinto de `rango`, y la función de agregación se aplica dentro "
                        "de cada montón. El resultado tiene una fila por grupo.\n\n"
                        "De ahí sale la regla que más se incumple al empezar: **toda "
                        "columna del `SELECT` que no esté dentro de una función de "
                        "agregación tiene que estar en el `GROUP BY`**. Si agrupas por "
                        "rango y pides `nombre`, la base de datos no sabe cuál de los "
                        "nombres del grupo darte.\n\n"
                        "Y una vez formados los grupos, a veces quieres quedarte solo con "
                        "algunos. Para eso está **`HAVING`**, que es a los grupos lo que "
                        "`WHERE` es a las filas:\n\n"
                        "- `WHERE` se evalúa **antes** de agrupar, sobre filas sueltas.\n"
                        "- `HAVING` se evalúa **después** de agrupar, sobre grupos ya formados.\n\n"
                        "Por eso `WHERE COUNT(*) > 2` es un error y `HAVING COUNT(*) > 2` "
                        "es correcto: cuando `WHERE` actúa, ese recuento todavía no existe."
                    ),
                ),
                BloqueSemilla(
                    position=2,
                    block_type=LessonBlockType.CODE_EXAMPLE,
                    body=(
                        "-- Un resumen por rango\n"
                        "SELECT rango,\n"
                        "       COUNT(*)       AS cuantos,\n"
                        "       SUM(victorias) AS victorias\n"
                        "FROM caballeros\n"
                        "GROUP BY rango\n"
                        "ORDER BY victorias DESC;\n\n"
                        "-- Filtrar filas antes (WHERE) y grupos después (HAVING)\n"
                        "SELECT rango, SUM(victorias) AS victorias\n"
                        "FROM caballeros\n"
                        "WHERE reino_id IS NOT NULL\n"
                        "GROUP BY rango\n"
                        "HAVING SUM(victorias) > 10;"
                    ),
                    payload={"language": "sql"},
                ),
                BloqueSemilla(
                    position=3,
                    block_type=LessonBlockType.EXAMPLE,
                    body=(
                        "La primera consulta devuelve cuatro filas, una por rango:\n\n"
                        "| rango | cuantos | victorias |\n"
                        "|---|---|---|\n"
                        "| caballero | 3 | 28 |\n"
                        "| capitan | 2 | 21 |\n"
                        "| escudero | 2 | 5 |\n"
                        "| errante | 1 | 4 |\n\n"
                        "La segunda añade dos filtros en dos momentos distintos. El "
                        "`WHERE` expulsa a Hilde (no tiene reino) **antes** de agrupar, "
                        "así que el grupo `errante` desaparece por completo. Después, el "
                        "`HAVING` descarta `escudero`, cuyo total es 5. Quedan "
                        "`caballero` (28) y `capitan` (21).\n\n"
                        "Cambia mentalmente el orden y verás por qué importa: si el "
                        "filtro de `reino_id` se aplicara después de agrupar, el grupo "
                        "`errante` habría contaminado los totales."
                    ),
                ),
                BloqueSemilla(
                    position=4,
                    block_type=LessonBlockType.INLINE_QUESTION,
                    question_code="m2-t2-q1",
                ),
                BloqueSemilla(
                    position=5,
                    block_type=LessonBlockType.SUMMARY,
                    body=(
                        "- `GROUP BY` parte la tabla en grupos; la agregación se aplica dentro de cada uno.\n"
                        "- Toda columna no agregada del `SELECT` debe estar en el `GROUP BY`.\n"
                        "- `WHERE` filtra filas antes de agrupar; `HAVING` filtra grupos después.\n"
                        "- Una función de agregación nunca puede ir en `WHERE`."
                    ),
                ),
            ),
            coverage_report=(
                {
                    "objective": "Agrupar filas por una columna y calcular un resumen por grupo.",
                    "status": "full",
                },
                {
                    "objective": "Aplicar la regla que liga las columnas del SELECT con el GROUP BY.",
                    "status": "full",
                },
                {
                    "objective": "Elegir entre WHERE y HAVING según lo que se quiera filtrar.",
                    "status": "full",
                },
            ),
        ),
    ),
    preguntas=_M2T2_PREGUNTAS,
)


_MODULO_2 = ModuloSemilla(
    code="m2",
    position=2,
    title="Agrupar y resumir",
    flavor_name="Torre de los Escribas",
    summary=(
        "Los escribas no copian filas: las resumen. Aquí aprendes a contar, sumar y "
        "promediar, y a pedir un resumen por cada categoría en lugar de uno global."
    ),
    difficulty=DifficultyLevel.MEDIUM,
    estimated_minutes=28,
    temas=(_M2T1, _M2T2),
    assessment_title="Prueba de la Torre de los Escribas",
    assessment_question_count=6,
)


# ---------------------------------------------------------------------------
# Módulo 3 · Puente de las Uniones
# ---------------------------------------------------------------------------

_M3T1_PREGUNTAS: tuple[PreguntaSemilla, ...] = (
    PreguntaSemilla(
        code="m3-t1-q1",
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=DifficultyLevel.MEDIUM,
        stem=(
            "¿Cuántas filas devuelve `SELECT c.nombre, r.nombre FROM caballeros c JOIN "
            "reinos r ON c.reino_id = r.id`?"
        ),
        body={
            "options": [
                {"key": "a", "text": "8, una por caballero."},
                {"key": "b", "text": "7, porque Hilde no tiene reino y queda fuera."},
                {"key": "c", "text": "4, una por reino."},
                {"key": "d", "text": "32, el producto de 8 caballeros por 4 reinos."},
            ]
        },
        answer_key={"correct_option": "b", "correct_option_id": "b"},
        explanation=(
            "Un `JOIN` interno solo conserva las filas que **encuentran pareja**. Hilde "
            "tiene `reino_id` nulo, así que no casa con ningún reino y desaparece del "
            "resultado: quedan 7 filas. Las 32 filas de la opción (d) serían el producto "
            "cartesiano que aparece si se olvida el `ON`, un error clásico y muy visible."
        ),
        learning_objective="Predecir cuántas filas conserva un INNER JOIN.",
        estimated_seconds=60,
        inline=True,
    ),
    PreguntaSemilla(
        code="m3-t1-q2",
        question_type=QuestionType.ORDERING,
        difficulty=DifficultyLevel.MEDIUM,
        stem="Ordena las partes de una consulta con JOIN tal como deben escribirse.",
        body={
            "items": [
                {"key": "on", "text": "ON c.reino_id = r.id"},
                {"key": "select", "text": "SELECT c.nombre, r.nombre AS reino"},
                {"key": "join", "text": "JOIN reinos r"},
                {"key": "from", "text": "FROM caballeros c"},
                {"key": "where", "text": "WHERE r.region = 'Norte'"},
            ]
        },
        answer_key={"order": ["select", "from", "join", "on", "where"]},
        explanation=(
            "`SELECT` → `FROM` → `JOIN` → `ON` → `WHERE`. El `ON` viaja siempre pegado a "
            "su `JOIN`, porque describe **cómo** se unen esas dos tablas; el `WHERE` "
            "llega después y filtra el resultado ya unido. Los alias `c` y `r` se "
            "declaran en `FROM` y `JOIN`, y por eso pueden usarse en todas las demás "
            "cláusulas."
        ),
        learning_objective="Colocar JOIN, ON y WHERE en el orden correcto.",
        estimated_seconds=70,
    ),
    PreguntaSemilla(
        code="m3-t1-q3",
        question_type=QuestionType.MATCHING,
        difficulty=DifficultyLevel.MEDIUM,
        stem="Relaciona cada elemento de una consulta con JOIN con su función.",
        body={
            "left": [
                {"key": "on", "text": "ON"},
                {"key": "alias", "text": "FROM caballeros c"},
                {"key": "inner", "text": "INNER JOIN"},
                {"key": "clave", "text": "c.reino_id"},
            ],
            "right": [
                {"key": "condicion", "text": "Dice qué columnas deben coincidir"},
                {"key": "apodo", "text": "Da un alias corto a la tabla"},
                {"key": "interseccion", "text": "Conserva solo las filas con pareja"},
                {"key": "foranea", "text": "Clave foránea que apunta a la otra tabla"},
            ],
        },
        answer_key={
            "pairs": [
                {"left": "on", "right": "condicion"},
                {"left": "alias", "right": "apodo"},
                {"left": "inner", "right": "interseccion"},
                {"left": "clave", "right": "foranea"},
            ]
        },
        explanation=(
            "El `ON` lleva la condición de unión, el alias abrevia el nombre de la tabla, "
            "`INNER JOIN` se queda con la intersección y `reino_id` es la clave foránea "
            "que conecta `caballeros` con `reinos`. `JOIN` a secas significa `INNER JOIN`."
        ),
        learning_objective="Identificar las piezas de una consulta con JOIN.",
        estimated_seconds=70,
    ),
    PreguntaSemilla(
        code="m3-t1-q4",
        question_type=QuestionType.SQL_EXERCISE,
        difficulty=DifficultyLevel.MEDIUM,
        stem=(
            "El cronista quiere saber a qué reino sirve cada caballero. Devuelve el "
            "**nombre del caballero** y el **nombre de su reino** (llámalo `reino`), solo "
            "para los caballeros que tienen reino asignado."
        ),
        body=cuerpo_sql(),
        answer_key={
            "reference_sql": (
                "SELECT c.nombre, r.nombre AS reino FROM caballeros c JOIN reinos r ON c.reino_id = r.id"
            )
        },
        explanation=(
            "El `INNER JOIN` ya excluye por sí solo a quien no tiene pareja, así que no "
            "hace falta añadir `WHERE c.reino_id IS NOT NULL`. El alias `AS reino` es "
            "necesario porque las dos tablas tienen una columna `nombre` y el resultado "
            "quedaría ambiguo de leer."
        ),
        learning_objective="Unir dos tablas con INNER JOIN por su clave foránea.",
        estimated_seconds=180,
    ),
)

_M3T1 = TemaSemilla(
    code="m3-t1",
    position=1,
    title="INNER JOIN: cruzar dos tablas",
    learning_objectives=(
        "Explicar por qué los datos viven repartidos en varias tablas.",
        "Unir dos tablas con JOIN … ON usando su clave foránea.",
        "Predecir cuántas filas conserva un INNER JOIN.",
    ),
    difficulty=DifficultyLevel.MEDIUM,
    estimated_minutes=11,
    lecciones=(
        LeccionSemilla(
            code="m3-t1-l1",
            position=1,
            title="El puente entre dos salones",
            summary=(
                "Cómo enlazar dos tablas por su clave foránea y por qué el JOIN interno "
                "deja fuera lo que no encuentra pareja."
            ),
            estimated_seconds=660,
            bloques=(
                BloqueSemilla(
                    position=1,
                    block_type=LessonBlockType.EXPLANATION,
                    body=(
                        "La tabla `caballeros` no guarda el nombre de su reino: guarda un "
                        "`reino_id`. Eso no es pereza, es diseño. Si el nombre estuviera "
                        "repetido en cada caballero, renombrar un reino obligaría a "
                        "corregir ocho filas y bastaría un despiste para tener dos "
                        "versiones del mismo reino.\n\n"
                        "Esa columna que apunta a otra tabla es una **clave foránea**, y "
                        "el puente que vuelve a juntar la información es el **`JOIN`**:\n\n"
                        "```\n"
                        "FROM caballeros c\n"
                        "JOIN reinos r ON c.reino_id = r.id\n"
                        "```\n\n"
                        "El `ON` es la condición de unión: para cada caballero, busca el "
                        "reino cuyo `id` coincide con su `reino_id`. Los alias `c` y `r` "
                        "evitan escribir el nombre completo de la tabla y, sobre todo, "
                        "permiten distinguir `c.nombre` de `r.nombre`.\n\n"
                        "`JOIN` (o `INNER JOIN`, que es lo mismo) conserva **solo las "
                        "filas que encuentran pareja**. Un caballero sin reino y un reino "
                        "sin caballeros desaparecen del resultado. No es un fallo: es la "
                        "definición. Cuando eso no es lo que quieres, necesitas el "
                        "`LEFT JOIN` del tema siguiente."
                    ),
                ),
                BloqueSemilla(
                    position=2,
                    block_type=LessonBlockType.CODE_EXAMPLE,
                    body=(
                        "-- Cada caballero junto al nombre de su reino\n"
                        "SELECT c.nombre AS caballero,\n"
                        "       r.nombre AS reino,\n"
                        "       c.victorias\n"
                        "FROM caballeros c\n"
                        "JOIN reinos r ON c.reino_id = r.id\n"
                        "ORDER BY r.nombre, c.victorias DESC;\n\n"
                        "-- Un JOIN se puede filtrar y agrupar como cualquier consulta\n"
                        "SELECT r.region, COUNT(*) AS caballeros\n"
                        "FROM caballeros c\n"
                        "JOIN reinos r ON c.reino_id = r.id\n"
                        "GROUP BY r.region;"
                    ),
                    payload={"language": "sql"},
                ),
                BloqueSemilla(
                    position=3,
                    block_type=LessonBlockType.EXAMPLE,
                    body=(
                        "La primera consulta devuelve **7 filas**, no 8: Hilde, la "
                        "errante, tiene `reino_id` nulo y no encuentra pareja.\n\n"
                        "| caballero | reino | victorias |\n"
                        "|---|---|---|\n"
                        "| Corvin | Marlen | 9 |\n"
                        "| Dalia | Marlen | 7 |\n"
                        "| Edric | Ostgard | 15 |\n"
                        "| Fiora | Ostgard | 2 |\n"
                        "| Aldric | Valdoria | 12 |\n"
                        "| Garen | Valdoria | 6 |\n"
                        "| Brenna | Valdoria | 3 |\n\n"
                        "Selvana tampoco aparece: es un reino sin caballeros. Y si "
                        "olvidaras el `ON`, la base de datos cruzaría cada caballero con "
                        "cada reino y devolvería 32 filas sin sentido. Cuando un "
                        "resultado tiene muchas más filas de las esperadas, sospecha "
                        "siempre de la condición de unión."
                    ),
                ),
                BloqueSemilla(
                    position=4,
                    block_type=LessonBlockType.INLINE_QUESTION,
                    question_code="m3-t1-q1",
                ),
                BloqueSemilla(
                    position=5,
                    block_type=LessonBlockType.SUMMARY,
                    body=(
                        "- Una clave foránea apunta de una tabla a otra; el `JOIN` las vuelve a juntar.\n"
                        "- El `ON` dice qué columnas deben coincidir.\n"
                        "- `JOIN` = `INNER JOIN`: conserva solo las filas con pareja.\n"
                        "- Sin `ON`, el resultado se multiplica: revisa siempre el número de filas."
                    ),
                ),
            ),
            coverage_report=(
                {
                    "objective": "Explicar por qué los datos viven repartidos en varias tablas.",
                    "status": "full",
                },
                {"objective": "Unir dos tablas con JOIN … ON usando su clave foránea.", "status": "full"},
                {"objective": "Predecir cuántas filas conserva un INNER JOIN.", "status": "full"},
            ),
        ),
    ),
    preguntas=_M3T1_PREGUNTAS,
)


_M3T2_PREGUNTAS: tuple[PreguntaSemilla, ...] = (
    PreguntaSemilla(
        code="m3-t2-q1",
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=DifficultyLevel.HARD,
        stem=(
            "En `SELECT r.nombre, COUNT(c.id) FROM reinos r LEFT JOIN caballeros c ON "
            "c.reino_id = r.id GROUP BY r.nombre`, ¿qué valor sale para Selvana, que no "
            "tiene caballeros?"
        ),
        body={
            "options": [
                {"key": "a", "text": "0, porque COUNT(c.id) no cuenta los NULL."},
                {"key": "b", "text": "1, porque hay una fila con los datos de Selvana."},
                {"key": "c", "text": "NULL, porque no hay caballeros que contar."},
                {"key": "d", "text": "Selvana no aparece en el resultado."},
            ]
        },
        answer_key={"correct_option": "a", "correct_option_id": "a"},
        explanation=(
            "El `LEFT JOIN` conserva Selvana y le rellena las columnas de `caballeros` "
            "con `NULL`. Esa fila existe, por eso no es la opción (d). `COUNT(c.id)` "
            "ignora los nulos y devuelve **0**. Si se hubiera escrito `COUNT(*)` "
            "devolvería 1, contando la propia fila rellenada: ese es exactamente el "
            "error que convierte un «reino vacío» en un «reino con un caballero»."
        ),
        learning_objective="Contar correctamente el lado nulo de un LEFT JOIN.",
        estimated_seconds=90,
        inline=True,
    ),
    PreguntaSemilla(
        code="m3-t2-q2",
        question_type=QuestionType.TRUE_FALSE,
        difficulty=DifficultyLevel.HARD,
        stem="Decide si la afirmación es verdadera o falsa.",
        body={
            "statement": (
                "Añadir `WHERE c.rango = 'capitan'` a un LEFT JOIN mantiene igualmente "
                "las filas de los reinos que no tienen ningún capitán."
            )
        },
        answer_key={"correct": False, "answer": False},
        explanation=(
            "Falso. El `WHERE` se aplica **después** de la unión, y en las filas "
            "rellenadas `c.rango` vale `NULL`, que no cumple la condición: esos reinos "
            "desaparecen y el `LEFT JOIN` acaba comportándose como un `INNER JOIN`. Si "
            "quieres conservarlos, la condición va en el `ON` (`LEFT JOIN caballeros c "
            "ON c.reino_id = r.id AND c.rango = 'capitan'`)."
        ),
        learning_objective="Distinguir una condición en el ON de una condición en el WHERE.",
        estimated_seconds=60,
    ),
    PreguntaSemilla(
        code="m3-t2-q3",
        question_type=QuestionType.OPEN_SHORT,
        difficulty=DifficultyLevel.HARD,
        stem=(
            "El Reino quiere un informe con todos los reinos, incluidos los que aún no "
            "tienen caballeros. Explica en dos o tres frases qué tipo de JOIN usarías y "
            "qué precaución hay que tomar al contar."
        ),
        body={
            "rubric": {
                "criteria": [
                    {"key": "tipo", "text": "Elige LEFT JOIN con reinos como tabla izquierda."},
                    {
                        "key": "nulos",
                        "text": "Menciona que las columnas del lado derecho quedan en NULL.",
                    },
                    {
                        "key": "conteo",
                        "text": "Advierte de usar COUNT(columna_derecha) y no COUNT(*).",
                    },
                ],
                "max_words": 90,
            }
        },
        answer_key={
            "reference_answer": (
                "Usaría un LEFT JOIN partiendo de reinos, para conservar todos los reinos "
                "aunque no casen con ningún caballero. En esas filas las columnas de "
                "caballeros quedan en NULL, así que para contar hay que usar "
                "COUNT(c.id) y no COUNT(*): COUNT(*) contaría la fila rellenada y daría 1 "
                "donde debería dar 0."
            ),
            "key_points": [
                "LEFT JOIN con reinos a la izquierda",
                "las columnas del lado derecho quedan en NULL",
                "COUNT(c.id) en lugar de COUNT(*)",
            ],
        },
        explanation=(
            "Las tres ideas que debe contener la respuesta son: `LEFT JOIN` desde la "
            "tabla que se quiere conservar, relleno con `NULL` en el lado sin pareja, y "
            "`COUNT` sobre una columna del lado derecho para que los grupos vacíos den 0."
        ),
        learning_objective="Justificar la elección de LEFT JOIN y su efecto al agregar.",
        estimated_seconds=180,
    ),
    PreguntaSemilla(
        code="m3-t2-q4",
        question_type=QuestionType.SQL_EXERCISE,
        difficulty=DifficultyLevel.HARD,
        stem=(
            "Cierra la crónica del Reino: devuelve el **nombre de cada reino** y "
            "**cuántos caballeros** tiene (columna `caballeros`), incluyendo los reinos "
            "que no tienen ninguno, que deben aparecer con 0."
        ),
        body=cuerpo_sql(),
        answer_key={
            "reference_sql": (
                "SELECT r.nombre, COUNT(c.id) AS caballeros "
                "FROM reinos r LEFT JOIN caballeros c ON c.reino_id = r.id "
                "GROUP BY r.nombre"
            )
        },
        explanation=(
            "Tres decisiones encadenadas: `reinos` va a la izquierda porque es la tabla "
            "que hay que conservar entera; `LEFT JOIN` mantiene a Selvana; y "
            "`COUNT(c.id)` —no `COUNT(*)`— hace que Selvana salga con 0 en lugar de con "
            "1. El resultado es Valdoria 3, Marlen 2, Ostgard 2 y Selvana 0. Hilde no "
            "aparece por ningún lado: no tiene reino, y el informe es de reinos."
        ),
        learning_objective="Combinar LEFT JOIN con GROUP BY para incluir los grupos vacíos.",
        estimated_seconds=240,
    ),
)

_M3T2 = TemaSemilla(
    code="m3-t2",
    position=2,
    title="LEFT JOIN y los NULL: conservar lo que no casa",
    learning_objectives=(
        "Elegir LEFT JOIN cuando hay que conservar filas sin pareja.",
        "Interpretar los NULL que aparecen en el lado sin coincidencia.",
        "Contar correctamente grupos vacíos combinando LEFT JOIN y GROUP BY.",
    ),
    difficulty=DifficultyLevel.HARD,
    estimated_minutes=12,
    lecciones=(
        LeccionSemilla(
            code="m3-t2-l1",
            position=1,
            title="Nadie se queda fuera del puente",
            summary=(
                "Cuándo el JOIN interno miente por omisión, cómo conservar todas las "
                "filas con LEFT JOIN y qué cambia al contar."
            ),
            estimated_seconds=720,
            bloques=(
                BloqueSemilla(
                    position=1,
                    block_type=LessonBlockType.EXPLANATION,
                    body=(
                        "El `INNER JOIN` responde «qué caballeros sirven a qué reino». No "
                        "responde «qué reinos existen», porque los reinos sin caballeros "
                        "se caen del resultado sin avisar. Un informe así no da error: da "
                        "una foto incompleta, que es peor.\n\n"
                        "El **`LEFT JOIN`** conserva **todas** las filas de la tabla de la "
                        "izquierda (la del `FROM`) y, cuando no encuentra pareja a la "
                        "derecha, rellena esas columnas con `NULL`.\n\n"
                        "De ahí se derivan dos consecuencias prácticas:\n\n"
                        "1. **Al contar**, usa una columna del lado derecho: `COUNT(c.id)` "
                        "da 0 para los grupos vacíos, mientras que `COUNT(*)` da 1 porque "
                        "cuenta la fila rellenada.\n"
                        "2. **Al filtrar**, una condición sobre el lado derecho puesta en "
                        "`WHERE` elimina las filas rellenadas y convierte tu `LEFT JOIN` "
                        "en un `INNER JOIN` sin que nadie te avise. Si la condición forma "
                        "parte de la unión, va en el `ON`; si filtra el resultado final, "
                        "va en el `WHERE`.\n\n"
                        "Elegir el lado es una decisión de producto, no de sintaxis: "
                        "pregúntate siempre qué lista tiene que aparecer completa."
                    ),
                ),
                BloqueSemilla(
                    position=2,
                    block_type=LessonBlockType.CODE_EXAMPLE,
                    body=(
                        "-- Todos los reinos, tengan o no caballeros\n"
                        "SELECT r.nombre, COUNT(c.id) AS caballeros\n"
                        "FROM reinos r\n"
                        "LEFT JOIN caballeros c ON c.reino_id = r.id\n"
                        "GROUP BY r.nombre\n"
                        "ORDER BY caballeros DESC;\n\n"
                        "-- Solo los capitanes, sin perder los reinos que no tienen ninguno\n"
                        "SELECT r.nombre, COUNT(c.id) AS capitanes\n"
                        "FROM reinos r\n"
                        "LEFT JOIN caballeros c\n"
                        "       ON c.reino_id = r.id AND c.rango = 'capitan'\n"
                        "GROUP BY r.nombre;"
                    ),
                    payload={"language": "sql"},
                ),
                BloqueSemilla(
                    position=3,
                    block_type=LessonBlockType.EXAMPLE,
                    body=(
                        "La primera consulta devuelve las cuatro filas que el informe "
                        "necesita:\n\n"
                        "| nombre | caballeros |\n"
                        "|---|---|\n"
                        "| Valdoria | 3 |\n"
                        "| Marlen | 2 |\n"
                        "| Ostgard | 2 |\n"
                        "| Selvana | 0 |\n\n"
                        "Con `COUNT(*)` en lugar de `COUNT(c.id)`, Selvana habría salido "
                        "con 1 caballero inexistente.\n\n"
                        "La segunda consulta pone la condición del rango en el `ON`: "
                        "Valdoria 1, Marlen 1, Ostgard 0 y Selvana 0. Si esa misma "
                        "condición se hubiera escrito en el `WHERE`, Ostgard y Selvana "
                        "habrían desaparecido y el informe diría que solo dos reinos "
                        "existen. Misma intención, dos sitios, resultados distintos."
                    ),
                ),
                BloqueSemilla(
                    position=4,
                    block_type=LessonBlockType.INLINE_QUESTION,
                    question_code="m3-t2-q1",
                ),
                BloqueSemilla(
                    position=5,
                    block_type=LessonBlockType.SUMMARY,
                    body=(
                        "- `LEFT JOIN` conserva toda la tabla izquierda y rellena con `NULL`.\n"
                        "- Para contar grupos vacíos usa `COUNT(columna_derecha)`, no `COUNT(*)`.\n"
                        "- Una condición del lado derecho en el `WHERE` anula el `LEFT JOIN`.\n"
                        "- Elegir el lado izquierdo es decidir qué lista debe salir completa."
                    ),
                ),
            ),
            coverage_report=(
                {
                    "objective": "Elegir LEFT JOIN cuando hay que conservar filas sin pareja.",
                    "status": "full",
                },
                {
                    "objective": "Interpretar los NULL que aparecen en el lado sin coincidencia.",
                    "status": "full",
                },
                {
                    "objective": "Contar correctamente grupos vacíos combinando LEFT JOIN y GROUP BY.",
                    "status": "full",
                },
            ),
        ),
    ),
    preguntas=_M3T2_PREGUNTAS,
)


_MODULO_3 = ModuloSemilla(
    code="m3",
    position=3,
    title="Unir tablas",
    flavor_name="Puente de las Uniones",
    summary=(
        "Los datos del Reino viven repartidos en varios salones. Este puente los "
        "reúne: JOIN para cruzar lo que casa y LEFT JOIN para no perder a nadie."
    ),
    difficulty=DifficultyLevel.HARD,
    estimated_minutes=30,
    temas=(_M3T1, _M3T2),
    assessment_title="Prueba del Puente de las Uniones",
    assessment_question_count=6,
)


# ---------------------------------------------------------------------------
# La ruta completa
# ---------------------------------------------------------------------------

RUTA = RutaSemilla(
    code="ruta_sql_reino",
    area_slug="sql",
    title="El Castillo de las Consultas: SQL desde cero",
    goal_text=(
        "Quiero aprender SQL desde cero para consultar una base de datos por mi cuenta: "
        "pedir datos, filtrarlos, resumirlos y cruzar tablas."
    ),
    summary=(
        "Tres módulos para pasar de no haber escrito nunca una consulta a responder "
        "preguntas reales sobre dos tablas. Empiezas pidiendo columnas y filtrando "
        "filas, sigues resumiendo por categorías con GROUP BY y terminas uniendo tablas "
        "con JOIN y LEFT JOIN, incluidos los casos con valores nulos que arruinan la "
        "mitad de los informes del mundo. Todo se practica en un sandbox real: escribes "
        "la consulta y el Castillo la ejecuta."
    ),
    declared_level=DeclaredLevel.BEGINNER,
    estimated_minutes=83,
    modulos=(_MODULO_1, _MODULO_2, _MODULO_3),
)


def preguntas_de_modulo(modulo: ModuloSemilla) -> list[PreguntaSemilla]:
    """Pool completo de un módulo: es también el banco de su evaluación."""
    return [pregunta for tema in modulo.temas for pregunta in tema.preguntas]


def todas_las_preguntas() -> list[PreguntaSemilla]:
    """Las 24 preguntas de la ruta, en el orden en que se siembran."""
    return [pregunta for modulo in RUTA.modulos for pregunta in preguntas_de_modulo(modulo)]


def banco_de_evaluacion(modulo: ModuloSemilla) -> list[PreguntaSemilla]:
    """Banco de la evaluación del módulo: todo el pool **menos** las preguntas abiertas.

    La Ruta del Reino tiene que poder completarse entera **sin IA** (contrato §9): las
    `open_short` las corrige el juez de Claude, así que se quedan en la lección, donde
    enriquecen el aprendizaje, y fuera de la prueba, que debe puntuar de forma
    determinista con los correctores de `app.modules.content.correccion` y el sandbox
    DuckDB de `app.modules.ai.sandbox_sql`.
    """
    return [
        pregunta
        for pregunta in preguntas_de_modulo(modulo)
        if pregunta.question_type is not QuestionType.OPEN_SHORT
    ]
