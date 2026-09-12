"""Configuración de logging estructurado con structlog.

- En producción y staging: una línea **JSON** por evento, apta para Railway.
- En desarrollo y pruebas: salida legible y coloreada por consola.
- El `request_id` (cabecera `X-Request-Id`, o generado por el servidor) se inyecta
  en **todos** los eventos de la petición mediante `contextvars`, igual que viaja
  en `error.request_id` de las respuestas de error (§8.1 y §8.4).

Nunca se registran secretos: contraseñas, hashes, tokens ni cabeceras `Authorization`.
"""

from __future__ import annotations

import logging
import sys
import uuid
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, get_contextvars

from app.core.config import settings

#: Claves que jamás se emiten en un log, vengan de donde vengan.
REDACTED_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "token_hash",
        "authorization",
        "api_key",
        "anthropic_api_key",
        "voyage_api_key",
        "jwt_secret",
        "answer_key",
    }
)

_configured = False


def _redact_processor(
    _logger: Any, _method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Sustituye por `***` cualquier clave sensible del evento."""
    for key in list(event_dict):
        if key.lower() in REDACTED_KEYS:
            event_dict[key] = "***"
    return event_dict


def configure_logging(level: str | None = None, *, json_logs: bool | None = None) -> None:
    """Configura structlog y la librería estándar de logging.

    Es idempotente: llamarla varias veces (aplicación y pruebas) no duplica handlers.
    """
    global _configured

    log_level = (level or settings.log_level).upper()
    use_json = settings.is_production if json_logs is None else json_logs

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level, logging.INFO),
        force=True,
    )
    # Ruido de terceros a raya.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.db_echo else logging.WARNING
    )
    logging.getLogger("passlib").setLevel(logging.ERROR)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _redact_processor,
    ]

    renderer: Any
    if use_json:
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        # Fábrica de la librería estándar: los logs de structlog y los de terceros
        # (uvicorn, sqlalchemy) salen por el mismo handler y con el mismo formato.
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None) -> Any:
    """Devuelve un logger estructurado, configurando el sistema si aún no se hizo."""
    if not _configured:
        configure_logging()
    return structlog.get_logger(name) if name else structlog.get_logger()


# ---------------------------------------------------------------------------
# Contexto de la petición
# ---------------------------------------------------------------------------


def new_request_id() -> str:
    """Genera un identificador de petición nuevo."""
    return str(uuid.uuid4())


def bind_request_context(
    request_id: str | None = None,
    *,
    user_id: str | None = None,
    path: str | None = None,
    method: str | None = None,
    **extra: Any,
) -> str:
    """Ata el `request_id` (y lo que se le añada) al contexto de logging.

    Devuelve el `request_id` efectivo, que el middleware debe guardar en
    `request.state.request_id` y devolver en la cabecera `X-Request-Id`.
    """
    rid = request_id or new_request_id()
    context: dict[str, Any] = {"request_id": rid}
    if user_id:
        context["user_id"] = user_id
    if path:
        context["path"] = path
    if method:
        context["method"] = method
    context.update(extra)
    bind_contextvars(**context)
    return rid


def bind_user(user_id: str | uuid.UUID) -> None:
    """Añade el usuario autenticado al contexto de logging de la petición."""
    bind_contextvars(user_id=str(user_id))


def current_request_id() -> str | None:
    """Devuelve el `request_id` atado al contexto actual, si lo hay."""
    value = get_contextvars().get("request_id")
    return str(value) if value else None


def clear_request_context() -> None:
    """Limpia el contexto de logging al terminar la petición."""
    clear_contextvars()


__all__ = [
    "REDACTED_KEYS",
    "bind_request_context",
    "bind_user",
    "clear_request_context",
    "configure_logging",
    "current_request_id",
    "get_logger",
    "new_request_id",
]
