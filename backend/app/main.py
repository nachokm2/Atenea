"""Punto de entrada de la API de Atenea.

Arranque:

    python -m uvicorn app.main:app --reload --port 8000

Monta la API v1 completa (CONTRACT.md §7), los manejadores de error del núcleo,
el registro estructurado con identificador de petición y CORS para el cliente
Flutter. El trabajo pesado (ingesta de documentos y generación con IA) no vive
aquí: lo ejecuta el worker (``python -m app.worker.principal``).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import api_v1, rutas_duplicadas, rutas_registradas
from app.core.config import settings
from app.core.db import engine
from app.core.errors import register_exception_handlers
from app.core.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
    new_request_id,
)

configure_logging()
log = get_logger(__name__)

DESCRIPCION = """
API de **Atenea**, un RPG medieval de aprendizaje: el material del usuario se
convierte en una ruta jugable y el progreso intelectual **es** la progresión del
personaje.

Reglas que atraviesan toda la API:

* El servidor es la autoridad. El cliente informa hechos (empecé, respondí,
  terminé) y nunca envía cantidades de XP, oro, dominio ni precios.
* Las acciones que otorgan recompensas devuelven el objeto canónico
  `RewardsReceipt` y exigen la cabecera `Idempotency-Key`.
* Los valores de juego viven en `game_configs`, no en el código.
"""


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    """Comprobaciones de arranque y cierre ordenado."""
    duplicadas = rutas_duplicadas()
    if duplicadas:
        # Un duplicado significa que dos módulos reclaman la misma ruta: es un
        # error de montaje, no una condición de ejecución.
        raise RuntimeError(f"Rutas duplicadas en la API v1: {duplicadas}")

    total = len(rutas_registradas())
    try:
        with engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        base_ok = True
    except Exception as exc:  # pragma: no cover - depende del entorno
        base_ok = False
        log.warning("base_de_datos_no_disponible_al_arrancar", error=str(exc))

    log.info(
        "atenea_arrancada",
        entorno=settings.environment,
        rutas=total,
        base_de_datos="ok" if base_ok else "sin conexión",
        proveedor_ia=settings.ai_provider,
        proveedor_embeddings=settings.embeddings_provider,
    )
    yield
    engine.dispose()
    log.info("atenea_detenida")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=DESCRIPCION,
    summary="Convierte cualquier conocimiento en una aventura.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=ciclo_de_vida,
)

# --------------------------------------------------------------------------
# CORS: el cliente Flutter en web (desarrollo) y los orígenes configurados.
# En móvil no hay origen, así que CORS no aplica.
# --------------------------------------------------------------------------
_origenes: list[str] = list(getattr(settings, "cors_origins", []) or [])
if settings.environment == "development" and not _origenes:
    _origenes = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5000",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:8080",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origenes or ["*"],
    allow_origin_regex=r"http://localhost:\d+" if settings.environment == "development" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)


@app.middleware("http")
async def contexto_de_peticion(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Asigna un identificador a cada petición y registra su resultado."""
    request_id = request.headers.get("X-Request-Id") or new_request_id()
    bind_request_context(request_id=request_id, method=request.method, path=request.url.path)
    inicio = time.perf_counter()
    try:
        respuesta = await call_next(request)
    except Exception:
        log.exception("peticion_fallida", ruta=request.url.path)
        clear_request_context()
        raise
    duracion_ms = round((time.perf_counter() - inicio) * 1000, 2)
    respuesta.headers["X-Request-Id"] = request_id
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
        log.info(
            "peticion",
            estado=respuesta.status_code,
            duracion_ms=duracion_ms,
        )
    clear_request_context()
    return respuesta


register_exception_handlers(app)
app.include_router(api_v1)


@app.get("/api/v1/health", tags=["salud"], summary="Salud del servicio")
def salud() -> dict[str, Any]:
    """Comprobación de vida usada por Railway y por el cliente (§7.9)."""
    try:
        with engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        base = "ok"
    except Exception:
        base = "error"
    return {
        "status": "ok" if base == "ok" else "degraded",
        "database": base,
        "version": app.version,
        "environment": settings.environment,
    }


@app.get("/", include_in_schema=False)
def raiz() -> dict[str, str]:
    """Cortesía: apunta a la documentación."""
    return {
        "servicio": settings.app_name,
        "documentacion": "/docs",
        "salud": "/api/v1/health",
    }
