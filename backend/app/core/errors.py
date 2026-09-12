"""Jerarquía de errores de Atenea y manejadores de excepción de FastAPI.

Formato único de respuesta de error (contrato §8.1)::

    {
      "error": {
        "code": "INSUFFICIENT_GOLD",
        "message": "No te alcanza el oro para esta compra.",
        "details": {"required": 1200, "balance": 860, "missing": 340},
        "request_id": "01J9X4K2M7Q8R…",
        "field_errors": []
      }
    }

El `message` va **en español** y es el texto que la app puede mostrar tal cual;
los detalles técnicos van en `details`. Nunca se devuelve una traza ni SQL.
El catálogo de códigos es **cerrado**: añadir uno exige actualizar CONTRACT.md.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("atenea.errors")

# ---------------------------------------------------------------------------
# Catálogo cerrado de códigos de error (§8.1): código -> estado HTTP
# ---------------------------------------------------------------------------

ERROR_STATUS: Final[dict[str, int]] = {
    "VALIDATION_ERROR": 422,
    "UNAUTHORIZED": 401,
    "INVALID_CREDENTIALS": 401,
    "TOKEN_REUSE_DETECTED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "EMAIL_ALREADY_EXISTS": 409,
    "CHARACTER_ALREADY_EXISTS": 409,
    "ALREADY_OWNED": 409,
    "REQUIREMENTS_NOT_MET": 409,
    "PRICE_CHANGED": 409,
    "UNAVAILABLE": 409,
    "INSUFFICIENT_GOLD": 409,
    "ATTEMPT_NOT_OPEN": 409,
    "ALREADY_ANSWERED": 409,
    "MODULE_LOCKED": 409,
    "ASSESSMENT_COOLDOWN": 409,
    "ASSESSMENT_ATTEMPT_LIMIT": 409,
    "CONTENT_NOT_READY": 409,
    "IDEMPOTENCY_KEY_REQUIRED": 400,
    "IDEMPOTENCY_KEY_CONFLICT": 409,
    "QUOTA_EXCEEDED": 429,
    "RATE_LIMITED": 429,
    "AI_BUDGET_EXCEEDED": 503,
    "FILE_TOO_LARGE": 413,
    "UNSUPPORTED_FILE_TYPE": 415,
    "DOCUMENT_UNREADABLE": 422,
    "GENERATION_FAILED": 502,
    "INTERNAL_ERROR": 500,
}

#: Mensajes por defecto, en español y dirigidos a la persona.
DEFAULT_MESSAGES: Final[dict[str, str]] = {
    "VALIDATION_ERROR": "Revisa los datos enviados: hay campos inválidos.",
    "UNAUTHORIZED": "Tu sesión no es válida o ha caducado. Vuelve a iniciar sesión.",
    "INVALID_CREDENTIALS": "El correo o la contraseña no son correctos.",
    "TOKEN_REUSE_DETECTED": "Se detectó un uso indebido de la sesión. Vuelve a iniciar sesión.",
    "FORBIDDEN": "No tienes permiso para hacer esto.",
    "NOT_FOUND": "No encontramos lo que buscas.",
    "EMAIL_ALREADY_EXISTS": "Ya existe una cuenta con ese correo.",
    "CHARACTER_ALREADY_EXISTS": "Ya creaste tu personaje.",
    "ALREADY_OWNED": "Ya tienes este objeto.",
    "REQUIREMENTS_NOT_MET": "Todavía no cumples los requisitos para desbloquear esto.",
    "PRICE_CHANGED": "El precio cambió. Vuelve a revisarlo antes de comprar.",
    "UNAVAILABLE": "Este objeto no está disponible en este momento.",
    "INSUFFICIENT_GOLD": "No te alcanza el oro para esta compra.",
    "ATTEMPT_NOT_OPEN": "Esta actividad ya no está abierta.",
    "ALREADY_ANSWERED": "Ya respondiste esta pregunta en este intento.",
    "MODULE_LOCKED": "Este módulo todavía está bloqueado.",
    "ASSESSMENT_COOLDOWN": "Aún no puedes repetir la prueba. Repasa un poco y vuelve.",
    "ASSESSMENT_ATTEMPT_LIMIT": "Alcanzaste el máximo de intentos de prueba por hoy.",
    "CONTENT_NOT_READY": "Tu contenido todavía se está preparando. Te avisamos al terminar.",
    "IDEMPOTENCY_KEY_REQUIRED": "Falta la cabecera Idempotency-Key en esta operación.",
    "IDEMPOTENCY_KEY_CONFLICT": "Esa clave de idempotencia ya se usó con otros datos.",
    "QUOTA_EXCEEDED": "Agotaste tu cuota diaria. Vuelve a intentarlo mañana.",
    "RATE_LIMITED": "Demasiadas peticiones seguidas. Espera un momento.",
    "AI_BUDGET_EXCEEDED": "El servicio de generación está saturado. Inténtalo más tarde.",
    "FILE_TOO_LARGE": "El archivo es demasiado grande.",
    "UNSUPPORTED_FILE_TYPE": "Ese formato de archivo no está admitido.",
    "DOCUMENT_UNREADABLE": "No pudimos leer el documento. Prueba con un archivo de texto real.",
    "GENERATION_FAILED": "No pudimos generar el contenido. Inténtalo de nuevo.",
    "INTERNAL_ERROR": "Ocurrió un error inesperado. Ya estamos en ello.",
}


# ---------------------------------------------------------------------------
# Jerarquía de excepciones
# ---------------------------------------------------------------------------


class AteneaError(Exception):
    """Error de dominio de Atenea traducible al formato de error de la API.

    Atributos:
        code: código del catálogo cerrado de §8.1.
        message: texto en español, apto para mostrar al usuario.
        details: datos estructurados de apoyo (nunca traza ni SQL).
        field_errors: lista `[{"field": …, "message": …}]` para errores de validación.
        status_code: estado HTTP; por defecto el que fija el catálogo.
        headers: cabeceras extra de la respuesta (por ejemplo `Retry-After`).
    """

    code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        field_errors: list[dict[str, str]] | None = None,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code or self.code
        self.status_code = status_code or ERROR_STATUS.get(self.code, self.status_code)
        self.message = message or DEFAULT_MESSAGES.get(self.code, "Ocurrió un error.")
        self.details: dict[str, Any] = details or {}
        self.field_errors: list[dict[str, str]] = field_errors or []
        self.headers: dict[str, str] = headers or {}
        super().__init__(self.message)

    def to_payload(self, request_id: str | None = None) -> dict[str, Any]:
        """Construye el cuerpo JSON de la respuesta de error."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "request_id": request_id,
                "field_errors": self.field_errors,
            }
        }

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"{type(self).__name__}(code={self.code!r}, status={self.status_code})"


class ValidationFailed(AteneaError):
    """422 · El cuerpo o los parámetros de la petición son inválidos."""

    code = "VALIDATION_ERROR"
    status_code = 422


class Unauthorized(AteneaError):
    """401 · Falta el token, está vencido o es inválido."""

    code = "UNAUTHORIZED"
    status_code = 401


class InvalidCredentials(Unauthorized):
    """401 · Correo o contraseña incorrectos."""

    code = "INVALID_CREDENTIALS"


class TokenReuseDetected(Unauthorized):
    """401 · Refresh token ya rotado; se revoca toda la cadena."""

    code = "TOKEN_REUSE_DETECTED"


class Forbidden(AteneaError):
    """403 · El recurso no pertenece al usuario o falta el rol.

    Ojo: para no filtrar la existencia de un recurso ajeno se usa `NotFound` (404),
    no este error (contrato §8.7).
    """

    code = "FORBIDDEN"
    status_code = 403


class NotFound(AteneaError):
    """404 · El recurso no existe o no es visible para este usuario."""

    code = "NOT_FOUND"
    status_code = 404


class Conflict(AteneaError):
    """409 · Conflicto con el estado actual del recurso.

    Base de todos los conflictos del catálogo: `EMAIL_ALREADY_EXISTS`,
    `ALREADY_OWNED`, `INSUFFICIENT_GOLD`, `MODULE_LOCKED`, etc.
    """

    code = "UNAVAILABLE"
    status_code = 409


class RateLimited(AteneaError):
    """429 · Demasiadas peticiones; añade la cabecera `Retry-After`."""

    code = "RATE_LIMITED"
    status_code = 429

    def __init__(self, message: str | None = None, *, retry_after: int | None = None, **kwargs: Any) -> None:
        headers = dict(kwargs.pop("headers", None) or {})
        details = dict(kwargs.pop("details", None) or {})
        if retry_after is not None:
            headers.setdefault("Retry-After", str(retry_after))
            details.setdefault("retry_after", retry_after)
        super().__init__(message, details=details, headers=headers, **kwargs)


class QuotaExceeded(RateLimited):
    """429 · Cuota diaria agotada (`details.quota`, `details.resets_at`)."""

    code = "QUOTA_EXCEEDED"


#: Alias histórico: en Atenea el plan gratuito no cobra, agota cuota.
PaymentRequired = QuotaExceeded


class ExternalServiceError(AteneaError):
    """502/503 · Falla un servicio externo (Claude, proveedor de embeddings…).

    Por defecto se reporta como `GENERATION_FAILED` (502); usa
    `code="AI_BUDGET_EXCEEDED"` para el freno global de presupuesto (503).
    """

    code = "GENERATION_FAILED"
    status_code = 502


class InternalError(AteneaError):
    """500 · Error no controlado. Nunca expone traza ni SQL."""

    code = "INTERNAL_ERROR"
    status_code = 500


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _request_id(request: Request) -> str | None:
    """Obtiene el identificador de la petición del estado o de la cabecera."""
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return str(request_id)
    return request.headers.get("X-Request-Id")


def error_response(exc: AteneaError, request: Request) -> JSONResponse:
    """Serializa un `AteneaError` al formato de error del contrato."""
    request_id = _request_id(request)
    headers = dict(exc.headers)
    if request_id:
        headers.setdefault("X-Request-Id", request_id)
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_payload(request_id),
        headers=headers or None,
    )


def _status_to_code(status_code: int) -> str:
    """Traduce un estado HTTP genérico al código del catálogo más cercano."""
    for code, status in ERROR_STATUS.items():
        if status == status_code:
            return code
    return "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# Manejadores de FastAPI
# ---------------------------------------------------------------------------


def atenea_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Traduce cualquier `AteneaError` al sobre de error de la API."""
    assert isinstance(exc, AteneaError)
    if exc.status_code >= 500:
        logger.error("atenea_error", extra={"code": exc.code, "details": exc.details})
    return error_response(exc, request)


def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convierte los errores de validación de FastAPI/Pydantic en `VALIDATION_ERROR`."""
    assert isinstance(exc, RequestValidationError)
    field_errors: list[dict[str, str]] = []
    for raw in exc.errors():
        location = [str(part) for part in raw.get("loc", ()) if part not in ("body", "query", "path")]
        field_errors.append(
            {
                "field": ".".join(location) or "body",
                "message": str(raw.get("msg", "Valor inválido.")),
            }
        )
    return error_response(ValidationFailed(field_errors=field_errors), request)


def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Normaliza las `HTTPException` de Starlette/FastAPI al formato del contrato."""
    assert isinstance(exc, StarletteHTTPException)
    code = _status_to_code(exc.status_code)
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail else None
    error = AteneaError(
        detail or DEFAULT_MESSAGES.get(code),
        code=code,
        status_code=exc.status_code,
        headers=dict(getattr(exc, "headers", None) or {}),
    )
    return error_response(error, request)


def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Última red de seguridad: registra la traza y devuelve `INTERNAL_ERROR` sin detalles."""
    logger.exception("unhandled_exception", exc_info=exc)
    return error_response(InternalError(), request)


def register_exception_handlers(app: FastAPI) -> None:
    """Registra en la aplicación todos los manejadores de error del contrato."""
    app.add_exception_handler(AteneaError, atenea_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


__all__ = [
    "DEFAULT_MESSAGES",
    "ERROR_STATUS",
    "AteneaError",
    "Conflict",
    "ExternalServiceError",
    "Forbidden",
    "InternalError",
    "InvalidCredentials",
    "NotFound",
    "PaymentRequired",
    "QuotaExceeded",
    "RateLimited",
    "TokenReuseDetected",
    "Unauthorized",
    "ValidationFailed",
    "atenea_error_handler",
    "error_response",
    "http_exception_handler",
    "register_exception_handlers",
    "unhandled_exception_handler",
    "validation_error_handler",
]
