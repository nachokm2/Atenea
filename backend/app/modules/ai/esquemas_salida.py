"""Esquemas estrictos de las salidas de la IA y su validación con reintento acotado.

Cada tarea de generación tiene un modelo Pydantic v2 que describe **exactamente** lo
que el proveedor debe devolver. De ese modelo se deriva el esquema JSON estricto que
viaja en `output_config.format` (`prompt_templates.output_schema`) y contra el que se
valida la salida antes de persistir nada (CONTRACT.md §8.7: "toda salida se valida
contra su esquema antes de persistir").

Si la salida no valida, se reintenta un número **acotado** de veces devolviéndole al
modelo el error concreto; agotados los intentos se lanza `SalidaInvalida`
(`GENERATION_FAILED`, 502) y el trabajo queda en `FAILED` con su motivo.
"""

from __future__ import annotations

import copy
import json
from typing import Annotated, Any, Final, Literal, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger
from app.models.enums import (
    CoverageLevel,
    DifficultyLevel,
    LessonBlockType,
    ProvenanceOrigin,
    QuestionType,
)
from app.modules.ai.proveedor import ProveedorIA, RespuestaIA, SolicitudIA, UsoIA, uso_vacio

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------


class SalidaInvalida(ExternalServiceError):
    """502 · La IA devolvió una salida que no cumple su esquema tras los reintentos.

    Lleva el consumo de **todas** las tentativas en `uso`. Esas llamadas se
    hicieron y el proveedor las cobra, aunque ninguna sirviera: quien cierre el
    trabajo tiene que contabilizarlas o el presupuesto del día dirá que no se
    gastó nada.
    """

    code = "GENERATION_FAILED"

    #: Consumo acumulado de los intentos fallidos. Lo rellena `generar_validado`.
    uso: UsoIA | None = None


# ---------------------------------------------------------------------------
# Base común
# ---------------------------------------------------------------------------


def _objeto_desde_texto(valor: Any) -> Any:
    """Acepta un objeto libre tal cual, o el texto JSON con el que viaja.

    Las salidas estructuradas del proveedor no admiten objetos abiertos: exigen
    que todo objeto declare `additionalProperties: false`, lo que en un campo
    libre equivale a prohibir cualquier contenido. Por eso estos campos se le
    piden al modelo como texto JSON (ver `esquema_para_proveedor`) y se
    convierten aquí, en la frontera, una sola vez y en un solo sitio.
    """
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return {}
        try:
            cargado = json.loads(texto)
        except json.JSONDecodeError:
            # Un campo ilegible no debe tumbar la generación entera: se conserva
            # el texto para poder revisarlo.
            return {"texto": texto}
        return cargado if isinstance(cargado, dict) else {"valor": cargado}
    return valor


#: Objeto JSON de forma libre: llega como diccionario o como texto JSON.
ObjetoLibre = Annotated[dict[str, Any], BeforeValidator(_objeto_desde_texto)]


class EsquemaSalida(BaseModel):
    """Base de todas las salidas de la IA: estricta y sin campos extra."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Texto = Annotated[str, Field(min_length=1)]

#: Los dos tipos reservados de `QuestionType` no se generan en el MVP (§2, D13).
TIPOS_PREGUNTA_MVP: Final[frozenset[QuestionType]] = frozenset(
    {
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.TRUE_FALSE,
        QuestionType.FILL_BLANK,
        QuestionType.MATCHING,
        QuestionType.ORDERING,
        QuestionType.OPEN_SHORT,
        QuestionType.SQL_EXERCISE,
    }
)

#: Tipos de bloque que la IA puede producir: `inline_question` la inserta el servidor.
TIPOS_BLOQUE_GENERABLES: Final[frozenset[LessonBlockType]] = frozenset(
    {
        LessonBlockType.EXPLANATION,
        LessonBlockType.EXAMPLE,
        LessonBlockType.CODE_EXAMPLE,
        LessonBlockType.DIAGRAM,
        LessonBlockType.SUMMARY,
    }
)


# ---------------------------------------------------------------------------
# Fase A: esquema de ruta
# ---------------------------------------------------------------------------


class SalidaTema(EsquemaSalida):
    """Tema del esquema de ruta (`topics`)."""

    position: int = Field(ge=1, le=20)
    title: str = Field(min_length=3, max_length=140)
    learning_objectives: list[Texto] = Field(min_length=1, max_length=6)
    coverage: CoverageLevel = CoverageLevel.FULL
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    estimated_minutes: int = Field(default=12, ge=1, le=180)
    suggested_question_types: list[QuestionType] = Field(default_factory=list, max_length=7)
    source_chunk_ids: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("suggested_question_types")
    @classmethod
    def _solo_tipos_mvp(cls, valor: list[QuestionType]) -> list[QuestionType]:
        """Rechaza los tipos reservados de fase 2/3 (§2, D13)."""
        invalidos = [tipo for tipo in valor if tipo not in TIPOS_PREGUNTA_MVP]
        if invalidos:
            raise ValueError(f"tipos de pregunta fuera del MVP: {invalidos}")
        return valor


class SalidaModulo(EsquemaSalida):
    """Módulo del esquema de ruta (`path_modules`)."""

    position: int = Field(ge=1, le=20)
    title: str = Field(min_length=3, max_length=120)
    flavor_name: str = Field(default="", max_length=120)
    summary: str = Field(default="", max_length=2000)
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    estimated_minutes: int = Field(default=60, ge=1, le=2000)
    topics: list[SalidaTema] = Field(min_length=1, max_length=10)


class SalidaRuta(EsquemaSalida):
    """Salida completa de la Fase A (diseño de ruta)."""

    title: str = Field(min_length=3, max_length=120)
    summary: str = Field(default="", max_length=4000)
    modules: list[SalidaModulo] = Field(min_length=1, max_length=12)
    coverage_notes: list[Texto] = Field(default_factory=list, max_length=20)


# ---------------------------------------------------------------------------
# Fase B: lección y preguntas
# ---------------------------------------------------------------------------


class SalidaBloque(EsquemaSalida):
    """Bloque de una lección (`lesson_blocks`)."""

    position: int = Field(ge=1, le=40)
    block_type: LessonBlockType
    body: str = Field(min_length=1, max_length=12000)
    payload: ObjetoLibre = Field(default_factory=dict)
    """Datos propios del tipo de bloque (código, pie de imagen, referencias…).

    Es libre por diseño, y las salidas estructuradas del proveedor no admiten
    objetos abiertos: exigen que todo objeto declare `additionalProperties:
    false`, lo que dejaría este campo inservible. Por eso al proveedor se le
    pide como **texto JSON** y aquí se convierte de vuelta.
    """

    origin: ProvenanceOrigin = ProvenanceOrigin.SOURCE
    source_chunk_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("block_type")
    @classmethod
    def _tipo_generable(cls, valor: LessonBlockType) -> LessonBlockType:
        """`inline_question` la coloca el servidor, no el modelo."""
        if valor not in TIPOS_BLOQUE_GENERABLES:
            raise ValueError(f"la IA no genera bloques de tipo {valor.value}")
        return valor


class SalidaCobertura(EsquemaSalida):
    """Entrada de `lessons.coverage_report`: qué consiguió cubrir cada objetivo."""

    objective: Texto
    status: CoverageLevel = CoverageLevel.FULL


class SalidaLeccion(EsquemaSalida):
    """Salida de la generación de una lección (`lessons` + `lesson_blocks`)."""

    title: str = Field(min_length=3, max_length=140)
    summary: str = Field(default="", max_length=4000)
    estimated_seconds: int = Field(default=540, ge=60, le=3600)
    blocks: list[SalidaBloque] = Field(min_length=1, max_length=20)
    coverage_report: list[SalidaCobertura] = Field(default_factory=list, max_length=10)


class SalidaPregunta(EsquemaSalida):
    """Pregunta generada (`questions`)."""

    question_type: QuestionType
    difficulty: DifficultyLevel = DifficultyLevel.EASY
    stem: str = Field(min_length=5, max_length=2000)
    body: ObjetoLibre = Field(default_factory=dict)
    answer_key: ObjetoLibre = Field(default_factory=dict)
    explanation: str = Field(default="", max_length=4000)
    learning_objective: str = Field(default="", max_length=240)
    estimated_seconds: int = Field(default=45, ge=5, le=900)
    origin: ProvenanceOrigin = ProvenanceOrigin.SOURCE
    source_chunk_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("question_type")
    @classmethod
    def _solo_tipos_mvp(cls, valor: QuestionType) -> QuestionType:
        """El validador de contenido rechaza `case_study` y `code_exercise` (D13)."""
        if valor not in TIPOS_PREGUNTA_MVP:
            raise ValueError(f"tipo de pregunta fuera del MVP: {valor.value}")
        return valor

    def clave_completa(self) -> bool:
        """Comprueba que `answer_key` encaja con el `body` del tipo declarado."""
        cuerpo, clave = self.body, self.answer_key
        match self.question_type:
            case QuestionType.MULTIPLE_CHOICE:
                opciones = {str(o.get("key")) for o in cuerpo.get("options", []) if isinstance(o, dict)}
                return len(opciones) >= 2 and str(clave.get("correct_option")) in opciones
            case QuestionType.TRUE_FALSE:
                return isinstance(clave.get("correct"), bool) and bool(cuerpo.get("statement"))
            case QuestionType.FILL_BLANK:
                huecos = clave.get("blanks")
                return isinstance(huecos, list) and len(huecos) >= 1
            case QuestionType.MATCHING:
                parejas = clave.get("pairs")
                return isinstance(parejas, list) and len(parejas) >= 2
            case QuestionType.ORDERING:
                orden = clave.get("order")
                elementos = {str(i.get("key")) for i in cuerpo.get("items", []) if isinstance(i, dict)}
                return isinstance(orden, list) and set(map(str, orden)) == elementos and len(orden) >= 2
            case QuestionType.OPEN_SHORT:
                rubrica = cuerpo.get("rubric", {})
                criterios = rubrica.get("criteria") if isinstance(rubrica, dict) else None
                return isinstance(criterios, list) and len(criterios) >= 1
            case QuestionType.SQL_EXERCISE:
                return bool(cuerpo.get("schema_sql")) and bool(clave.get("reference_sql"))
            case _:  # pragma: no cover - tipos reservados ya rechazados arriba
                return False


class SalidaLotePreguntas(EsquemaSalida):
    """Lote de preguntas de un tema."""

    questions: list[SalidaPregunta] = Field(min_length=1, max_length=20)


# ---------------------------------------------------------------------------
# Juez de respuestas abiertas
# ---------------------------------------------------------------------------


class SalidaCriterio(EsquemaSalida):
    """Criterio de la rúbrica evaluado por el juez."""

    key: Texto
    met: Literal["full", "partial", "none"]


class SalidaVeredicto(EsquemaSalida):
    """Veredicto estructurado del juez de respuestas abiertas."""

    score: float = Field(ge=0, le=100)
    verdict: Literal["correct", "partial", "incorrect"]
    confidence: float = Field(ge=0, le=1)
    feedback: str = Field(default="", max_length=1200)
    criteria: list[SalidaCriterio] = Field(default_factory=list, max_length=12)
    missing: list[str] = Field(default_factory=list, max_length=12)
    flags: list[str] = Field(default_factory=list, max_length=8)


# ---------------------------------------------------------------------------
# Re-explicación adaptativa
# ---------------------------------------------------------------------------


class SalidaExplicacion(EsquemaSalida):
    """Explicación alternativa (`ExplanationOut` de §7.6)."""

    approach: Texto
    body: str = Field(min_length=40, max_length=8000)
    citations: list[str] = Field(default_factory=list, max_length=10)
    check_question: str = Field(default="", max_length=400)


# ---------------------------------------------------------------------------
# Registro de esquemas por tarea
# ---------------------------------------------------------------------------

ModeloSalida = TypeVar("ModeloSalida", bound=EsquemaSalida)

#: Modelo de salida de cada tarea de `proveedor.TAREA_*`.
ESQUEMAS: Final[dict[str, type[EsquemaSalida]]] = {
    "path_design": SalidaRuta,
    "lesson": SalidaLeccion,
    "questions": SalidaLotePreguntas,
    "judge": SalidaVeredicto,
    "judge_escalation": SalidaVeredicto,
    "re_explanation": SalidaExplicacion,
}


# ---------------------------------------------------------------------------
# Esquema JSON estricto
# ---------------------------------------------------------------------------


def _inline_refs(nodo: Any, defs: dict[str, Any]) -> Any:
    """Sustituye los `$ref` por su definición para que el esquema sea autocontenido."""
    if isinstance(nodo, dict):
        referencia = nodo.get("$ref")
        if isinstance(referencia, str) and referencia.startswith("#/$defs/"):
            destino = copy.deepcopy(defs.get(referencia.split("/")[-1], {}))
            resto = {k: v for k, v in nodo.items() if k != "$ref"}
            destino.update(resto)
            return _inline_refs(destino, defs)
        return {clave: _inline_refs(valor, defs) for clave, valor in nodo.items()}
    if isinstance(nodo, list):
        return [_inline_refs(elemento, defs) for elemento in nodo]
    return nodo


def _endurecer(nodo: Any) -> Any:
    """Marca todo objeto como cerrado y con todas sus propiedades obligatorias."""
    if isinstance(nodo, dict):
        resultado = {clave: _endurecer(valor) for clave, valor in nodo.items()}
        propiedades = resultado.get("properties")
        if isinstance(propiedades, dict):
            resultado["type"] = "object"
            resultado["additionalProperties"] = False
            resultado["required"] = list(propiedades.keys())
        return resultado
    if isinstance(nodo, list):
        return [_endurecer(elemento) for elemento in nodo]
    return nodo


def esquema_estricto(modelo: type[EsquemaSalida]) -> dict[str, Any]:
    """Esquema JSON estricto y autocontenido de un modelo de salida.

    Estricto significa: sin `$ref`, todo objeto cerrado (`additionalProperties: false`)
    y con todas sus propiedades en `required`, tal y como exigen las salidas
    estructuradas del proveedor.
    """
    crudo = modelo.model_json_schema()
    defs = crudo.pop("$defs", {})
    plano = _inline_refs(crudo, defs)
    duro = _endurecer(plano)
    duro.pop("$defs", None)
    duro.setdefault("title", modelo.__name__)
    return duro


#: Palabras clave de JSON Schema que las salidas estructuradas del proveedor no
#: aceptan. Son restricciones de valor, no de forma: quitarlas no cambia la
#: estructura que se le pide al modelo, y la validación sigue siendo estricta
#: porque el Pydantic de este módulo las aplica igual al leer la respuesta.
#:
#: `maxItems` fue la que rompió la primera llamada real ("For 'array' type,
#: property 'maxItems' is not supported"); las demás se quitan por prevención,
#: al ser de la misma familia.
CLAVES_NO_SOPORTADAS: frozenset[str] = frozenset(
    {
        "maxItems",
        "minItems",
        "uniqueItems",
        "maxLength",
        "minLength",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "format",
        "default",
        "examples",
    }
)


def esquema_para_proveedor(esquema: dict[str, Any]) -> dict[str, Any]:
    """Versión del esquema apta para enviar al proveedor.

    Conserva lo estructural (tipos, propiedades, obligatorios, enumeraciones,
    descripciones) y descarta las restricciones de valor que la API rechaza. La
    validación fuerte no se pierde: ocurre aquí, al convertir la respuesta en el
    modelo Pydantic, que sí aplica longitudes, rangos y tamaños.
    """

    def limpiar(nodo: Any) -> Any:
        if isinstance(nodo, dict):
            resultado = {
                clave: limpiar(valor)
                for clave, valor in nodo.items()
                if clave not in CLAVES_NO_SOPORTADAS
            }
            if resultado.get("type") == "object" and "properties" not in resultado:
                # Objeto libre: el proveedor exige `additionalProperties: false`
                # en todo objeto, lo que aquí equivaldría a prohibir cualquier
                # contenido. Se pide como texto JSON y se convierte al leerlo.
                descripcion = resultado.get("description") or resultado.get("title") or ""
                return {
                    "type": "string",
                    "description": (
                        f"{descripcion} Devuélvelo como un objeto JSON "
                        "serializado en una sola cadena de texto."
                    ).strip(),
                }
            if "properties" in resultado:
                resultado["type"] = "object"
                resultado["additionalProperties"] = False
            return resultado
        if isinstance(nodo, list):
            return [limpiar(elemento) for elemento in nodo]
        return nodo

    return limpiar(esquema)


def esquema_de_tarea(tarea: str) -> dict[str, Any] | None:
    """Esquema JSON estricto de una tarea, o `None` si la tarea devuelve texto libre."""
    modelo = ESQUEMAS.get(tarea)
    return esquema_estricto(modelo) if modelo is not None else None


# ---------------------------------------------------------------------------
# Validación con reintento acotado
# ---------------------------------------------------------------------------


def _resumen_errores(error: ValidationError, maximo: int = 6) -> str:
    """Resumen legible de los errores de validación para devolvérselo al modelo."""
    lineas = []
    for detalle in error.errors()[:maximo]:
        ruta = ".".join(str(parte) for parte in detalle.get("loc", ())) or "(raíz)"
        lineas.append(f"- {ruta}: {detalle.get('msg')}")
    return "\n".join(lineas)


def validar[ModeloSalida: EsquemaSalida](modelo: type[ModeloSalida], bruto: Any) -> ModeloSalida:
    """Valida una salida cruda contra su modelo Pydantic."""
    if not isinstance(bruto, dict):
        raise SalidaInvalida(
            "No pudimos generar el contenido. Inténtalo de nuevo.",
            details={"reason": "output_not_object"},
        )
    return modelo.model_validate(bruto)


def generar_validado[ModeloSalida: EsquemaSalida](
    proveedor: ProveedorIA,
    solicitud: SolicitudIA,
    modelo: type[ModeloSalida],
    *,
    max_intentos: int = 2,
) -> tuple[ModeloSalida, RespuestaIA]:
    """Pide una salida estructurada y la valida, reintentando de forma **acotada**.

    En cada reintento se le devuelve al modelo el error exacto de validación. El uso de
    todas las tentativas se acumula en la `RespuestaIA` devuelta, de modo que el coste
    de los reintentos también se contabiliza.

    Y si ninguna tentativa valida, ese consumo no se pierde: viaja en
    `SalidaInvalida.uso`. Antes se descartaba, así que una racha de generaciones
    que no cuadraban con su esquema quemaba la tarjeta a toda velocidad mientras
    el presupuesto del día seguía marcando cero y el freno no saltaba nunca.
    """
    if solicitud.esquema is None:
        solicitud.esquema = esquema_estricto(modelo)

    instruccion_original = solicitud.instruccion
    uso_total: UsoIA = uso_vacio()
    ultimo_error: ValidationError | None = None
    respuesta: RespuestaIA | None = None

    for intento in range(1, max(1, max_intentos) + 1):
        respuesta = proveedor.generar_estructurado(solicitud)
        uso_total = uso_total + respuesta.uso
        try:
            validado = validar(modelo, respuesta.contenido)
        except ValidationError as error:
            ultimo_error = error
            solicitud.instruccion = (
                f"{instruccion_original}\n\n"
                "## Corrección obligatoria\n"
                "Tu respuesta anterior no cumplió el esquema. Corrige exactamente esto y "
                "devuelve de nuevo el objeto JSON completo:\n"
                f"{_resumen_errores(error)}"
            )
            continue
        solicitud.instruccion = instruccion_original
        return validado, RespuestaIA(
            contenido=respuesta.contenido,
            uso=uso_total,
            tarea=solicitud.tarea,
            reintentos=intento - 1,
            texto_bruto=respuesta.texto_bruto,
        )

    solicitud.instruccion = instruccion_original
    detalles: dict[str, Any] = {"task": solicitud.tarea, "attempts": max_intentos}
    if ultimo_error is not None:
        detalles["errors"] = _resumen_errores(ultimo_error)

    # Al registro va el detalle; al usuario, el mensaje amable. Sin esta línea,
    # un contenido que no valida es indistinguible de una caída del proveedor, y
    # se acaba buscando el fallo donde no está.
    logger.warning(
        "ai.salida_invalida",
        task=solicitud.tarea,
        attempts=max_intentos,
        errors=detalles.get("errors"),
        muestra=str(respuesta.contenido)[:400] if respuesta else "",
    )
    fallo = SalidaInvalida(
        "No pudimos generar el contenido. Inténtalo de nuevo.",
        details=detalles,
    )
    fallo.uso = uso_total
    raise fallo


__all__ = [
    "CLAVES_NO_SOPORTADAS",
    "ESQUEMAS",
    "TIPOS_BLOQUE_GENERABLES",
    "TIPOS_PREGUNTA_MVP",
    "EsquemaSalida",
    "SalidaBloque",
    "SalidaCobertura",
    "SalidaCriterio",
    "SalidaExplicacion",
    "SalidaInvalida",
    "SalidaLeccion",
    "SalidaLotePreguntas",
    "SalidaModulo",
    "SalidaPregunta",
    "SalidaRuta",
    "SalidaTema",
    "SalidaVeredicto",
    "esquema_de_tarea",
    "esquema_estricto",
    "esquema_para_proveedor",
    "generar_validado",
    "validar",
]
