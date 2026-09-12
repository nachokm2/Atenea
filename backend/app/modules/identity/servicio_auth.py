"""Autenticación: registro, login, rotación de refresh y cambio de contraseña.

Contrato §8.7:

- Contraseñas con `bcrypt` (`passlib`), coste 12. Nunca se registran ni se devuelven.
- Access token JWT (HS256) con `sub`, `role`, `exp`, `iat`, `jti`.
- Refresh token **opaco** de 256 bits, guardado solo como SHA-256, **rotatorio** y
  con **detección de reuso**: si llega un token ya revocado se corta la cadena
  entera del usuario y se responde `401 TOKEN_REUSE_DETECTED`.

El correo se normaliza a minúsculas y sin espacios antes de tocar la base: la
columna `users.email` tiene un `CHECK (email = lower(email))` y un único, así
que un registro duplicado se detecta también a nivel de base de datos y se
traduce a `409 EMAIL_ALREADY_EXISTS`.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import Conflict, InvalidCredentials, TokenReuseDetected, Unauthorized, ValidationFailed
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    refresh_token_expires_at,
    verify_password,
)
from app.core.time import is_valid_timezone, utcnow
from app.models.enums import AuthProvider, EventType, UserRole
from app.models.identity import RefreshToken, User
from app.modules.identity import servicio_usuario

#: Longitud mínima de la contraseña. bcrypt solo mira los primeros 72 bytes.
LARGO_MINIMO = 8
LARGO_MAXIMO = 128

#: Contraseñas prohibidas por obvias (lista corta: el resto lo cubren las reglas).
PROHIBIDAS: frozenset[str] = frozenset(
    {"12345678", "contrasena", "contraseña", "password", "atenea123", "qwertyui", "11111111"}
)

_MAYUSCULA = re.compile(r"[A-ZÁÉÍÓÚÑÜ]")
_MINUSCULA = re.compile(r"[a-záéíóúñü]")
_DIGITO = re.compile(r"\d")


@dataclass(slots=True)
class ParTokens:
    """Par de tokens emitido a un usuario, con el TTL del access en segundos."""

    access_token: str
    refresh_token: str
    expires_in: int
    user: User
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Normalización y validación
# ---------------------------------------------------------------------------


def normalizar_email(email: str) -> str:
    """Correo en minúsculas y sin espacios alrededor (lo exige el CHECK de la tabla)."""
    return email.strip().lower()


def validar_fuerza_contrasena(password: str, *, email: str | None = None) -> None:
    """Comprueba la fuerza mínima de la contraseña; lanza `VALIDATION_ERROR` si no pasa.

    Reglas: 8–128 caracteres, al menos una minúscula, una mayúscula y un dígito,
    y que no sea una contraseña obvia ni el propio correo.
    """
    problemas: list[str] = []
    if len(password) < LARGO_MINIMO:
        problemas.append(f"Debe tener al menos {LARGO_MINIMO} caracteres.")
    if len(password) > LARGO_MAXIMO:
        problemas.append(f"No puede superar los {LARGO_MAXIMO} caracteres.")
    if not _MINUSCULA.search(password):
        problemas.append("Debe incluir una letra minúscula.")
    if not _MAYUSCULA.search(password):
        problemas.append("Debe incluir una letra mayúscula.")
    if not _DIGITO.search(password):
        problemas.append("Debe incluir un número.")
    if password.lower() in PROHIBIDAS:
        problemas.append("Esa contraseña es demasiado común.")
    if email and password.lower() == normalizar_email(email):
        problemas.append("La contraseña no puede ser tu correo.")

    if problemas:
        raise ValidationFailed(
            "Esa contraseña es demasiado débil.",
            field_errors=[{"field": "password", "message": texto} for texto in problemas],
        )


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------


def buscar_por_email(db: Session, email: str) -> User | None:
    """Usuario activo (no borrado) con ese correo normalizado."""
    return db.execute(
        sa.select(User).where(User.email == normalizar_email(email), User.deleted_at.is_(None))
    ).scalar_one_or_none()


def _buscar_refresh(db: Session, token: str) -> RefreshToken | None:
    """Fila de `refresh_tokens` cuyo SHA-256 coincide con el token en claro."""
    return db.execute(
        sa.select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token))
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Emisión y revocación de tokens
# ---------------------------------------------------------------------------


def emitir_par(
    db: Session,
    usuario: User,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
    momento: dt.datetime | None = None,
) -> ParTokens:
    """Emite el access JWT y persiste un refresh opaco nuevo para el usuario."""
    instante = momento or utcnow()
    claro, huella = generate_refresh_token()
    fila = RefreshToken(
        user_id=usuario.id,
        token_hash=huella,
        issued_at=instante,
        expires_at=refresh_token_expires_at(instante),
        user_agent=(user_agent or None) and user_agent[:255],
        ip_address=(ip_address or None) and ip_address[:45],
    )
    db.add(fila)
    db.flush()

    acceso = create_access_token(usuario.id, role=usuario.role.value)
    return ParTokens(
        access_token=acceso,
        refresh_token=claro,
        expires_in=settings.jwt_access_ttl_min * 60,
        user=usuario,
    )


def revocar_refresh(db: Session, fila: RefreshToken, *, momento: dt.datetime | None = None) -> None:
    """Marca un refresh token como revocado (idempotente)."""
    if fila.revoked_at is None:
        fila.revoked_at = momento or utcnow()
        db.flush()


def revocar_todos_los_refresh(
    db: Session, usuario_id: uuid.UUID, *, momento: dt.datetime | None = None
) -> int:
    """Revoca **todos** los refresh vivos del usuario. Devuelve cuántos cerró.

    Es lo que corta la cadena en la detección de reuso, en el cambio de
    contraseña y en la baja de la cuenta.
    """
    instante = momento or utcnow()
    resultado = db.execute(
        sa.update(RefreshToken)
        .where(RefreshToken.user_id == usuario_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=instante)
    )
    db.flush()
    return int(resultado.rowcount or 0)


# ---------------------------------------------------------------------------
# Casos de uso
# ---------------------------------------------------------------------------


def registrar(
    db: Session,
    *,
    email: str,
    password: str,
    timezone: str | None = None,
    locale: str | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> ParTokens:
    """Crea la cuenta con correo y contraseña y devuelve el primer par de tokens.

    El correo es único: si ya existe se responde `409 EMAIL_ALREADY_EXISTS`.
    No se pide nombre —eso se define al crear el personaje (P03)— y tampoco se
    crea personaje aquí: `GET /auth/me` devolverá `has_character = false`.
    """
    normalizado = normalizar_email(email)
    validar_fuerza_contrasena(password, email=normalizado)

    if buscar_por_email(db, normalizado) is not None:
        raise Conflict("Ya existe una cuenta con ese correo.", code="EMAIL_ALREADY_EXISTS")

    zona = timezone if timezone and is_valid_timezone(timezone) else None
    usuario = User(
        email=normalizado,
        password_hash=hash_password(password),
        auth_provider=AuthProvider.EMAIL,
        role=UserRole.LEARNER,
    )
    if zona:
        usuario.timezone = zona
    if locale:
        usuario.locale = locale

    savepoint = db.begin_nested()
    try:
        db.add(usuario)
        db.flush()
    except IntegrityError as exc:
        savepoint.rollback()
        raise Conflict("Ya existe una cuenta con ese correo.", code="EMAIL_ALREADY_EXISTS") from exc
    savepoint.commit()

    servicio_usuario.obtener_o_crear_ajustes(db, usuario.id)
    servicio_usuario.emitir_evento(
        db,
        usuario=usuario,
        tipo=EventType.USER_REGISTERED,
        payload={
            "email_domain": normalizado.split("@")[-1],
            "auth_provider": AuthProvider.EMAIL.value,
        },
        sufijo="1",
    )

    usuario.last_login_at = utcnow()
    db.flush()
    return emitir_par(db, usuario, user_agent=user_agent, ip_address=ip_address)


def iniciar_sesion(
    db: Session,
    *,
    email: str,
    password: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> ParTokens:
    """Valida credenciales y emite un par de tokens nuevo.

    Responde siempre `401 INVALID_CREDENTIALS` (sin distinguir entre correo
    inexistente y contraseña equivocada) para no filtrar qué cuentas existen.
    """
    usuario = buscar_por_email(db, email)
    if usuario is None or not usuario.is_active:
        raise InvalidCredentials()
    if not verify_password(password, usuario.password_hash):
        raise InvalidCredentials()

    if usuario.password_hash and needs_rehash(usuario.password_hash):
        usuario.password_hash = hash_password(password)

    usuario.last_login_at = utcnow()
    db.flush()

    servicio_usuario.emitir_evento(
        db,
        usuario=usuario,
        tipo=EventType.USER_LOGGED_IN,
        payload={"device": (user_agent or "unknown")[:64]},
        sufijo=usuario.last_login_at.isoformat(),
    )
    return emitir_par(db, usuario, user_agent=user_agent, ip_address=ip_address)


def refrescar(
    db: Session,
    *,
    refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
    momento: dt.datetime | None = None,
) -> ParTokens:
    """Rota el refresh token: revoca el recibido y emite uno nuevo encadenado.

    Detección de reuso (§8.7): si el token que llega **ya estaba revocado**, es
    que alguien reprodujo un token viejo; se revoca toda la cadena viva del
    usuario y se responde `401 TOKEN_REUSE_DETECTED`.
    """
    instante = momento or utcnow()
    fila = _buscar_refresh(db, refresh_token)
    if fila is None:
        raise Unauthorized()

    if fila.revoked_at is not None:
        revocar_todos_los_refresh(db, fila.user_id, momento=instante)
        raise TokenReuseDetected()

    if fila.expires_at <= instante:
        revocar_refresh(db, fila, momento=instante)
        raise Unauthorized("Tu sesión ha caducado. Vuelve a iniciar sesión.")

    usuario = db.get(User, fila.user_id)
    if usuario is None or not usuario.is_active or usuario.deleted_at is not None:
        revocar_todos_los_refresh(db, fila.user_id, momento=instante)
        raise Unauthorized()

    par = emitir_par(db, usuario, user_agent=user_agent, ip_address=ip_address, momento=instante)
    nuevo = db.execute(
        sa.select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(par.refresh_token)
        )
    ).scalar_one()

    fila.revoked_at = instante
    fila.replaced_by_id = nuevo.id
    db.flush()
    return par


def cerrar_sesion(
    db: Session,
    usuario: User,
    *,
    refresh_token: str | None = None,
    momento: dt.datetime | None = None,
) -> int:
    """Revoca el refresh recibido. Sin token, cierra **todas** las sesiones.

    Un token que no existe o que es de otra persona no dice nada: se responde
    `204` igual, para no convertir el logout en un oráculo de tokens válidos.
    """
    instante = momento or utcnow()
    if not refresh_token:
        return revocar_todos_los_refresh(db, usuario.id, momento=instante)

    fila = _buscar_refresh(db, refresh_token)
    if fila is None or fila.user_id != usuario.id:
        return 0
    revocar_refresh(db, fila, momento=instante)
    return 1


def cambiar_contrasena(
    db: Session,
    usuario: User,
    *,
    current_password: str,
    new_password: str,
    momento: dt.datetime | None = None,
) -> None:
    """Cambia la contraseña y revoca **todos** los refresh tokens (§7.1).

    Exige la contraseña actual: sin ella un access token robado bastaría para
    secuestrar la cuenta.
    """
    if not verify_password(current_password, usuario.password_hash):
        raise InvalidCredentials("La contraseña actual no es correcta.")
    validar_fuerza_contrasena(new_password, email=usuario.email)
    if verify_password(new_password, usuario.password_hash):
        raise ValidationFailed(
            "La contraseña nueva debe ser distinta de la actual.",
            field_errors=[{"field": "new_password", "message": "Elige una contraseña distinta."}],
        )

    usuario.password_hash = hash_password(new_password)
    db.flush()
    revocar_todos_los_refresh(db, usuario.id, momento=momento)


__all__ = [
    "LARGO_MAXIMO",
    "LARGO_MINIMO",
    "PROHIBIDAS",
    "ParTokens",
    "buscar_por_email",
    "cambiar_contrasena",
    "cerrar_sesion",
    "emitir_par",
    "iniciar_sesion",
    "normalizar_email",
    "refrescar",
    "registrar",
    "revocar_refresh",
    "revocar_todos_los_refresh",
    "validar_fuerza_contrasena",
]
