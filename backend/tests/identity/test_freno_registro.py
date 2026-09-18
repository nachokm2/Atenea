"""El freno de `/auth/register` (§8.7).

Salió buscando por qué no se podía registrar una cuenta —no era eso, pero estaba
ahí—: `/auth/login` llevaba su freno y `/auth/register` no, así que le aplicaba
solo el general de sesenta por minuto.

Y el argumento del acceso vale igual aquí. Registrar también verifica y hashea
con bcrypt de coste 12 sobre un backend **síncrono** con cinco conexiones, así
que sesenta registros por minuto y por IP son sesenta bcrypt encolados, más
sesenta filas de usuario. Abrir cuentas en masa salía barato.

**Ninguna prueba de todo el proyecto ejercitaba un freno.** Esta es la primera, y
por eso empieza por encenderlo: el limitador se apaga solo en el entorno de
pruebas (`limites.py`, `enabled=settings.environment != "test"`), porque un caso
normal llama veinte veces a la misma ruta en el mismo segundo y no está midiendo
esto. Sin encenderlo a mano, una prueba de freno pasa con el freno quitado.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from app.core import limites

pytestmark = pytest.mark.db


@pytest.fixture
def freno_encendido(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Enciende el freno y le da una ventana limpia, solo para esta prueba.

    La ventana es propia —no la global— para que lo que cuente aquí no se le
    sume a ninguna otra prueba ni al revés. `comprobar` resuelve `_ventana` por
    nombre en cada llamada, así que sustituir el atributo del módulo basta.
    """
    monkeypatch.setattr(limites, "_ventana", MovingWindowRateLimiter(MemoryStorage()))
    monkeypatch.setattr(limites.limitador, "enabled", True)
    yield


def _registrar(cliente, password: str):
    """Un registro con un correo nuevo cada vez."""
    return cliente.post(
        "/api/v1/auth/register",
        json={
            "email": f"freno-{uuid.uuid4().hex[:12]}@atenea-qa.cl",
            "password": password,
            "timezone": "America/Santiago",
        },
    )


def test_el_registro_se_corta_al_pasar_el_tope(cliente, password, freno_encendido):
    """Diez por minuto pasan; el once recibe 429 con el sobre del contrato.

    Comprueba el código del catálogo y no solo el estado: `RATE_LIMITED` era el
    único código del catálogo de errores que no lanzaba nadie, y el cliente
    distingue por código, no por número.
    """
    for intento in range(10):
        respuesta = _registrar(cliente, password)
        assert respuesta.status_code == 201, f"el intento {intento + 1} ya venía frenado"

    frenada = _registrar(cliente, password)

    assert frenada.status_code == 429
    cuerpo = frenada.json()
    assert cuerpo["error"]["code"] == "RATE_LIMITED"
    assert "retry_after_seconds" in cuerpo["error"]["details"]


def test_el_freno_del_registro_no_es_el_general(cliente, password, freno_encendido):
    """Sin freno propio, el registro aguantaría sesenta por minuto.

    Es la prueba que distingue el arreglo de lo que había: con el freno general
    de `rate_limit_default` los once registros de arriba pasarían todos. Fija el
    número para que quitar la dependencia del router se note.
    """
    from app.core.config import settings

    assert settings.rate_limit_register != settings.rate_limit_default
    assert settings.rate_limit_register.startswith("10/minute")
    # Dos ventanas: una para la ráfaga y otra para el goteo. Con una sola, diez
    # por minuto siguen siendo catorce mil cuentas al día.
    assert ";" in settings.rate_limit_register


def test_el_acceso_tiene_su_propio_cubo(cliente, correo, password, freno_encendido):
    """Agotar el registro no puede dejar a nadie sin poder iniciar sesión.

    La ventana se cuenta por clave **y ruta** (`request.url.path`), así que los
    dos endpoints no comparten cubo. Si lo compartieran, un abuso del registro
    dejaría fuera al aprendiz legítimo que solo quiere entrar, que es
    exactamente el daño que el freno viene a evitar.
    """
    # La cuenta con la que se entrará luego. Gasta uno de los diez del cubo.
    assert (
        cliente.post(
            "/api/v1/auth/register",
            json={"email": correo, "password": password, "timezone": "America/Santiago"},
        ).status_code
        == 201
    )
    for _ in range(9):
        assert _registrar(cliente, password).status_code == 201
    assert _registrar(cliente, password).status_code == 429

    entrada = cliente.post(
        "/api/v1/auth/login", json={"email": correo, "password": password}
    )
    assert entrada.status_code == 200, "el registro frenado arrastró al acceso"
