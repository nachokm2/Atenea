"""Corrección de respuestas: determinista, sandbox o juez de IA.

Contrato §2 (`QuestionType`, `AttemptResult`, `EvaluationMethod`), §5.8 (`ai.judge`,
`ai.sql_sandbox`), §6.4 (peso de acierto `c_i`) y §7.6 (`AnswerResultOut`).

**Cinco tipos se corrigen sin IA y sin coste**, y esa es la ruta por defecto:

| Tipo | Regla | Crédito parcial |
|---|---|---|
| `multiple_choice` | opción(es) elegida(s) contra la clave | sí, si la clave es múltiple |
| `true_false` | booleano contra la clave | no |
| `fill_blank` | texto normalizado (acentos, mayúsculas y espacios) | sí, por hueco |
| `matching` | parejas contra la clave | sí, por pareja |
| `ordering` | posiciones correctas | sí, por posición |

`open_short` se delega al **juez de IA** y `sql_exercise` al **sandbox DuckDB**; ambos
viven en el módulo `ai`. Mientras ese módulo no esté disponible, la respuesta se
registra como `NEEDS_REVIEW` con `evaluation_method = PENDING` y **no cuenta para
dominio** (§3.4, `question_attempts.counts_for_mastery`): jamás se inventa un veredicto.

**El crédito parcial no es dominio.** §6.4 es explícito: `c_i` vale 1.0 si se acierta
al primer intento, 0.5 si se acierta al segundo y 0.0 en cualquier otro caso; el
"casi" puede pagar XP reducido pero cuenta 0 para el dominio del tema.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.models.content import Question
from app.models.enums import AttemptResult, EvaluationMethod, QuestionType
from app.core.logging import get_logger
from app.modules.gamification.servicio_config import ServicioConfig

logger = get_logger("atenea.content")

#: Códigos del sandbox que señalan un ejercicio mal generado, no una respuesta
#: equivocada. No cuentan para el dominio del aprendiz.
CULPA_DEL_CATALOGO: frozenset[str] = frozenset({"missing_reference", "broken_setup"})

#: Tipos que el MVP corrige de forma determinista, sin llamar a ninguna IA.
TIPOS_DETERMINISTAS: frozenset[QuestionType] = frozenset(
    {
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.TRUE_FALSE,
        QuestionType.FILL_BLANK,
        QuestionType.MATCHING,
        QuestionType.ORDERING,
    }
)

#: Tipos reservados para fases posteriores: el validador de contenido los rechaza (§2).
TIPOS_RESERVADOS: frozenset[QuestionType] = frozenset(
    {QuestionType.CASE_STUDY, QuestionType.CODE_EXERCISE}
)

#: Valores textuales que se leen como «verdadero» en una pregunta de verdadero/falso.
VERDADEROS: frozenset[str] = frozenset({"true", "verdadero", "v", "si", "sí", "1"})
#: Valores textuales que se leen como «falso».
FALSOS: frozenset[str] = frozenset({"false", "falso", "f", "no", "0"})


@dataclass(frozen=True, slots=True)
class ResultadoCorreccion:
    """Veredicto de una respuesta, tal como lo consume `AnswerResultOut` (§7.6)."""

    result: AttemptResult
    is_correct: bool
    partial_score: float
    correctness_weight: float
    evaluation_method: EvaluationMethod
    correct_answer: Any | None = None
    explanation: str | None = None
    judge_confidence: float | None = None
    judge_payload: dict[str, Any] = field(default_factory=dict)
    counts_for_mastery: bool = True


# ---------------------------------------------------------------------------
# Normalización de texto
# ---------------------------------------------------------------------------


def normalizar_texto(valor: Any) -> str:
    """Normaliza un texto para compararlo: sin acentos, sin mayúsculas, sin espacios extra.

    Es la tolerancia exacta que pide §7.6 para `fill_blank`: «acentos, mayúsculas y
    espacios». No se tocan los signos de puntuación ni el orden de las palabras.

    >>> normalizar_texto("  INNER   Jóin ")
    'inner join'
    """
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    texto = str(valor)
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_tildes.casefold().split())


def _como_lista(valor: Any) -> list[Any]:
    """Envuelve en lista lo que no lo sea; `None` produce lista vacía."""
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        return list(valor)
    return [valor]


def _primer_valor(origen: Any, claves: tuple[str, ...]) -> Any:
    """Primera clave presente de un mapa; si `origen` no es un mapa, lo devuelve tal cual."""
    if not isinstance(origen, dict):
        return origen
    for clave in claves:
        if clave in origen and origen[clave] is not None:
            return origen[clave]
    return None


def _a_booleano(valor: Any) -> bool | None:
    """Lee un booleano tolerante: `true`, `"verdadero"`, `"V"`, `1`…"""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)) and valor in (0, 1):
        return bool(valor)
    texto = normalizar_texto(valor)
    if texto in VERDADEROS:
        return True
    if texto in FALSOS:
        return False
    return None


def _parejas(valor: Any) -> dict[str, str]:
    """Normaliza parejas de `matching`: mapa, lista de pares o lista de objetos."""
    if isinstance(valor, dict):
        return {normalizar_texto(k): normalizar_texto(v) for k, v in valor.items()}
    parejas: dict[str, str] = {}
    for elemento in _como_lista(valor):
        if isinstance(elemento, dict):
            izquierda = _primer_valor(elemento, ("left", "left_id", "from", "key", "a"))
            derecha = _primer_valor(elemento, ("right", "right_id", "to", "value", "b"))
        elif isinstance(elemento, (list, tuple)) and len(elemento) == 2:
            izquierda, derecha = elemento
        else:
            continue
        parejas[normalizar_texto(izquierda)] = normalizar_texto(derecha)
    return parejas


def _porcentaje(aciertos: float, total: float) -> float:
    """Porcentaje 0–100 con dos decimales; `total = 0` da 0."""
    if total <= 0:
        return 0.0
    return round(max(0.0, min(1.0, aciertos / total)) * 100.0, 2)


# ---------------------------------------------------------------------------
# Correctores deterministas (funciones puras: no tocan la base de datos)
# ---------------------------------------------------------------------------


def corregir_multiple_choice(answer_key: dict, response: Any) -> tuple[float, Any]:
    """Selección múltiple: exacta si la clave es una opción; parcial si son varias.

    Con clave múltiple, cada opción errónea anula un acierto (evita que marcar todo
    puntúe): `score = max(0, aciertos − fallos) / |clave|`.
    """
    # `correct_option` está en la lista a propósito: es la clave que emite el
    # generador de preguntas, y sin ella toda selección múltiple escrita por la
    # IA se corregía contra una clave vacía y puntuaba cero.
    clave = _primer_valor(
        answer_key,
        (
            "correct_option_ids",
            "correct_option_id",
            "correct_option",
            "correct_options",
            "correct",
            "answer",
            "answers",
        ),
    )
    esperadas = [normalizar_texto(v) for v in _como_lista(clave) if normalizar_texto(v)]
    dadas = [
        normalizar_texto(v)
        for v in _como_lista(
            _primer_valor(response, ("option_ids", "option_id", "value", "answer", "selected"))
        )
        if normalizar_texto(v)
    ]
    if not esperadas:
        return 0.0, clave
    if len(esperadas) == 1:
        return (100.0 if dadas == esperadas else 0.0), clave

    conjunto = set(esperadas)
    aciertos = len([v for v in set(dadas) if v in conjunto])
    fallos = len([v for v in set(dadas) if v not in conjunto])
    return _porcentaje(aciertos - fallos, len(conjunto)), clave


def corregir_true_false(answer_key: dict, response: Any) -> tuple[float, Any]:
    """Verdadero/falso: sin crédito parcial."""
    esperado = _a_booleano(_primer_valor(answer_key, ("answer", "correct", "value", "is_true")))
    dado = _a_booleano(_primer_valor(response, ("value", "answer", "selected", "is_true")))
    if esperado is None:
        return 0.0, None
    return (100.0 if dado is esperado else 0.0), esperado


def corregir_fill_blank(answer_key: dict, response: Any) -> tuple[float, Any]:
    """Completar huecos: crédito parcial por hueco, con la tolerancia de `normalizar_texto`.

    La clave admite `{"blanks": [{"accepted": [...]}, ...]}`, `{"blanks": ["a", "b"]}`
    o `{"answers": [["a", "alias"], ["b"]]}`: cada hueco lleva su lista de respuestas
    aceptadas.
    """
    crudos = _como_lista(_primer_valor(answer_key, ("blanks", "answers", "correct", "answer")))
    aceptadas: list[list[str]] = []
    for hueco in crudos:
        valores = (
            _primer_valor(hueco, ("accepted", "answers", "values", "text"))
            if isinstance(hueco, dict)
            else hueco
        )
        aceptadas.append([normalizar_texto(v) for v in _como_lista(valores) if normalizar_texto(v)])
    if not aceptadas:
        return 0.0, None

    dadas = _como_lista(_primer_valor(response, ("blanks", "values", "answers", "answer", "value")))
    aciertos = 0
    for indice, opciones in enumerate(aceptadas):
        dada = normalizar_texto(dadas[indice]) if indice < len(dadas) else ""
        if dada and dada in opciones:
            aciertos += 1
    esperada = [opciones[0] if opciones else None for opciones in aceptadas]
    return _porcentaje(aciertos, len(aceptadas)), esperada


def corregir_matching(answer_key: dict, response: Any) -> tuple[float, Any]:
    """Relacionar: crédito parcial por pareja acertada."""
    esperadas = _parejas(_primer_valor(answer_key, ("pairs", "matches", "correct", "answer")))
    if not esperadas:
        return 0.0, None
    dadas = _parejas(_primer_valor(response, ("pairs", "matches", "answer", "value")))
    aciertos = sum(1 for izq, der in esperadas.items() if dadas.get(izq) == der)
    return _porcentaje(aciertos, len(esperadas)), esperadas


def corregir_ordering(answer_key: dict, response: Any) -> tuple[float, Any]:
    """Ordenar: crédito parcial por elemento en su posición correcta."""
    esperado = [
        normalizar_texto(v)
        for v in _como_lista(_primer_valor(answer_key, ("order", "sequence", "correct", "answer")))
    ]
    if not esperado:
        return 0.0, None
    dado = [
        normalizar_texto(v)
        for v in _como_lista(_primer_valor(response, ("order", "sequence", "answer", "value")))
    ]
    aciertos = sum(
        1 for i, valor in enumerate(esperado) if i < len(dado) and dado[i] == valor
    )
    return _porcentaje(aciertos, len(esperado)), esperado


#: Corrector determinista por tipo de pregunta.
CORRECTORES = {
    QuestionType.MULTIPLE_CHOICE: corregir_multiple_choice,
    QuestionType.TRUE_FALSE: corregir_true_false,
    QuestionType.FILL_BLANK: corregir_fill_blank,
    QuestionType.MATCHING: corregir_matching,
    QuestionType.ORDERING: corregir_ordering,
}


# ---------------------------------------------------------------------------
# Peso de acierto para el dominio (§6.4)
# ---------------------------------------------------------------------------


def peso_de_acierto(cfg: ServicioConfig, *, is_correct: bool, attempt_no: int) -> float:
    """`c_i` de §6.4: 1.0 al primer intento, `mastery.correctness_second_try` al segundo, 0.0 después.

    El crédito parcial **no** aporta dominio: solo el acierto pleno cuenta.
    """
    if not is_correct:
        return 0.0
    if attempt_no <= 1:
        return 1.0
    if attempt_no == 2:
        return float(cfg.obtener_decimal("mastery.correctness_second_try"))
    return 0.0


def resultado_de_puntaje(puntaje: float) -> AttemptResult:
    """Traduce un crédito 0–100 al enum `AttemptResult` (§2)."""
    if puntaje >= 100.0:
        return AttemptResult.CORRECT
    if puntaje > 0.0:
        return AttemptResult.PARTIAL
    return AttemptResult.INCORRECT


def respuesta_vacia(response: Any) -> bool:
    """Indica si el usuario no envió nada (se registra como `SKIPPED`)."""
    if response is None:
        return True
    if isinstance(response, dict):
        return not any(v not in (None, "", [], {}) for v in response.values())
    if isinstance(response, (list, tuple, str)):
        return len(response) == 0
    return False


# ---------------------------------------------------------------------------
# Puentes con el módulo `ai` (importación perezosa: §1.3)
# ---------------------------------------------------------------------------


def _juez_disponible():
    """Devuelve `ai.juez.juzgar_respuesta` si el módulo `ai` está construido.

    El nombre importa: durante mucho tiempo este puente buscó
    `evaluar_respuesta_abierta`, que no existe, de modo que `getattr` devolvía
    `None` **siempre** y toda respuesta abierta quedaba en `NEEDS_REVIEW` con
    método `PENDING` y puntaje cero. Ninguna prueba lo veía porque el propio
    juez se probaba por separado y el fallo vivía en la costura.
    """
    try:  # pragma: no cover - depende de que el módulo `ai` esté construido
        from app.modules.ai import juez  # noqa: PLC0415 - puente opcional
    except ImportError:
        return None
    return getattr(juez, "juzgar_respuesta", None)


def _sandbox_disponible():
    """Devuelve `ai.sandbox_sql.evaluar_ejercicio` si el módulo `ai` existe.

    Mismo caso que el juez: el módulo se llama `sandbox_sql`, no `sandbox`, así
    que el `import` fallaba en silencio y ningún ejercicio de SQL se corregía.
    """
    try:  # pragma: no cover - depende de que el módulo `ai` esté construido
        from app.modules.ai import sandbox_sql  # noqa: PLC0415 - puente opcional
    except ImportError:
        return None
    return getattr(sandbox_sql, "evaluar_ejercicio", None)


def _proveedor_disponible(cfg: ServicioConfig):
    """Crea el proveedor de IA configurado, o `None` si el módulo no está."""
    try:  # pragma: no cover - depende de que el módulo `ai` esté construido
        from app.modules.ai.proveedor import crear_proveedor  # noqa: PLC0415
    except ImportError:
        return None
    return crear_proveedor(cfg=cfg)


def _pendiente(explicacion: str | None, motivo: str) -> ResultadoCorreccion:
    """Respuesta que no se puede juzgar todavía: ni acierto ni error, sin dominio."""
    return ResultadoCorreccion(
        result=AttemptResult.NEEDS_REVIEW,
        is_correct=False,
        partial_score=0.0,
        correctness_weight=0.0,
        evaluation_method=EvaluationMethod.PENDING,
        correct_answer=None,
        explanation=explicacion,
        judge_payload={"pending_reason": motivo},
        counts_for_mastery=False,
    )


def corregir_abierta(
    cfg: ServicioConfig,
    pregunta: Question,
    response: Any,
    *,
    attempt_no: int,
    db: Any = None,
    usuario_id: Any = None,
    activity_id: Any = None,
) -> ResultadoCorreccion:
    """Respuesta abierta: la juzga el módulo `ai` con la rúbrica de `questions.body`.

    Las guardas de coste y de calidad de §5.8 (`ai.judge`) viven **dentro** del
    juez: las palabras mínimas, los umbrales de acierto y parcial, el beneficio
    de la duda por baja confianza y el escalado de modelo. Aquí no se repiten a
    propósito, porque dos copias de los mismos umbrales acaban divergiendo.

    Sin sesión de base de datos o sin el módulo `ai`, la respuesta queda
    pendiente en vez de darse por incorrecta: no calificar es honesto,
    suspender a quien acertó no lo es.
    """
    texto = str(_primer_valor(response, ("text", "answer", "value")) or "").strip()

    # Un «no sé» no vale una llamada al modelo. El juez aplica la misma guarda
    # leyendo la misma clave de configuración, así que no pueden divergir; esta
    # copia existe para que la corrección siga siendo barata sin base de datos.
    minimo = int(dict(cfg.obtener_json("ai.judge"))["min_words"])
    if len(texto.split()) < minimo:
        return ResultadoCorreccion(
            result=AttemptResult.INCORRECT,
            is_correct=False,
            partial_score=0.0,
            correctness_weight=0.0,
            evaluation_method=EvaluationMethod.DETERMINISTIC,
            correct_answer=None,
            explanation=pregunta.explanation,
        )

    juzgar = _juez_disponible()
    if juzgar is None or db is None:
        return _pendiente(pregunta.explanation, "judge_unavailable")
    proveedor = _proveedor_disponible(cfg)
    if proveedor is None:
        return _pendiente(pregunta.explanation, "judge_unavailable")

    try:
        veredicto = juzgar(
            db,
            cfg,
            proveedor,
            question=pregunta,
            texto=texto,
            usuario_id=usuario_id,
            activity_id=activity_id,
        )
    except Exception as error:
        # La respuesta del aprendiz vale más que el veredicto. Si la cuota está
        # agotada, el proveedor no responde o la clave no está configurada, se
        # guarda pendiente y se corrige después: dejar escapar el error haría
        # que el intento no se escribiera y que la lección no se pudiera cerrar.
        logger.warning(
            "content.juez_no_disponible",
            question_id=str(pregunta.id),
            error=type(error).__name__,
        )
        return _pendiente(pregunta.explanation, "judge_unavailable")

    carga = veredicto.como_dict()
    correcta = bool(veredicto.is_correct)
    # Un veredicto pendiente no es un cero: es una respuesta sin corregir. Si
    # contara para el dominio, agotar el presupuesto del día hundiría el dominio
    # de quien respondió bien y le sugeriría repasos que no necesita (§3.4).
    concluyente = veredicto.evaluation_method is not EvaluationMethod.PENDING
    return ResultadoCorreccion(
        result=veredicto.result,
        is_correct=correcta,
        partial_score=round(float(veredicto.partial_score), 2),
        correctness_weight=(
            peso_de_acierto(cfg, is_correct=correcta, attempt_no=attempt_no)
            if concluyente
            else 0.0
        ),
        evaluation_method=veredicto.evaluation_method,
        correct_answer=carga.get("model_answer") or carga.get("reference_answer"),
        explanation=veredicto.feedback or pregunta.explanation,
        judge_confidence=round(float(veredicto.confidence), 2),
        judge_payload=carga,
        counts_for_mastery=concluyente,
    )


def corregir_sql(
    cfg: ServicioConfig, pregunta: Question, response: Any, *, attempt_no: int
) -> ResultadoCorreccion:
    """Ejercicio de SQL: lo ejecuta el sandbox DuckDB del módulo `ai` (§5.8 `ai.sql_sandbox`).

    Es determinista y de coste cero: se compara el conjunto de filas devuelto por la
    consulta del usuario con el de la consulta de la clave.
    """
    evaluar = _sandbox_disponible()
    if evaluar is None:
        return _pendiente(pregunta.explanation, "sandbox_unavailable")

    consulta = str(_primer_valor(response, ("sql", "query", "text", "answer", "value")) or "")
    try:
        veredicto = evaluar(
            cfg,
            body=dict(pregunta.body or {}),
            answer_key=dict(pregunta.answer_key or {}),
            consulta_usuario=consulta,
        )
    except Exception as error:
        # El sandbox promete no lanzar, pero prepara la base con el esquema que
        # escribió el modelo: un tipo inventado en el `CREATE TABLE` revienta en
        # DuckDB. Eso es un fallo del catálogo, no del aprendiz.
        logger.warning(
            "content.sandbox_sql_roto",
            question_id=str(pregunta.id),
            error=type(error).__name__,
        )
        return _pendiente(pregunta.explanation, "sandbox_unavailable")

    # Cuando el ejercicio no tiene consulta de referencia utilizable, el veredicto
    # habla del catálogo y no de la respuesta: tampoco puede contar para dominio.
    if veredicto.error_code in CULPA_DEL_CATALOGO:
        return _pendiente(pregunta.explanation, veredicto.error_code or "sandbox_unavailable")

    correcta = bool(veredicto.is_correct)
    puntaje = float(veredicto.partial_score)
    return ResultadoCorreccion(
        result=resultado_de_puntaje(puntaje),
        is_correct=correcta,
        partial_score=round(puntaje, 2),
        correctness_weight=peso_de_acierto(cfg, is_correct=correcta, attempt_no=attempt_no),
        evaluation_method=EvaluationMethod.SANDBOX,
        correct_answer=(pregunta.answer_key or {}).get("reference_sql"),
        explanation=veredicto.message or pregunta.explanation,
        judge_payload=veredicto.como_dict(),
    )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


def corregir(
    cfg: ServicioConfig,
    pregunta: Question,
    response: Any,
    *,
    attempt_no: int = 1,
    db: Any = None,
    usuario_id: Any = None,
    activity_id: Any = None,
) -> ResultadoCorreccion:
    """Corrige una respuesta y devuelve el veredicto completo.

    Enruta por `question_type`: determinista para los cinco tipos cerrados, sandbox
    para SQL y juez de IA para las abiertas. Una respuesta vacía se registra como
    `SKIPPED` sin consumir ninguna llamada.
    """
    if respuesta_vacia(response):
        return ResultadoCorreccion(
            result=AttemptResult.SKIPPED,
            is_correct=False,
            partial_score=0.0,
            correctness_weight=0.0,
            evaluation_method=EvaluationMethod.DETERMINISTIC,
            correct_answer=None,
            explanation=pregunta.explanation,
        )

    tipo = pregunta.question_type
    if tipo in TIPOS_DETERMINISTAS:
        puntaje, esperada = CORRECTORES[tipo](dict(pregunta.answer_key or {}), response)
        correcta = puntaje >= 100.0
        return ResultadoCorreccion(
            result=resultado_de_puntaje(puntaje),
            is_correct=correcta,
            partial_score=puntaje,
            correctness_weight=peso_de_acierto(cfg, is_correct=correcta, attempt_no=attempt_no),
            evaluation_method=EvaluationMethod.DETERMINISTIC,
            correct_answer=esperada,
            explanation=pregunta.explanation,
        )
    if tipo == QuestionType.SQL_EXERCISE:
        return corregir_sql(cfg, pregunta, response, attempt_no=attempt_no)
    if tipo == QuestionType.OPEN_SHORT:
        return corregir_abierta(
            cfg,
            pregunta,
            response,
            attempt_no=attempt_no,
            db=db,
            usuario_id=usuario_id,
            activity_id=activity_id,
        )
    # `case_study` y `code_exercise` están reservados para fases 2 y 3 (§2).
    return _pendiente(pregunta.explanation, "question_type_reserved")


__all__ = [
    "CORRECTORES",
    "TIPOS_DETERMINISTAS",
    "TIPOS_RESERVADOS",
    "ResultadoCorreccion",
    "corregir",
    "corregir_abierta",
    "corregir_fill_blank",
    "corregir_matching",
    "corregir_multiple_choice",
    "corregir_ordering",
    "corregir_sql",
    "corregir_true_false",
    "normalizar_texto",
    "peso_de_acierto",
    "respuesta_vacia",
    "resultado_de_puntaje",
]
