"""Guardas de plataforma: lo que impide desplegar Atenea de forma peligrosa.

No son reglas de juego ni de contrato: son las condiciones bajo las que el
servidor se puede poner en internet. Están aquí, y no en el módulo de cada
dominio, porque no pertenecen a ninguno: pertenecen al arranque.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import MINIMO_SECRETO, SECRETO_DE_DESARROLLO, Settings
from app.core.limites import clave_de_cubo, freno


def _aplicacion():
    """Importa la aplicación **dentro** de la prueba, no al recolectar.

    Importar `app.main` en tiempo de colección deja a la suite de contenido sin
    su configuración de juego sembrada, que vive en una transacción de sesión.
    Es una fragilidad anterior a este archivo y merece arreglarse por su cuenta;
    mientras tanto, importarlo tarde evita contagiarla.
    """
    from app.main import app

    return app

# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------


def _produccion(**extra) -> dict:
    """Configuración de producción completa, sobre la que se rompe una cosa."""
    base = {
        "environment": "production",
        "jwt_secret": "x" * MINIMO_SECRETO,
        "ai_provider": "claude",
        "anthropic_api_key": "sk-de-mentira",
        "embeddings_provider": "voyage",
        "voyage_api_key": "vk-de-mentira",
        "cors_origins": ["https://atenea.cl"],
        "email_provider": "smtp",
    }
    base.update(extra)
    return base


def test_produccion_bien_configurada_arranca() -> None:
    """La guarda no puede ser tan estricta que impida desplegar de verdad."""
    ajustes = Settings(**_produccion())

    assert ajustes.is_production is True


def test_desarrollo_arranca_con_todo_por_defecto() -> None:
    """En local no se pide nada: los valores por defecto son para eso."""
    assert Settings(environment="development").is_production is False


@pytest.mark.parametrize(
    ("roto", "senal"),
    [
        ({"jwt_secret": SECRETO_DE_DESARROLLO}, "JWT_SECRET"),
        ({"jwt_secret": "corto"}, "JWT_SECRET"),
        ({"ai_provider": "mock"}, "AI_PROVIDER"),
        ({"anthropic_api_key": None}, "ANTHROPIC_API_KEY"),
        ({"embeddings_provider": "mock"}, "EMBEDDINGS_PROVIDER"),
        ({"voyage_api_key": None}, "VOYAGE_API_KEY"),
        ({"cors_origins": []}, "CORS_ORIGINS"),
        ({"email_provider": "consola"}, "EMAIL_PROVIDER"),
    ],
)
def test_produccion_mal_configurada_no_arranca(roto: dict, senal: str) -> None:
    """Cada pieza que falta impide el arranque **y se nombra** en el error.

    Un servidor mal configurado no falla: responde 200 y hace daño en silencio.
    Con el secreto publicado cualquiera firma un token ajeno; con el proveedor
    simulado el aprendiz recibe lecciones inventadas que parecen buenas. El
    único momento en que eso se puede ver es el arranque.
    """
    with pytest.raises(ValueError) as fallo:
        Settings(**_produccion(**roto))

    assert senal in str(fallo.value)


# ---------------------------------------------------------------------------
# Salud
# ---------------------------------------------------------------------------


def test_la_salud_responde_en_las_dos_rutas() -> None:
    """La del contrato y la que espera la plataforma de despliegue.

    Apuntar el chequeo de salud a una ruta que devuelve 404 pone el servicio en
    un bucle de reinicios con la aplicación perfectamente sana. Es exactamente
    lo que habría pasado en el primer despliegue.
    """
    with TestClient(_aplicacion()) as cliente:
        for ruta in ("/health", "/api/v1/health"):
            respuesta = cliente.get(ruta)
            assert respuesta.status_code == 200, ruta
            assert respuesta.json()["status"] == "ok", ruta


# ---------------------------------------------------------------------------
# Freno de peticiones
# ---------------------------------------------------------------------------


def test_el_freno_cuenta_por_usuario_cuando_hay_sesion() -> None:
    """Con la dirección sola, una red compartida se frenaría a sí misma."""

    class _Peticion:
        class state:  # noqa: N801 - imita `request.state`
            user_id = "abc"

    assert clave_de_cubo(_Peticion()) == "usuario:abc"


def test_el_freno_existe_para_las_rutas_que_el_contrato_nombra() -> None:
    """§8.7 fija cuatro límites; ninguno existía hasta ahora.

    Se comprueba en el esquema de rutas y no disparando peticiones, porque en
    pruebas el freno está desactivado a propósito.
    """
    rutas = {
        (r.path, metodo): r
        for r in _aplicacion().routes
        if hasattr(r, "methods")
        for metodo in r.methods
    }
    con_freno = {
        ("/api/v1/paths", "POST"),
        ("/api/v1/activities/{activity_id}/answers", "POST"),
        ("/api/v1/shop/purchase", "POST"),
        ("/api/v1/auth/login", "POST"),
        ("/api/v1/documents", "POST"),
    }

    for clave in con_freno:
        ruta = rutas.get(clave)
        assert ruta is not None, f"no existe la ruta {clave}"
        nombres = [d.call.__qualname__ for d in ruta.dependant.dependencies if d.call]
        assert any("freno" in n for n in nombres), f"{clave} no tiene freno"


def test_en_pruebas_el_freno_esta_desactivado() -> None:
    """Un caso puede llamar veinte veces a la misma ruta y no está midiendo esto."""
    comprobar = freno("1/minute")

    class _Peticion:
        class state:  # noqa: N801
            user_id = "quien-sea"

        class url:  # noqa: N801
            path = "/api/v1/algo"

    for _ in range(5):
        comprobar(_Peticion())
