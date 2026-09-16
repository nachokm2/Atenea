"""Pruebas de autenticación y cuenta (§7.1).

Cubren el camino feliz (registro y login), los fallos del contrato (correo
duplicado, credenciales incorrectas, token ausente), la **rotación** del refresh
token con revocación del anterior, la **detección de reuso** que corta la cadena
y la baja de cuenta.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.core.security import hash_refresh_token
from app.models.enums import EventType
from app.models.gamification import DomainEvent
from app.models.identity import RefreshToken, User, UserSettings

pytestmark = pytest.mark.db


def _fila_token(db, token: str) -> RefreshToken | None:
    """Fila de `refresh_tokens` correspondiente a un token en claro."""
    return db.execute(
        sa.select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token))
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------


def test_registro_feliz_crea_usuario_ajustes_y_tokens(cliente, db, correo, password):
    """`POST /auth/register` devuelve el par de tokens y deja los ajustes creados."""
    respuesta = cliente.post(
        "/api/v1/auth/register",
        json={"email": correo.upper(), "password": password, "timezone": "America/Santiago"},
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["expires_in"] > 0
    assert cuerpo["access_token"] and cuerpo["refresh_token"]
    # El correo se normaliza a minúsculas (CHECK `email = lower(email)`).
    assert cuerpo["user"]["email"] == correo.lower()
    assert cuerpo["user"]["role"] == "learner"
    assert "password_hash" not in cuerpo["user"]

    usuario = db.execute(sa.select(User).where(User.email == correo.lower())).scalar_one()
    assert usuario.password_hash and usuario.password_hash != password
    assert db.execute(
        sa.select(UserSettings).where(UserSettings.user_id == usuario.id)
    ).scalar_one_or_none() is not None
    assert db.execute(
        sa.select(DomainEvent).where(
            DomainEvent.user_id == usuario.id,
            DomainEvent.event_type == EventType.USER_REGISTERED,
        )
    ).scalar_one_or_none() is not None


def test_registro_con_correo_duplicado_falla(cliente, correo, password, registrado):
    """El segundo registro con el mismo correo responde `409 EMAIL_ALREADY_EXISTS`."""
    respuesta = cliente.post(
        "/api/v1/auth/register", json={"email": correo, "password": password}
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_registro_rechaza_una_contrasena_debil(cliente, correo):
    """Una contraseña sin mayúscula ni dígito es `422 VALIDATION_ERROR` con detalle."""
    respuesta = cliente.post("/api/v1/auth/register", json={"email": correo, "password": "atenea"})

    assert respuesta.status_code == 422
    error = respuesta.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["field_errors"]
    assert all(fallo["field"] == "password" for fallo in error["field_errors"])


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_feliz_devuelve_tokens_y_marca_last_login(cliente, db, correo, password, registrado):
    """`POST /auth/login` emite un par nuevo y actualiza `users.last_login_at`."""
    respuesta = cliente.post("/api/v1/auth/login", json={"email": correo, "password": password})

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["refresh_token"] != registrado["refresh_token"]

    usuario = db.execute(sa.select(User).where(User.email == correo)).scalar_one()
    assert usuario.last_login_at is not None


def test_login_con_contrasena_incorrecta_falla(cliente, correo, registrado):
    """Una contraseña equivocada responde `401 INVALID_CREDENTIALS`."""
    respuesta = cliente.post(
        "/api/v1/auth/login", json={"email": correo, "password": "OtraClave123"}
    )

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_con_correo_inexistente_no_filtra_la_existencia(cliente, password):
    """Un correo desconocido devuelve el mismo error que una contraseña mala."""
    respuesta = cliente.post(
        "/api/v1/auth/login", json={"email": "nadie@atenea-qa.cl", "password": password}
    )

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["code"] == "INVALID_CREDENTIALS"


# ---------------------------------------------------------------------------
# Rotación y reuso del refresh token
# ---------------------------------------------------------------------------


def test_refresh_rota_el_token_y_revoca_el_anterior(cliente, db, registrado):
    """El refresco emite un par nuevo, revoca el viejo y lo encadena al sucesor."""
    viejo = registrado["refresh_token"]

    respuesta = cliente.post("/api/v1/auth/refresh", json={"refresh_token": viejo})

    assert respuesta.status_code == 200, respuesta.text
    nuevo = respuesta.json()["refresh_token"]
    assert nuevo != viejo

    fila_vieja = _fila_token(db, viejo)
    fila_nueva = _fila_token(db, nuevo)
    assert fila_vieja is not None and fila_vieja.revoked_at is not None
    assert fila_nueva is not None and fila_nueva.revoked_at is None
    assert fila_vieja.replaced_by_id == fila_nueva.id


def test_reutilizar_un_refresh_revocado_corta_la_cadena(cliente, db, registrado):
    """Reusar un token ya rotado es `401 TOKEN_REUSE_DETECTED` y revoca toda la cadena."""
    viejo = registrado["refresh_token"]
    nuevo = cliente.post("/api/v1/auth/refresh", json={"refresh_token": viejo}).json()[
        "refresh_token"
    ]

    respuesta = cliente.post("/api/v1/auth/refresh", json={"refresh_token": viejo})

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["code"] == "TOKEN_REUSE_DETECTED"

    # El sucesor también queda revocado: la cadena entera cae.
    fila_nueva = _fila_token(db, nuevo)
    assert fila_nueva is not None and fila_nueva.revoked_at is not None
    assert cliente.post("/api/v1/auth/refresh", json={"refresh_token": nuevo}).status_code == 401


def test_refresh_desconocido_es_401(cliente):
    """Un refresh que no existe en la base no dice por qué falla."""
    respuesta = cliente.post("/api/v1/auth/refresh", json={"refresh_token": "no-existe"})

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["code"] == "UNAUTHORIZED"


def test_logout_revoca_el_refresh_recibido(cliente, db, registrado, autorizacion):
    """`POST /auth/logout` deja el token inservible para futuros refrescos."""
    token = registrado["refresh_token"]

    respuesta = cliente.post(
        "/api/v1/auth/logout", json={"refresh_token": token}, headers=autorizacion
    )

    assert respuesta.status_code == 204
    fila = _fila_token(db, token)
    assert fila is not None and fila.revoked_at is not None


# ---------------------------------------------------------------------------
# Sesión actual
# ---------------------------------------------------------------------------


def test_me_exige_token(cliente):
    """`GET /auth/me` sin cabecera `Authorization` responde `401 UNAUTHORIZED`."""
    respuesta = cliente.get("/api/v1/auth/me")

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_con_token_invalido_es_401(cliente):
    """Un Bearer que no es un JWT de Atenea también es `401`."""
    respuesta = cliente.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer esto-no-es-un-jwt"}
    )

    assert respuesta.status_code == 401


def test_me_devuelve_el_estado_de_onboarding(cliente, autorizacion, registrado):
    """Sin personaje ni ruta, `has_character` y `has_path` son `false`."""
    respuesta = cliente.get("/api/v1/auth/me", headers=autorizacion)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["user"]["id"] == registrado["user"]["id"]
    assert cuerpo["has_character"] is False
    assert cuerpo["has_path"] is False
    assert cuerpo["character"] is None
    assert cuerpo["settings"]["theme"] == "system"


# ---------------------------------------------------------------------------
# Contraseña y baja
# ---------------------------------------------------------------------------


def test_cambiar_contrasena_revoca_todos_los_refresh(
    cliente, db, correo, password, registrado, autorizacion
):
    """Cambiar la contraseña cierra todas las sesiones y la nueva clave ya sirve."""
    nueva = "OtraClaveSegura9"

    respuesta = cliente.post(
        "/api/v1/auth/password",
        json={"current_password": password, "new_password": nueva},
        headers=autorizacion,
    )

    assert respuesta.status_code == 204
    fila = _fila_token(db, registrado["refresh_token"])
    assert fila is not None and fila.revoked_at is not None
    assert (
        cliente.post(
            "/api/v1/auth/refresh", json={"refresh_token": registrado["refresh_token"]}
        ).status_code
        == 401
    )
    assert cliente.post("/api/v1/auth/login", json={"email": correo, "password": nueva}).status_code == 200


def test_cambiar_contrasena_exige_la_actual(cliente, autorizacion):
    """Sin la contraseña actual correcta no se cambia nada."""
    respuesta = cliente.post(
        "/api/v1/auth/password",
        json={"current_password": "Incorrecta123", "new_password": "OtraClaveSegura9"},
        headers=autorizacion,
    )

    assert respuesta.status_code == 401
    assert respuesta.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_borrar_cuenta_elimina_de_verdad(cliente, db, correo, password, registrado, autorizacion):
    """`DELETE /auth/account` deja la cuenta inservible: no autentica ni conserva el correo."""
    usuario_id = registrado["user"]["id"]

    respuesta = cliente.delete("/api/v1/auth/account", headers=autorizacion)
    assert respuesta.status_code == 204

    usuario = db.get(User, usuario_id)
    assert usuario is not None
    assert usuario.deleted_at is not None
    assert usuario.is_active is False
    assert usuario.password_hash is None
    assert usuario.email != correo  # el correo queda liberado

    # Ni el access token vivo ni el login ni el refresh vuelven a funcionar.
    assert cliente.get("/api/v1/auth/me", headers=autorizacion).status_code == 401
    assert (
        cliente.post("/api/v1/auth/login", json={"email": correo, "password": password}).status_code
        == 401
    )
    assert (
        cliente.post(
            "/api/v1/auth/refresh", json={"refresh_token": registrado["refresh_token"]}
        ).status_code
        == 401
    )
    assert db.execute(
        sa.select(DomainEvent).where(
            DomainEvent.user_id == usuario.id, DomainEvent.event_type == EventType.USER_DELETED
        )
    ).scalar_one_or_none() is not None

    # Y el correo se puede volver a registrar.
    assert (
        cliente.post(
            "/api/v1/auth/register", json={"email": correo, "password": password}
        ).status_code
        == 201
    )


def test_borrar_cuenta_tambien_borra_el_material(cliente, db, registrado, autorizacion):
    """Irse del Reino se lleva lo que uno subió.

    No pasaba. `borrar_cuenta` emitía `USER_DELETED` y su propio docstring
    afirmaba que «`ingestion` consume para purgar sus documentos», pero ese
    consumidor no existía en ninguna parte: los archivos del aprendiz se quedaban
    en el disco y en la base para siempre aunque hubiera pedido irse. Con una ley
    de datos personales encima, eso no es una deuda técnica cualquiera.

    El binario no se borra en este instante: se marca el borrado lógico y se fija
    `purge_after`, y el mantenimiento del worker lo retira del disco al vencer el
    plazo. Es el mismo camino que borrar un documento a mano, para que el plazo de
    retención sea uno solo.
    """
    from app.models.ingestion import Document
    from app.modules.ingestion import servicio as ingestion

    usuario_id = uuid.UUID(registrado["user"]["id"])
    biblioteca = ingestion.biblioteca_por_defecto(db, usuario_id)
    documento = ingestion.pegar_texto(
        db,
        usuario_id=usuario_id,
        titulo="Apuntes de SQL",
        texto="SELECT * FROM alumnos; " * 60,
        idempotency_key=f"pegar:{uuid.uuid4()}",
        knowledge_base_id=biblioteca.id,
    ).document
    db.flush()
    assert documento.deleted_at is None

    respuesta = cliente.delete("/api/v1/auth/account", headers=autorizacion)
    assert respuesta.status_code == 204

    db.refresh(documento)
    assert documento.deleted_at is not None, "el material sigue vivo tras la baja"
    assert documento.purge_after is not None, "sin plazo, el worker no lo borrará nunca"

    # Y el evento cuenta cuántos se llevó por delante, para que la baja sea
    # auditable sin tener que mirar la tabla de documentos.
    evento = db.execute(
        sa.select(DomainEvent).where(
            DomainEvent.user_id == usuario_id,
            DomainEvent.event_type == EventType.USER_DELETED,
        )
    ).scalar_one()
    assert evento.payload["documents_deleted"] == 1
    assert db.execute(
        sa.select(sa.func.count(Document.id)).where(
            Document.user_id == usuario_id, Document.deleted_at.is_(None)
        )
    ).scalar_one() == 0
