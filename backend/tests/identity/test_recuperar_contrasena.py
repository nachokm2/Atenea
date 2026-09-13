"""Recuperar la contraseña olvidada (`POST /auth/password/forgot` y `/reset`).

Hasta ahora, olvidar la contraseña significaba perder la cuenta: cambiarla exigía
la sesión y la contraseña actual, y darse de baja también exigía la sesión. La
pantalla de acceso tenía el botón y una hoja que prometía una versión futura.

Lo que se prueba aquí no es solo que funcione, sino las tres cosas que lo hacen
seguro: que el formulario no revele quién tiene cuenta, que el permiso se gaste, y
que recuperar la contraseña eche a quien estuviera dentro.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.identity import PasswordReset, RefreshToken

NUEVA = "Reino2026Rescatado"


@pytest.fixture()
def correos(monkeypatch) -> list[dict[str, str]]:
    """Intercepta el correo saliente en vez de enviarlo."""
    enviados: list[dict[str, str]] = []

    def _capturar(*, destinatario: str, asunto: str, cuerpo: str) -> None:
        enviados.append({"destinatario": destinatario, "asunto": asunto, "cuerpo": cuerpo})

    from app.modules.identity import servicio_auth

    monkeypatch.setattr(servicio_auth.correo, "enviar", _capturar)
    return enviados


def _permiso(correos: list[dict[str, str]]) -> str:
    """Saca el token del enlace que viajó en el correo."""
    assert correos, "no se envió ningún correo"
    encontrado = re.search(r"token=([A-Za-z0-9_\-]+)", correos[-1]["cuerpo"])
    assert encontrado, correos[-1]["cuerpo"]
    return encontrado.group(1)


# ---------------------------------------------------------------------------
# Pedir el enlace
# ---------------------------------------------------------------------------


def test_pedirlo_envia_el_enlace(cliente, correo, registrado, correos) -> None:
    """Con una cuenta real, sale un correo con el enlace."""
    respuesta = cliente.post("/api/v1/auth/password/forgot", json={"email": correo})

    assert respuesta.status_code == 204
    assert len(correos) == 1
    assert correos[0]["destinatario"] == correo
    assert "token=" in correos[0]["cuerpo"]


def test_un_correo_desconocido_responde_igual_y_no_envia_nada(cliente, correos) -> None:
    """El formulario no puede ser una lista de cuentas válidas.

    Si respondiera distinto según exista la cuenta, cualquiera podría ir
    probando direcciones y quedarse con las que sí están registradas.
    """
    respuesta = cliente.post(
        "/api/v1/auth/password/forgot", json={"email": "nadie@atenea-qa.cl"}
    )

    assert respuesta.status_code == 204
    assert correos == []


def test_pedirlo_dos_veces_deja_vivo_solo_el_ultimo(
    cliente, db: Session, correo, registrado, correos
) -> None:
    """Quien no ve llegar el primero pide otro, y espera que sirva el nuevo."""
    cliente.post("/api/v1/auth/password/forgot", json={"email": correo})
    primero = _permiso(correos)
    cliente.post("/api/v1/auth/password/forgot", json={"email": correo})
    segundo = _permiso(correos)

    assert primero != segundo
    caducado = cliente.post(
        "/api/v1/auth/password/reset", json={"token": primero, "new_password": NUEVA}
    )
    assert caducado.status_code == 401
    bueno = cliente.post(
        "/api/v1/auth/password/reset", json={"token": segundo, "new_password": NUEVA}
    )
    assert bueno.status_code == 204


# ---------------------------------------------------------------------------
# Usar el enlace
# ---------------------------------------------------------------------------


def test_el_enlace_deja_entrar_con_la_contrasena_nueva(
    cliente, correo, password, registrado, correos
) -> None:
    """El camino entero: pedirlo, usarlo y volver a entrar."""
    cliente.post("/api/v1/auth/password/forgot", json={"email": correo})

    cambio = cliente.post(
        "/api/v1/auth/password/reset",
        json={"token": _permiso(correos), "new_password": NUEVA},
    )
    assert cambio.status_code == 204

    vieja = cliente.post("/api/v1/auth/login", json={"email": correo, "password": password})
    nueva = cliente.post("/api/v1/auth/login", json={"email": correo, "password": NUEVA})

    assert vieja.status_code == 401, "la contraseña vieja tiene que dejar de servir"
    assert nueva.status_code == 200


def test_el_permiso_solo_sirve_una_vez(cliente, correo, registrado, correos) -> None:
    """Un enlace gastado no puede volver a abrir la cuenta."""
    cliente.post("/api/v1/auth/password/forgot", json={"email": correo})
    permiso = _permiso(correos)

    assert cliente.post(
        "/api/v1/auth/password/reset", json={"token": permiso, "new_password": NUEVA}
    ).status_code == 204
    segunda = cliente.post(
        "/api/v1/auth/password/reset",
        json={"token": permiso, "new_password": "OtraDistinta2026"},
    )

    assert segunda.status_code == 401


def test_un_permiso_caducado_no_sirve(
    cliente, db: Session, correo, registrado, correos
) -> None:
    """Es una llave a la cuenta viajando por correo: caduca pronto."""
    cliente.post("/api/v1/auth/password/forgot", json={"email": correo})
    permiso = _permiso(correos)
    db.execute(
        sa.update(PasswordReset).values(expires_at=utcnow() - dt.timedelta(minutes=1))
    )
    db.flush()

    respuesta = cliente.post(
        "/api/v1/auth/password/reset", json={"token": permiso, "new_password": NUEVA}
    )

    assert respuesta.status_code == 401


def test_un_permiso_inventado_no_sirve(cliente) -> None:
    """Probar enlaces al azar no puede abrir ninguna cuenta."""
    respuesta = cliente.post(
        "/api/v1/auth/password/reset",
        json={"token": "inventado-de-cabo-a-rabo", "new_password": NUEVA},
    )

    assert respuesta.status_code == 401


def test_recuperar_la_cuenta_echa_a_quien_estuviera_dentro(
    cliente, db: Session, correo, registrado: dict[str, Any], correos
) -> None:
    """Si la cuenta estuvo en manos de otro, cambiar la clave sin echarlo no sirve."""
    refresco = registrado["refresh_token"]
    cliente.post("/api/v1/auth/password/forgot", json={"email": correo})
    cliente.post(
        "/api/v1/auth/password/reset",
        json={"token": _permiso(correos), "new_password": NUEVA},
    )

    reintento = cliente.post("/api/v1/auth/refresh", json={"refresh_token": refresco})

    assert reintento.status_code == 401
    vivos = db.execute(
        sa.select(sa.func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.revoked_at.is_(None))
    ).scalar_one()
    assert vivos == 0


def test_la_contrasena_nueva_tambien_tiene_que_ser_fuerte(
    cliente, correo, registrado, correos
) -> None:
    """Recuperar la cuenta no es excusa para volver a una clave débil."""
    cliente.post("/api/v1/auth/password/forgot", json={"email": correo})

    respuesta = cliente.post(
        "/api/v1/auth/password/reset",
        json={"token": _permiso(correos), "new_password": "atenea"},
    )

    assert respuesta.status_code == 422


def test_el_token_en_claro_nunca_se_guarda(
    cliente, db: Session, correo, registrado, correos
) -> None:
    """Quien lea la base no puede restablecer la contraseña de nadie."""
    cliente.post("/api/v1/auth/password/forgot", json={"email": correo})
    permiso = _permiso(correos)

    guardados = db.execute(sa.select(PasswordReset.token_hash)).scalars().all()

    assert guardados
    assert permiso not in guardados
    assert all(len(h) == 64 for h in guardados), "se guarda el SHA-256, no el token"
