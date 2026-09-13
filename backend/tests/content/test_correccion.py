"""Corrección determinista de cada tipo admitido y sus tolerancias (§7.6, §6.4).

Ninguna de estas pruebas toca la base de datos ni llama a una IA: los cinco tipos
cerrados del MVP se corrigen con aritmética y comparación de texto.
"""

from __future__ import annotations

import pytest

from app.models.content import Question
from app.models.enums import AttemptResult, DifficultyLevel, EvaluationMethod, QuestionType
from app.modules.content import correccion


def _pregunta(tipo: QuestionType, answer_key: dict, body: dict | None = None) -> Question:
    """Pregunta en memoria (sin persistir): basta para la corrección pura."""
    return Question(
        question_type=tipo,
        difficulty=DifficultyLevel.MEDIUM,
        stem="Enunciado de prueba",
        body=body or {},
        answer_key=answer_key,
        explanation="Explicación de prueba",
    )


# ---------------------------------------------------------------------------
# Normalización de texto
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("  INNER   JOIN ", "inner join"),
        ("Inner Jóin", "inner join"),
        ("ÍNNER JOIN", "inner join"),
        ("inner\tjoin", "inner join"),
        (None, ""),
    ],
)
def test_normalizar_texto_tolera_acentos_mayusculas_y_espacios(entrada, esperado):
    """La tolerancia de `fill_blank` es exactamente la que pide §7.6."""
    assert correccion.normalizar_texto(entrada) == esperado


# ---------------------------------------------------------------------------
# Selección múltiple
# ---------------------------------------------------------------------------


def test_multiple_choice_acierto(cfg_falso):
    """La opción correcta da 100 y resultado `CORRECT`."""
    pregunta = _pregunta(QuestionType.MULTIPLE_CHOICE, {"correct_option_id": "b"})

    veredicto = correccion.corregir(cfg_falso, pregunta, {"option_id": "b"})

    assert veredicto.is_correct is True
    assert veredicto.partial_score == 100.0
    assert veredicto.result == AttemptResult.CORRECT
    assert veredicto.evaluation_method == EvaluationMethod.DETERMINISTIC
    assert veredicto.explanation == "Explicación de prueba"


def test_multiple_choice_error_no_da_credito_parcial(cfg_falso):
    """Con clave única no hay medias tintas: o es esa opción o es 0."""
    pregunta = _pregunta(QuestionType.MULTIPLE_CHOICE, {"correct_option_id": "b"})

    veredicto = correccion.corregir(cfg_falso, pregunta, {"option_id": "a"})

    assert veredicto.is_correct is False
    assert veredicto.partial_score == 0.0
    assert veredicto.result == AttemptResult.INCORRECT


def test_multiple_choice_multiple_penaliza_las_opciones_de_mas(cfg_falso):
    """Marcar todo no puntúa: cada opción errónea anula un acierto."""
    pregunta = _pregunta(QuestionType.MULTIPLE_CHOICE, {"correct_option_ids": ["a", "b"]})

    parcial = correccion.corregir(cfg_falso, pregunta, {"option_ids": ["a"]})
    todas = correccion.corregir(cfg_falso, pregunta, {"option_ids": ["a", "b", "c", "d"]})

    assert parcial.partial_score == 50.0
    assert parcial.result == AttemptResult.PARTIAL
    assert todas.partial_score == 0.0


# ---------------------------------------------------------------------------
# Verdadero / falso
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("respuesta", [True, "true", "Verdadero", "V", 1])
def test_true_false_lee_el_booleano_en_varias_formas(cfg_falso, respuesta):
    """El cliente puede mandar el booleano como texto o como número."""
    pregunta = _pregunta(QuestionType.TRUE_FALSE, {"answer": True})

    veredicto = correccion.corregir(cfg_falso, pregunta, {"value": respuesta})

    assert veredicto.is_correct is True
    assert veredicto.partial_score == 100.0


def test_true_false_falla_sin_credito_parcial(cfg_falso):
    """Verdadero/falso nunca da crédito parcial."""
    pregunta = _pregunta(QuestionType.TRUE_FALSE, {"answer": False})

    veredicto = correccion.corregir(cfg_falso, pregunta, {"value": True})

    assert veredicto.is_correct is False
    assert veredicto.partial_score == 0.0


# ---------------------------------------------------------------------------
# Completar huecos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "respuesta",
    ["INNER JOIN", "inner join", "  Inner   Join  ", "ínner jóin", "join interno"],
)
def test_fill_blank_tolera_acentos_mayusculas_y_espacios(cfg_falso, respuesta):
    """Las cinco formas son la misma respuesta para el corrector (§7.6)."""
    pregunta = _pregunta(
        QuestionType.FILL_BLANK,
        {"blanks": [{"accepted": ["INNER JOIN", "join interno"]}]},
    )

    veredicto = correccion.corregir(cfg_falso, pregunta, {"blanks": [respuesta]})

    assert veredicto.is_correct is True
    assert veredicto.partial_score == 100.0


def test_fill_blank_da_credito_parcial_por_hueco(cfg_falso):
    """Dos huecos, uno acertado: 50 % y resultado `PARTIAL`."""
    pregunta = _pregunta(
        QuestionType.FILL_BLANK,
        {"blanks": [{"accepted": ["inner"]}, {"accepted": ["outer"]}]},
    )

    veredicto = correccion.corregir(cfg_falso, pregunta, {"blanks": ["inner", "cross"]})

    assert veredicto.is_correct is False
    assert veredicto.partial_score == 50.0
    assert veredicto.result == AttemptResult.PARTIAL


# ---------------------------------------------------------------------------
# Relacionar
# ---------------------------------------------------------------------------


def test_matching_credito_parcial_por_pareja(cfg_falso):
    """Cuatro parejas, tres correctas: 75 %."""
    pregunta = _pregunta(
        QuestionType.MATCHING, {"pairs": {"1": "a", "2": "b", "3": "c", "4": "d"}}
    )

    veredicto = correccion.corregir(
        cfg_falso, pregunta, {"pairs": {"1": "a", "2": "b", "3": "c", "4": "a"}}
    )

    assert veredicto.partial_score == 75.0
    assert veredicto.result == AttemptResult.PARTIAL


def test_matching_admite_lista_de_pares(cfg_falso):
    """La clave y la respuesta pueden venir como lista de pares."""
    pregunta = _pregunta(QuestionType.MATCHING, {"pairs": [["1", "a"], ["2", "b"]]})

    veredicto = correccion.corregir(cfg_falso, pregunta, {"pairs": [["1", "a"], ["2", "b"]]})

    assert veredicto.is_correct is True


# ---------------------------------------------------------------------------
# Ordenar
# ---------------------------------------------------------------------------


def test_ordering_acierto_total(cfg_falso):
    """La secuencia exacta da 100."""
    pregunta = _pregunta(QuestionType.ORDERING, {"order": ["a", "b", "c"]})

    veredicto = correccion.corregir(cfg_falso, pregunta, {"order": ["a", "b", "c"]})

    assert veredicto.is_correct is True
    assert veredicto.partial_score == 100.0


def test_ordering_credito_parcial_por_posicion(cfg_falso):
    """Tres elementos con uno en su sitio: 33,33 %."""
    pregunta = _pregunta(QuestionType.ORDERING, {"order": ["a", "b", "c"]})

    veredicto = correccion.corregir(cfg_falso, pregunta, {"order": ["a", "c", "b"]})

    assert veredicto.partial_score == pytest.approx(33.33)
    assert veredicto.result == AttemptResult.PARTIAL


# ---------------------------------------------------------------------------
# Casos transversales
# ---------------------------------------------------------------------------


def test_respuesta_vacia_se_registra_como_omitida(cfg_falso):
    """No responder es `SKIPPED`, no un error: no gasta ninguna llamada de IA."""
    pregunta = _pregunta(QuestionType.MULTIPLE_CHOICE, {"correct_option_id": "a"})

    veredicto = correccion.corregir(cfg_falso, pregunta, {})

    assert veredicto.result == AttemptResult.SKIPPED
    assert veredicto.is_correct is False
    assert veredicto.correctness_weight == 0.0


def test_peso_de_acierto_sigue_la_formula_de_dominio(cfg_falso):
    """`c_i` = 1.0 al primer intento, 0.5 al segundo y 0.0 del tercero en adelante (§6.4)."""
    assert correccion.peso_de_acierto(cfg_falso, is_correct=True, attempt_no=1) == 1.0
    assert correccion.peso_de_acierto(cfg_falso, is_correct=True, attempt_no=2) == 0.5
    assert correccion.peso_de_acierto(cfg_falso, is_correct=True, attempt_no=3) == 0.0
    assert correccion.peso_de_acierto(cfg_falso, is_correct=False, attempt_no=1) == 0.0


def test_credito_parcial_no_aporta_dominio(cfg_falso):
    """§6.4: el «casi» puede pagar XP reducido, pero cuenta 0 para el dominio."""
    pregunta = _pregunta(QuestionType.ORDERING, {"order": ["a", "b", "c"]})

    veredicto = correccion.corregir(cfg_falso, pregunta, {"order": ["a", "c", "b"]})

    assert veredicto.partial_score > 0
    assert veredicto.correctness_weight == 0.0


def test_respuesta_abierta_sin_juez_queda_pendiente(cfg_falso):
    """Sin el módulo `ai` no se inventa veredicto: `NEEDS_REVIEW` y sin dominio."""
    pregunta = _pregunta(QuestionType.OPEN_SHORT, {"rubric": ["menciona claves foráneas"]})

    veredicto = correccion.corregir(
        cfg_falso, pregunta, {"text": "Une dos tablas por su clave foránea"}
    )

    assert veredicto.result == AttemptResult.NEEDS_REVIEW
    assert veredicto.evaluation_method == EvaluationMethod.PENDING
    assert veredicto.counts_for_mastery is False


def test_respuesta_abierta_demasiado_corta_no_llega_al_juez(cfg_falso):
    """`ai.judge.min_words` evita pagar una llamada por un «no sé»."""
    pregunta = _pregunta(QuestionType.OPEN_SHORT, {"rubric": []})

    veredicto = correccion.corregir(cfg_falso, pregunta, {"text": "no sé"})

    assert veredicto.result == AttemptResult.INCORRECT
    assert veredicto.evaluation_method == EvaluationMethod.DETERMINISTIC


def test_el_ejercicio_sql_se_corrige_de_verdad(cfg_falso):
    """El sandbox tiene que **ejecutarse**, no quedarse en pendiente.

    Esta prueba afirmaba lo contrario: daba por buena la respuesta pendiente
    "porque no hay sandbox". El sandbox existía desde hacía tiempo; lo que
    fallaba era el puente, que importaba el módulo `sandbox` cuando se llama
    `sandbox_sql`. La prueba consagraba el fallo, así que ahora exige lo que
    debe pasar: que el veredicto venga del sandbox y cuente para el dominio.
    """
    pregunta = _pregunta(
        QuestionType.SQL_EXERCISE,
        {"reference_sql": "SELECT nombre FROM reinos"},
        {
            "schema_sql": "CREATE TABLE reinos(nombre TEXT)",
            "seed_data": ["INSERT INTO reinos VALUES ('Atenea')"],
        },
    )

    acierto = correccion.corregir(cfg_falso, pregunta, {"sql": "SELECT nombre FROM reinos"})
    fallo = correccion.corregir(cfg_falso, pregunta, {"sql": "SELECT 1"})

    assert acierto.evaluation_method == EvaluationMethod.SANDBOX
    assert acierto.is_correct is True
    assert acierto.counts_for_mastery is True
    assert fallo.evaluation_method == EvaluationMethod.SANDBOX
    assert fallo.is_correct is False


def test_el_puente_del_juez_apunta_a_una_funcion_que_existe(cfg_falso):
    """El fallo histórico fue un `getattr` a un nombre inexistente.

    No se comprueba el veredicto, que necesita base de datos y proveedor, sino
    que el puente **encuentra** algo al otro lado. Un `None` aquí significa que
    ninguna respuesta abierta ni ningún SQL se calificarán jamás, en silencio.
    """
    assert correccion._juez_disponible() is not None
    assert correccion._sandbox_disponible() is not None


# ---------------------------------------------------------------------------
# Degradación: lo que pasa cuando el juez o el sandbox no pueden responder
# ---------------------------------------------------------------------------
#
# Conectar los dos puentes al módulo `ai` fue un arreglo, pero abrió un camino
# nuevo: ahora la corrección de una respuesta abierta puede fallar por cuota
# agotada, por un proveedor caído o por un catálogo mal generado. Ninguna de esas
# cosas es culpa del aprendiz, y ninguna puede costarle la respuesta que acaba de
# escribir ni hundirle el dominio del tema.


class _JuezQueRevienta:
    """Sustituto del juez que falla como fallaría la cuota agotada."""

    def __call__(self, *args, **kwargs):
        raise RuntimeError("cuota agotada")


def test_si_el_juez_falla_la_respuesta_queda_pendiente_y_no_se_pierde(
    cfg_falso, monkeypatch
) -> None:
    """Un 429 o un proveedor caído no pueden tumbar el envío de la respuesta.

    Si la excepción escapara, el intento no se escribiría, la pregunta quedaría
    sin contestar y la lección no se podría cerrar.
    """
    monkeypatch.setattr(correccion, "_juez_disponible", lambda: _JuezQueRevienta())
    monkeypatch.setattr(correccion, "_proveedor_disponible", lambda cfg: object())  # noqa: ARG005 - firma fijada por el sustituto
    pregunta = _pregunta(QuestionType.OPEN_SHORT, {"rubric": ["menciona claves foráneas"]})

    veredicto = correccion.corregir(
        cfg_falso,
        pregunta,
        {"text": "Una clave foránea enlaza la fila de una tabla con la de otra tabla."},
        db=object(),
    )

    assert veredicto.result == AttemptResult.NEEDS_REVIEW
    assert veredicto.evaluation_method == EvaluationMethod.PENDING
    assert veredicto.counts_for_mastery is False


def test_un_veredicto_pendiente_no_cuenta_para_el_dominio(cfg_falso, monkeypatch) -> None:
    """Sin presupuesto de IA el juez devuelve `PENDING`: eso no es un cero.

    Contarlo hundiría el dominio de quien respondió bien el día que se agote el
    presupuesto, y le sugeriría repasos que no necesita (§3.4).
    """

    class _VeredictoPendiente:
        result = AttemptResult.NEEDS_REVIEW
        is_correct = False
        partial_score = 0.0
        confidence = 0.0
        evaluation_method = EvaluationMethod.PENDING
        feedback = "Guardamos tu respuesta: la corregimos en cuanto podamos."

        def como_dict(self) -> dict:
            return {"reason": "ai_budget_exceeded"}

    monkeypatch.setattr(
        correccion, "_juez_disponible", lambda: lambda *a, **k: _VeredictoPendiente()  # noqa: ARG005 - firma fijada por el sustituto
    )
    monkeypatch.setattr(correccion, "_proveedor_disponible", lambda cfg: object())  # noqa: ARG005 - firma fijada por el sustituto
    pregunta = _pregunta(QuestionType.OPEN_SHORT, {"rubric": ["define índice"]})

    veredicto = correccion.corregir(
        cfg_falso,
        pregunta,
        {"text": "Un índice acelera la búsqueda a cambio de ocupar espacio en disco."},
        db=object(),
    )

    assert veredicto.evaluation_method == EvaluationMethod.PENDING
    assert veredicto.counts_for_mastery is False
    assert veredicto.correctness_weight == 0.0


def test_un_ejercicio_sql_con_el_catalogo_roto_no_lo_paga_el_aprendiz(
    cfg_falso, monkeypatch
) -> None:
    """Un `CREATE TABLE` con un tipo inventado revienta DuckDB, no al alumno."""

    def _revienta(*args, **kwargs):
        raise RuntimeError("Type with name TEXTO does not exist")

    monkeypatch.setattr(correccion, "_sandbox_disponible", lambda: _revienta)
    pregunta = _pregunta(
        QuestionType.SQL_EXERCISE,
        {"reference_sql": "SELECT 1"},
        {"schema_sql": "CREATE TABLE reinos(nombre TEXTO)"},
    )

    veredicto = correccion.corregir(cfg_falso, pregunta, {"sql": "SELECT 1"})

    assert veredicto.result == AttemptResult.NEEDS_REVIEW
    assert veredicto.evaluation_method == EvaluationMethod.PENDING
    assert veredicto.counts_for_mastery is False


def test_un_ejercicio_sin_consulta_de_referencia_queda_pendiente(cfg_falso) -> None:
    """Sin consulta de referencia no hay con qué comparar: es fallo del catálogo."""
    pregunta = _pregunta(
        QuestionType.SQL_EXERCISE,
        {},
        {"schema_sql": "CREATE TABLE reinos(nombre TEXT)"},
    )

    veredicto = correccion.corregir(cfg_falso, pregunta, {"sql": "SELECT 1"})

    assert veredicto.evaluation_method == EvaluationMethod.PENDING
    assert veredicto.counts_for_mastery is False


def test_la_clave_que_escribe_el_generador_tambien_se_corrige(cfg_falso) -> None:
    """El generador emite `correct_option`; el corrector tiene que leerlo.

    Mientras no lo leía, la clave salía vacía y **toda** pregunta de selección
    múltiple escrita por la IA puntuaba cero, acertara el aprendiz o no. Solo
    funcionaban las de la Ruta semilla, que usan `correct_option_ids`.
    """
    pregunta = _pregunta(
        QuestionType.MULTIPLE_CHOICE,
        {"correct_option": "b"},
        {"options": [{"key": "a", "text": "No"}, {"key": "b", "text": "Sí"}]},
    )

    acierto = correccion.corregir(cfg_falso, pregunta, {"option_ids": ["b"]})
    fallo = correccion.corregir(cfg_falso, pregunta, {"option_ids": ["a"]})

    assert acierto.is_correct is True
    assert acierto.partial_score == 100.0
    assert fallo.is_correct is False
