"""Punto de entrada de la API de Atenea.

Arranque:

    python -m uvicorn app.main:app --reload --port 8000

Monta la API v1 completa (CONTRACT.md §7), los manejadores de error del núcleo,
el registro estructurado con identificador de petición y CORS para el cliente
Flutter. El trabajo pesado (ingesta de documentos y generación con IA) no vive
aquí: lo ejecuta el worker (``python -m app.worker.principal``).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import api_v1, rutas_duplicadas, rutas_registradas
from app.core.config import settings
from app.core.db import engine
from app.core.errors import register_exception_handlers
from app.core.limites import montar_limitador
from app.core.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
    new_request_id,
)
from app.core.security import decode_access_token
from app.worker.principal import bucle as bucle_del_worker

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
async def ciclo_de_vida(app: FastAPI):  # noqa: ARG001 - firma fijada por quien llama
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

    parar_worker = threading.Event()
    hilo_worker: threading.Thread | None = None
    if settings.worker_en_proceso:
        # El procesador de trabajos dentro de la propia API.
        #
        # No es una optimización: es lo único que funciona mientras el material
        # del aprendiz viva en disco. Un volumen se monta en **un** servicio, así
        # que una API y un worker separados no comparten archivos: el aprendiz
        # sube un PDF, el worker no lo encuentra y la ingesta falla siempre.
        #
        # El día que el material viva en un bucket, esto se apaga y el worker
        # vuelve a ser su propio servicio, que escala mejor.
        hilo_worker = threading.Thread(
            target=bucle_del_worker,
            kwargs={"parar": parar_worker},
            name="atenea-worker",
            daemon=True,
        )
        hilo_worker.start()
        log.info("worker_en_proceso_arrancado")

    yield

    if hilo_worker is not None:
        parar_worker.set()
        hilo_worker.join(timeout=20)
        log.info("worker_en_proceso_detenido", vivo=hilo_worker.is_alive())
    engine.dispose()
    log.info("atenea_detenida")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=DESCRIPCION,
    summary="Convierte cualquier conocimiento en una aventura.",
    # El esquema completo de la API es un mapa del Reino: útil mientras se
    # construye, innecesario en producción, donde solo ayuda a quien busca por
    # dónde entrar.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=ciclo_de_vida,
)

# --------------------------------------------------------------------------
# CORS: el cliente Flutter en web (desarrollo) y los orígenes configurados.
# En móvil no hay origen, así que CORS no aplica.
# --------------------------------------------------------------------------
_origenes: list[str] = list(settings.cors_origins or [])
if settings.environment == "development" and not _origenes:
    _origenes = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5000",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:8080",
    ]

# En producción `cors_origins` no puede estar vacío: el arranque lo exige, así
# que aquí nunca se cae al comodín. El comodín con credenciales permitiría a
# cualquier página hablar con la API en nombre de quien la visite.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origenes or ([] if settings.is_production else ["*"]),
    allow_origin_regex=(
        r"http://localhost:\d+" if settings.environment == "development" else None
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id", "X-Config-Version"],
)


def usuario_del_token(request: Request) -> str | None:
    """Identificador del usuario de la petición, si trae un token legible.

    Es una lectura barata y **sin autoridad**: no autoriza nada, solo sirve para
    que el freno de peticiones cuente a cada héroe por separado en vez de meter a
    toda una red detrás de la misma dirección. Un token inválido o caducado se
    trata como si no hubiera sesión, y quien decide de verdad sigue siendo la
    dependencia de autenticación de cada ruta.
    """
    cabecera = request.headers.get("Authorization") or ""
    if not cabecera.lower().startswith("bearer "):
        return None
    try:
        carga = decode_access_token(cabecera[7:].strip())
    except Exception:
        return None
    sujeto = carga.get("sub")
    return str(sujeto) if sujeto else None


@app.middleware("http")
async def contexto_de_peticion(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Asigna un identificador a cada petición y registra su resultado."""
    request_id = request.headers.get("X-Request-Id") or new_request_id()
    request.state.request_id = request_id
    # El freno de peticiones cuenta por usuario cuando hay sesión y por dirección
    # cuando no la hay. Se resuelve aquí, antes de las dependencias, porque el
    # middleware del limitador corre antes que ellas.
    request.state.user_id = usuario_del_token(request)
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
montar_limitador(app)
app.include_router(api_v1)


@app.get("/api/v1/health", tags=["salud"], summary="Salud del servicio")
@app.get("/health", include_in_schema=False)
def salud(response: Response) -> dict[str, Any]:
    """Comprobación de vida usada por la plataforma y por el cliente (§7.9).

    Responde en dos rutas a propósito. `/api/v1/health` es la del contrato, la
    que consume la app; `/health` es la que esperan por convención los balanceadores
    y las plataformas de despliegue, que no saben del prefijo de versión. Apuntar
    el chequeo de salud a una ruta que devuelve 404 pone al servicio en un bucle
    de reinicios con la aplicación perfectamente sana.

    Si la base no responde, esto **no** es un 200: un servicio que no puede leer
    ni una fila no está vivo, y decir que sí impide que nadie se entere.
    """
    try:
        with engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        base = "ok"
    except Exception:
        base = "error"
    if base != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
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
