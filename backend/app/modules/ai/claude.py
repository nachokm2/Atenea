"""Proveedor real de IA: Anthropic Claude con el SDK `anthropic` (cliente síncrono).

Decisiones que fija el contrato y que aquí se cumplen al pie de la letra:

- **Enrutamiento por tarea** desde `game_configs` → `ai.models` (§5.8): arquitecto
  `claude-opus-5`, autor `claude-sonnet-5`, juez `claude-haiku-4-5`. Ningún identificador
  de modelo se escribe en el código (§1.2).
- **Salidas estructuradas** con `output_config={"format": {"type": "json_schema", …}}`.
- **Caché de prefijo estable**: el `system` es el cuerpo de la plantilla de prompt y
  lleva `cache_control`; todo lo variable (tema, objetivos, material) va después, en el
  mensaje de usuario, para no invalidar el prefijo.
- **El material del usuario nunca va en el `system`** (§8.7) y las llamadas de
  generación **no llevan herramientas**.
- **Reintentos con `tenacity`** ante errores transitorios y traducción de cualquier
  fallo a `ExternalServiceError` (`GENERATION_FAILED`, 502), sin filtrar trazas.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import anthropic
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.errors import ExternalServiceError
from app.core.logging import get_logger
from app.modules.ai.proveedor import (
    ProveedorIA,
    RespuestaIA,
    SolicitudIA,
    UsoIA,
    calcular_coste,
    modelo_para_tarea,
)
from app.modules.gamification.servicio_config import ServicioConfig

logger = get_logger(__name__)

#: Errores del SDK que merecen reintento: son transitorios por definición.
_TRANSITORIOS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
)

#: A partir de este tope de salida se usa `messages.stream` para no chocar con el
#: tiempo de espera HTTP del SDK.
UMBRAL_STREAMING: int = 8_000


class ProveedorClaude(ProveedorIA):
    """Implementación real del proveedor de IA sobre el SDK `anthropic`."""

    nombre = "anthropic"

    def __init__(
        self,
        *,
        cfg: ServicioConfig | None = None,
        cliente: Any | None = None,
        max_reintentos: int = 3,
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.max_reintentos = max(1, max_reintentos)
        if cliente is not None:
            self.cliente = cliente
        else:
            if not settings.anthropic_api_key:
                raise ExternalServiceError(
                    "El servicio de generación no está configurado.",
                    details={"reason": "missing_api_key"},
                )
            # `max_retries=0`: los reintentos los gobierna `tenacity` aquí abajo,
            # para que el trabajo pueda contarlos y persistirlos.
            self.cliente = anthropic.Anthropic(
                api_key=settings.anthropic_api_key, max_retries=0
            )

    # ------------------------------------------------------------------
    # Interfaz
    # ------------------------------------------------------------------
    def generar_estructurado(self, solicitud: SolicitudIA) -> RespuestaIA:
        """Llama al modelo con salida estructurada y devuelve el JSON ya parseado."""
        if solicitud.esquema is None:
            raise ExternalServiceError(
                "No pudimos generar el contenido. Inténtalo de nuevo.",
                details={"reason": "missing_output_schema", "task": solicitud.tarea},
            )
        texto, uso = self._invocar(solicitud, esquema=solicitud.esquema)
        try:
            contenido = json.loads(texto)
        except json.JSONDecodeError as error:
            raise ExternalServiceError(
                "No pudimos generar el contenido. Inténtalo de nuevo.",
                details={"reason": "invalid_json", "task": solicitud.tarea},
            ) from error
        return RespuestaIA(
            contenido=contenido,
            uso=uso,
            tarea=solicitud.tarea,
            texto_bruto=texto,
        )

    def generar_texto(self, solicitud: SolicitudIA) -> RespuestaIA:
        """Llama al modelo sin esquema y devuelve el texto plano."""
        texto, uso = self._invocar(solicitud, esquema=None)
        return RespuestaIA(
            contenido=texto,
            uso=uso,
            tarea=solicitud.tarea,
            texto_bruto=texto,
        )

    # ------------------------------------------------------------------
    # Construcción de la petición
    # ------------------------------------------------------------------
    def _parametros(self, solicitud: SolicitudIA, esquema: dict[str, Any] | None) -> dict[str, Any]:
        """Arma los argumentos de `messages.create` / `messages.stream`."""
        modelo = solicitud.modelo or modelo_para_tarea(self.cfg, solicitud.tarea)
        parametros: dict[str, Any] = {
            "model": modelo,
            "max_tokens": solicitud.max_tokens,
            # Prefijo estable y cacheable: solo la plantilla de prompt.
            "system": [
                {
                    "type": "text",
                    "text": solicitud.sistema,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            # Lo variable (instrucción + material no confiable) va aquí.
            "messages": [{"role": "user", "content": solicitud.mensaje_usuario()}],
        }
        salida: dict[str, Any] = {}
        if esquema is not None:
            salida["format"] = {"type": "json_schema", "schema": esquema}
        if solicitud.esfuerzo:
            salida["effort"] = solicitud.esfuerzo
        if salida:
            parametros["output_config"] = salida
        return parametros

    # ------------------------------------------------------------------
    # Llamada con reintentos
    # ------------------------------------------------------------------
    def _invocar(
        self, solicitud: SolicitudIA, *, esquema: dict[str, Any] | None
    ) -> tuple[str, UsoIA]:
        """Ejecuta la llamada con reintentos y traduce cualquier fallo del proveedor."""
        parametros = self._parametros(solicitud, esquema)

        @retry(
            retry=retry_if_exception_type(_TRANSITORIOS),
            stop=stop_after_attempt(self.max_reintentos),
            wait=wait_exponential(multiplier=1, min=1, max=20),
            reraise=True,
        )
        def _llamar() -> Any:
            if solicitud.max_tokens > UMBRAL_STREAMING:
                with self.cliente.messages.stream(**parametros) as flujo:
                    return flujo.get_final_message()
            return self.cliente.messages.create(**parametros)

        try:
            mensaje = _llamar()
        except RetryError as error:  # pragma: no cover - tenacity con reraise=True
            raise self._traducir(error, solicitud) from error
        except anthropic.APIStatusError as error:
            raise self._traducir(error, solicitud) from error
        except anthropic.APIError as error:
            raise self._traducir(error, solicitud) from error

        if getattr(mensaje, "stop_reason", None) == "refusal":
            detalle = getattr(mensaje, "stop_details", None)
            raise ExternalServiceError(
                "No pudimos generar el contenido. Inténtalo de nuevo.",
                details={
                    "reason": "refusal",
                    "task": solicitud.tarea,
                    "category": getattr(detalle, "category", None),
                },
            )

        texto = self._texto_de(mensaje)
        uso = self._uso_de(mensaje, parametros["model"])
        logger.info(
            "ai.llamada",
            task=solicitud.tarea,
            model=uso.model_id,
            input_tokens=uso.input_tokens,
            cached_input_tokens=uso.cached_input_tokens,
            output_tokens=uso.output_tokens,
            cost_usd=str(uso.cost_usd),
        )
        return texto, self._anotar(uso, solicitud.tarea)

    # ------------------------------------------------------------------
    # Lectura de la respuesta
    # ------------------------------------------------------------------
    @staticmethod
    def _texto_de(mensaje: Any) -> str:
        """Concatena los bloques de texto de la respuesta."""
        partes = [
            bloque.text
            for bloque in getattr(mensaje, "content", [])
            if getattr(bloque, "type", None) == "text"
        ]
        return "".join(partes).strip()

    @staticmethod
    def _uso_de(mensaje: Any, modelo_pedido: str) -> UsoIA:
        """Traduce `usage` del SDK a `UsoIA` y calcula el coste con la tarifa real."""
        uso = getattr(mensaje, "usage", None)
        entrada = int(getattr(uso, "input_tokens", 0) or 0)
        escritura = int(getattr(uso, "cache_creation_input_tokens", 0) or 0)
        lectura = int(getattr(uso, "cache_read_input_tokens", 0) or 0)
        salida = int(getattr(uso, "output_tokens", 0) or 0)
        # `model` de la respuesta es el modelo exacto que atendió (§3.3).
        modelo = str(getattr(mensaje, "model", "") or modelo_pedido)
        coste = calcular_coste(
            modelo,
            input_tokens=entrada,
            cache_creation_tokens=escritura,
            cached_input_tokens=lectura,
            output_tokens=salida,
        )
        return UsoIA(
            model_id=modelo,
            provider=ProveedorClaude.nombre,
            # `generation_jobs.input_tokens` acumula entrada + escritura de caché.
            input_tokens=entrada + escritura,
            cached_input_tokens=lectura,
            output_tokens=salida,
            cache_creation_tokens=escritura,
            cost_usd=coste if isinstance(coste, Decimal) else Decimal(str(coste)),
        )

    # ------------------------------------------------------------------
    # Traducción de errores
    # ------------------------------------------------------------------
    @staticmethod
    def _traducir(error: Exception, solicitud: SolicitudIA) -> ExternalServiceError:
        """Convierte un error del SDK en `ExternalServiceError` sin filtrar trazas."""
        detalles: dict[str, Any] = {"task": solicitud.tarea, "provider": ProveedorClaude.nombre}
        estado = getattr(error, "status_code", None)
        if estado is not None:
            detalles["upstream_status"] = estado
        if isinstance(error, anthropic.RateLimitError):
            detalles["reason"] = "rate_limited"
        elif isinstance(error, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
            detalles["reason"] = "connection"
        elif isinstance(error, anthropic.AuthenticationError):
            detalles["reason"] = "auth"
        else:
            detalles["reason"] = "upstream_error"
        logger.warning("ai.error_proveedor", **detalles)
        return ExternalServiceError(
            "No pudimos generar el contenido. Inténtalo de nuevo.", details=detalles
        )


__all__ = ["UMBRAL_STREAMING", "ProveedorClaude"]
