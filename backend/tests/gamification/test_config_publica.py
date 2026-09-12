"""`GET /config/public`: lo que la app necesita para dibujar sin preguntar.

Es, junto a la de salud, la única ruta sin sesión del contrato (§7.9). La app la
pide antes de que nadie entre, y de ahí saca los precios, los umbrales, los
colores de rareza y la curva de niveles. Nada de eso puede estar escrito en el
cliente: si lo estuviera, calibrar la economía obligaría a publicar una versión
nueva en las tiendas.

La otra mitad de lo que se prueba aquí es lo que **no** debe salir. Las reglas
anti-abuso (multiplicadores por repetición, topes diarios, tiempos mínimos
plausibles) son públicas solo en el sentido de que existen: publicar sus valores
sería un manual para saltárselas.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import register_exception_handlers
from app.models.enums import LevelScope
from app.models.gamification import LevelDefinition
from app.modules.gamification.router import router


@pytest.fixture()
def cliente(db: Session) -> TestClient:
    """Cliente HTTP con el router de gamificación y la sesión de prueba."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as cliente_http:
        yield cliente_http


@pytest.fixture()
def hay_curva(db: Session) -> int:
    """Cuántos niveles hay sembrados en la curva global."""
    return int(
        db.execute(
            sa.select(sa.func.count())
            .select_from(LevelDefinition)
            .where(LevelDefinition.scope == LevelScope.GLOBAL)
        ).scalar_one()
    )


def test_no_exige_sesion(cliente: TestClient) -> None:
    """Se pide antes de entrar: sin cabecera de autorización debe responder."""
    respuesta = cliente.get("/api/v1/config/public")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["config_version"] >= 0
    assert cuerpo["values"], "debe traer al menos una clave pública"


def test_devuelve_la_version_en_la_cabecera(cliente: TestClient) -> None:
    """`X-Config-Version` le dice a la app cuándo recargar (§8.4)."""
    respuesta = cliente.get("/api/v1/config/public")

    assert respuesta.headers.get("X-Config-Version") is not None
    assert int(respuesta.headers["X-Config-Version"]) == respuesta.json()["config_version"]


def test_las_reglas_anti_abuso_no_se_publican(cliente: TestClient) -> None:
    """Publicar sus valores sería enseñar a saltárselas."""
    valores = cliente.get("/api/v1/config/public").json()["values"]

    filtradas = [
        clave
        for clave in valores
        if any(
            marca in clave
            for marca in ("repeat_multipliers", "softcap", "min_time", "daily_cap")
        )
    ]
    assert filtradas == [], f"se filtraron reglas anti-abuso: {filtradas}"


def test_la_curva_de_niveles_llega_ordenada(cliente: TestClient, hay_curva: int) -> None:
    """Sin la curva, la app no sabe cuánto falta para el siguiente nivel."""
    niveles = cliente.get("/api/v1/config/public").json()["levels"]

    assert len(niveles) == hay_curva
    if not niveles:
        pytest.skip("la curva no está sembrada en esta suite")

    assert [n["level"] for n in niveles] == sorted(n["level"] for n in niveles)
    acumulados = [n["xp_required"] for n in niveles]
    assert acumulados == sorted(acumulados), "el XP acumulado nunca decrece"
    assert all(n["rank_title"] for n in niveles), "cada nivel necesita su título de rango"


def test_cada_valor_publico_es_serializable(cliente: TestClient) -> None:
    """Lo que sale tiene que poder viajar como JSON tal cual."""
    import json

    valores = cliente.get("/api/v1/config/public").json()["values"]

    json.dumps(valores)  # no debe lanzar
    assert all(isinstance(clave, str) for clave in valores)
