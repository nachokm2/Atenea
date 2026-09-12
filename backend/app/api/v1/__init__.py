"""Agregación de los routers de la API v1 (CONTRACT.md §7).

Cada módulo expone su ``router = APIRouter()`` **sin prefijo**: el prefijo
``/api/v1`` y las etiquetas de OpenAPI se aplican aquí, en un único lugar, para
que el mapa de rutas del contrato se pueda auditar de un vistazo.

El orden de montaje importa poco para el enrutado de FastAPI (las rutas son
literales o con parámetros bien delimitados), pero se mantiene el del contrato
para que ``/docs`` se lea en el mismo orden que §7.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.content.router import router as content_router
from app.modules.economy.router import router as economy_router
from app.modules.gamification.router import router as gamification_router
from app.modules.identity.router import router as identity_router
from app.modules.ingestion.router import router as ingestion_router
from app.modules.progress.router import router as progress_router

#: Prefijo obligatorio de la versión 1 de la API.
PREFIJO_V1 = "/api/v1"

api_v1 = APIRouter(prefix=PREFIJO_V1)

#: Routers montados, en el orden en que el contrato los documenta.
_MONTAJES: tuple[tuple[APIRouter, str], ...] = (
    (identity_router, "identidad"),
    (economy_router, "economía"),
    (content_router, "contenido"),
    (ingestion_router, "ingesta"),
    (progress_router, "progreso"),
    (gamification_router, "gamificación"),
)

for _router, _etiqueta in _MONTAJES:
    api_v1.include_router(_router, tags=[_etiqueta])


def rutas_registradas() -> list[tuple[str, str]]:
    """Devuelve ``(método, ruta)`` de todo lo montado, para auditoría.

    Se usa en el arranque y en las pruebas de contrato para comparar la API
    real contra las 75 rutas de §7 y detectar duplicados.
    """
    salida: list[tuple[str, str]] = []
    for ruta in api_v1.routes:
        metodos = sorted(getattr(ruta, "methods", set()) - {"HEAD", "OPTIONS"})
        for metodo in metodos:
            salida.append((metodo, getattr(ruta, "path", "")))
    return sorted(salida)


def rutas_duplicadas() -> list[tuple[str, str]]:
    """Pares ``(método, ruta)`` montados más de una vez."""
    vistas: dict[tuple[str, str], int] = {}
    for par in rutas_registradas():
        vistas[par] = vistas.get(par, 0) + 1
    return sorted(par for par, veces in vistas.items() if veces > 1)


__all__ = ["PREFIJO_V1", "api_v1", "rutas_duplicadas", "rutas_registradas"]
