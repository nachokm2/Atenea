"""`POST /devices/push-token`: la credencial de notificaciones del dispositivo.

El contrato agrupa esta ruta con las notificaciones (§7.9), pero el dato vive en
`users.push_token` y esa tabla es de `identity`, así que el endpoint se sirve
desde aquí.

Lo que se prueba no es solo que funcione, sino que el valor del token **nunca
vuelva** en ninguna respuesta: es una credencial, no un ajuste más.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture()
def autorizado(cliente, registrado):
    """Cliente con sesión iniciada."""
    cliente.headers["Authorization"] = f"Bearer {registrado['access_token']}"
    return cliente


# ---------------------------------------------------------------------------
# POST /devices/push-token
# ---------------------------------------------------------------------------


def test_registrar_el_token_del_dispositivo(autorizado):
    """Queda guardado y los ajustes lo reflejan como un sí o un no."""
    respuesta = autorizado.post(
        "/api/v1/devices/push-token", json={"push_token": "fcm-de-prueba"}
    )

    assert respuesta.status_code == 204
    assert autorizado.get("/api/v1/settings").json()["has_push_token"] is True


def test_el_valor_del_token_nunca_vuelve_al_cliente(autorizado):
    """Es una credencial del dispositivo: §8.7 prohíbe serializarla."""
    secreto = f"fcm-secreto-{uuid.uuid4().hex}"
    autorizado.post("/api/v1/devices/push-token", json={"push_token": secreto})

    assert secreto not in autorizado.get("/api/v1/settings").text
    assert secreto not in autorizado.get("/api/v1/auth/me").text


def test_enviar_nulo_da_de_baja_el_dispositivo(autorizado):
    """Es la forma de decir "ya no me avises aquí" sin borrar la cuenta."""
    autorizado.post("/api/v1/devices/push-token", json={"push_token": "fcm-de-prueba"})

    respuesta = autorizado.post("/api/v1/devices/push-token", json={"push_token": None})

    assert respuesta.status_code == 204
    assert autorizado.get("/api/v1/settings").json()["has_push_token"] is False


def test_sin_sesion_no_se_puede_registrar_un_token(cliente):
    """Un token de push sin dueño no significa nada."""
    respuesta = cliente.post("/api/v1/devices/push-token", json={"push_token": "x"})

    assert respuesta.status_code == 401
