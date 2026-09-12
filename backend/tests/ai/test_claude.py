"""Proveedor real: forma de la petición, caché de prefijo, coste y traducción de errores.

Sin red: se inyecta un cliente falso con la misma superficie que el SDK `anthropic`.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import anthropic
import httpx
import pytest

from app.core.errors import ExternalServiceError
from app.modules.ai.claude import ProveedorClaude
from app.modules.ai.esquemas_salida import SalidaExplicacion, esquema_estricto
from app.modules.ai.proveedor import TAREA_LESSON, FragmentoContexto, SolicitudIA

import uuid


class _Bloque:
    def __init__(self, texto: str) -> None:
        self.type = "text"
        self.text = texto


class _Uso:
    def __init__(self, entrada: int, escritura: int, lectura: int, salida: int) -> None:
        self.input_tokens = entrada
        self.cache_creation_input_tokens = escritura
        self.cache_read_input_tokens = lectura
        self.output_tokens = salida


class _Mensaje:
    def __init__(self, texto: str, *, uso: _Uso, modelo: str, stop: str = "end_turn") -> None:
        self.content = [_Bloque(texto)]
        self.usage = uso
        self.model = modelo
        self.stop_reason = stop
        self.stop_details = None


class _Flujo:
    def __init__(self, mensaje: _Mensaje) -> None:
        self._mensaje = mensaje

    def __enter__(self) -> _Flujo:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get_final_message(self) -> _Mensaje:
        return self._mensaje


class _Mensajes:
    def __init__(self, respuesta: Any, error: Exception | None = None) -> None:
        self.respuesta = respuesta
        self.error = error
        self.llamadas: list[dict[str, Any]] = []
        self.streams: list[dict[str, Any]] = []

    def create(self, **parametros: Any) -> Any:
        self.llamadas.append(parametros)
        if self.error is not None:
            raise self.error
        return self.respuesta

    def stream(self, **parametros: Any) -> _Flujo:
        self.streams.append(parametros)
        if self.error is not None:
            raise self.error
        return _Flujo(self.respuesta)


class _Cliente:
    def __init__(self, respuesta: Any, error: Exception | None = None) -> None:
        self.messages = _Mensajes(respuesta, error)


CONTENIDO = json.dumps(
    {
        "approach": "analogy",
        "body": "Una explicación con la longitud suficiente para pasar el mínimo del esquema.",
        "citations": [],
        "check_question": "¿Lo sabrías explicar?",
    }
)


def _solicitud() -> SolicitudIA:
    return SolicitudIA(
        tarea=TAREA_LESSON,
        sistema="Eres el autor de lecciones de Atenea.",
        instruccion="Explica los JOINs.",
        fragmentos=[
            FragmentoContexto(chunk_id=uuid.uuid4(), text="Un INNER JOIN devuelve las filas que casan.")
        ],
        esquema=esquema_estricto(SalidaExplicacion),
        modelo="claude-sonnet-5",
        max_tokens=4_000,
    )


def _proveedor(respuesta: Any, error: Exception | None = None) -> ProveedorClaude:
    return ProveedorClaude(cliente=_Cliente(respuesta, error))


def test_la_peticion_usa_cache_de_prefijo_y_salida_estructurada() -> None:
    """El `system` es estable y cacheado; el material va en el mensaje de usuario."""
    mensaje = _Mensaje(CONTENIDO, uso=_Uso(1_000, 200, 800, 300), modelo="claude-sonnet-5")
    proveedor = _proveedor(mensaje)
    respuesta = proveedor.generar_estructurado(_solicitud())

    assert respuesta.contenido["approach"] == "analogy"
    (parametros,) = proveedor.cliente.messages.llamadas
    assert parametros["model"] == "claude-sonnet-5"
    assert parametros["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert parametros["system"][0]["text"] == "Eres el autor de lecciones de Atenea."
    assert parametros["output_config"]["format"]["type"] == "json_schema"
    assert parametros["output_config"]["format"]["schema"]["additionalProperties"] is False
    # El material del usuario nunca viaja en el `system` (§8.7).
    contenido_usuario = parametros["messages"][0]["content"]
    assert "<material>" in contenido_usuario
    assert "INNER JOIN" in contenido_usuario
    assert "INNER JOIN" not in parametros["system"][0]["text"]
    # Las llamadas de generación no llevan herramientas.
    assert "tools" not in parametros


def test_contabiliza_tokens_y_coste_con_la_tarifa_real() -> None:
    """La escritura de caché cuesta más que la entrada y la lectura mucho menos."""
    mensaje = _Mensaje(CONTENIDO, uso=_Uso(1_000_000, 0, 0, 0), modelo="claude-sonnet-5")
    proveedor = _proveedor(mensaje)
    uso = proveedor.generar_estructurado(_solicitud()).uso

    assert uso.model_id == "claude-sonnet-5"
    assert uso.provider == "anthropic"
    assert uso.input_tokens == 1_000_000
    assert uso.cost_usd == Decimal("2.000000")
    assert proveedor.uso_acumulado.llamadas == 1


def test_la_escritura_de_cache_entra_en_input_tokens() -> None:
    """`generation_jobs` solo tiene tres columnas: la escritura suma a la entrada."""
    mensaje = _Mensaje(CONTENIDO, uso=_Uso(100, 50, 900, 20), modelo="claude-haiku-4-5")
    uso = _proveedor(mensaje).generar_estructurado(_solicitud()).uso
    assert uso.input_tokens == 150
    assert uso.cached_input_tokens == 900
    assert uso.cache_creation_tokens == 50


def test_usa_streaming_cuando_la_salida_es_larga() -> None:
    """Con `max_tokens` grande se usa `messages.stream` para no agotar el tiempo HTTP."""
    mensaje = _Mensaje(CONTENIDO, uso=_Uso(10, 0, 0, 10), modelo="claude-opus-5")
    proveedor = _proveedor(mensaje)
    solicitud = _solicitud()
    solicitud.max_tokens = 16_000
    proveedor.generar_estructurado(solicitud)

    assert proveedor.cliente.messages.streams
    assert not proveedor.cliente.messages.llamadas


def test_json_invalido_se_traduce_a_error_de_generacion() -> None:
    """Una salida que no es JSON no se persiste: es un fallo de generación."""
    mensaje = _Mensaje("esto no es json", uso=_Uso(10, 0, 0, 5), modelo="claude-sonnet-5")
    with pytest.raises(ExternalServiceError) as error:
        _proveedor(mensaje).generar_estructurado(_solicitud())
    assert error.value.code == "GENERATION_FAILED"
    assert error.value.details["reason"] == "invalid_json"


def test_traduce_el_limite_de_peticiones() -> None:
    """Un 429 del proveedor se traduce sin filtrar trazas ni mensajes técnicos."""
    fallo = anthropic.RateLimitError(
        "slow down",
        response=httpx.Response(429, request=httpx.Request("POST", "https://api.anthropic.com")),
        body=None,
    )
    with pytest.raises(ExternalServiceError) as error:
        _proveedor(None, fallo).generar_estructurado(_solicitud())
    assert error.value.code == "GENERATION_FAILED"
    assert error.value.details["reason"] == "rate_limited"
    assert error.value.message == "No pudimos generar el contenido. Inténtalo de nuevo."


def test_traduce_el_rechazo_del_modelo() -> None:
    """Un `stop_reason = refusal` no se confunde con contenido válido."""
    mensaje = _Mensaje("", uso=_Uso(10, 0, 0, 0), modelo="claude-opus-5", stop="refusal")
    with pytest.raises(ExternalServiceError) as error:
        _proveedor(mensaje).generar_estructurado(_solicitud())
    assert error.value.details["reason"] == "refusal"


def test_exige_esquema_en_las_salidas_estructuradas() -> None:
    """Sin esquema no hay salida estructurada posible: es un error de programación."""
    mensaje = _Mensaje(CONTENIDO, uso=_Uso(1, 0, 0, 1), modelo="claude-sonnet-5")
    solicitud = _solicitud()
    solicitud.esquema = None
    with pytest.raises(ExternalServiceError) as error:
        _proveedor(mensaje).generar_estructurado(solicitud)
    assert error.value.details["reason"] == "missing_output_schema"


def test_genera_texto_libre() -> None:
    """`generar_texto` devuelve el texto tal cual, sin `output_config.format`."""
    mensaje = _Mensaje("Texto de sabor del territorio.", uso=_Uso(5, 0, 0, 5), modelo="claude-haiku-4-5")
    proveedor = _proveedor(mensaje)
    solicitud = _solicitud()
    solicitud.esquema = None
    respuesta = proveedor.generar_texto(solicitud)
    assert respuesta.contenido == "Texto de sabor del territorio."
    (parametros,) = proveedor.cliente.messages.llamadas
    assert "output_config" not in parametros
