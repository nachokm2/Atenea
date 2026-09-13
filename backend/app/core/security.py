"""Seguridad: contraseñas con bcrypt, JWT de acceso/refresco y tokens opacos.

Contrato §8.7:

- Contraseñas con `bcrypt` (`passlib`), coste 12. Nunca se registran ni se devuelven.
- Access token JWT (`pyjwt`, HS256, `JWT_SECRET`) con `sub`, `role`, `exp`, `iat`, `jti`.
- Refresh token **opaco** de 256 bits, guardado solo como SHA-256 (64 hex), rotatorio
  y con detección de reuso. El token en claro nunca se persiste.

Además se ofrece un JWT de refresco (`create_refresh_token`) para clientes que
prefieran un token autocontenido; el modo canónico del MVP es el token opaco.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import bcrypt as _bcrypt
import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.errors import Unauthorized

# Compatibilidad passlib 1.7.4 con bcrypt >= 4.1: passlib lee `bcrypt.__about__.__version__`,
# atributo que bcrypt 4.1 eliminó, y registra un "(trapped) error reading bcrypt version".
# El backend funciona igual; el parche solo evita el ruido en los logs.
if not hasattr(_bcrypt, "__about__"):  # pragma: no cover - depende de la versión instalada

    class _BcryptAbout:
        """Envoltorio de compatibilidad que expone la versión de bcrypt a passlib."""

        __version__ = getattr(_bcrypt, "__version__", "4.0.0")

    _bcrypt.__about__ = _BcryptAbout  # type: ignore[attr-defined]

#: Tipos de token admitidos en el claim `type`.
TOKEN_TYPE_ACCESS: Final[str] = "access"
TOKEN_TYPE_REFRESH: Final[str] = "refresh"

#: Bytes de entropía del token opaco de refresco (256 bits).
REFRESH_TOKEN_BYTES: Final[int] = 32

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.bcrypt_rounds,
)


# ---------------------------------------------------------------------------
# Contraseñas
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Devuelve el hash bcrypt (coste 12) de una contraseña en claro."""
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Comprueba una contraseña contra su hash.

    Devuelve `False` (sin lanzar) si la cuenta no tiene hash —cuenta social— o si
    el hash almacenado está corrupto.
    """
    if not password_hash:
        return False
    try:
        return pwd_context.verify(password, password_hash)
    except (ValueError, TypeError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Indica si el hash usa parámetros antiguos y conviene regenerarlo al iniciar sesión."""
    try:
        return pwd_context.needs_update(password_hash)
    except (ValueError, TypeError):
        return True


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def _now() -> datetime:
    """Instante actual en UTC (nunca `datetime.now()` sin zona)."""
    return datetime.now(UTC)


def _encode(
    subject: str | uuid.UUID,
    *,
    token_type: str,
    expires_delta: timedelta,
    role: str | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Firma un JWT HS256 con los claims obligatorios `sub`, `exp`, `iat`, `jti` y `type`."""
    issued_at = _now()
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + expires_delta).timestamp()),
        "jti": str(uuid.uuid4()),
        "type": token_type,
        "iss": settings.jwt_issuer,
    }
    if role is not None:
        payload["role"] = role
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    subject: str | uuid.UUID,
    *,
    role: str | None = None,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Crea el JWT de acceso (TTL `JWT_ACCESS_TTL_MIN`, 30 min por defecto)."""
    minutes = settings.jwt_access_ttl_min if expires_minutes is None else expires_minutes
    return _encode(
        subject,
        token_type=TOKEN_TYPE_ACCESS,
        expires_delta=timedelta(minutes=minutes),
        role=role,
        extra_claims=extra_claims,
    )


def create_refresh_token(
    subject: str | uuid.UUID,
    *,
    role: str | None = None,
    expires_days: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Crea un JWT de refresco (TTL `JWT_REFRESH_TTL_DAYS`, 60 días por defecto)."""
    days = settings.jwt_refresh_ttl_days if expires_days is None else expires_days
    return _encode(
        subject,
        token_type=TOKEN_TYPE_REFRESH,
        expires_delta=timedelta(days=days),
        role=role,
        extra_claims=extra_claims,
    )


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any]:
    """Decodifica y valida un JWT de Atenea.

    Lanza `Unauthorized` si la firma es inválida, si caducó o si el claim `type`
    no es el esperado. Nunca revela el motivo técnico al usuario.
    """
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Tu sesión ha caducado. Vuelve a iniciar sesión.") from exc
    except jwt.PyJWTError as exc:
        raise Unauthorized() from exc

    if expected_type is not None and claims.get("type") != expected_type:
        raise Unauthorized()
    return claims


def decode_access_token(token: str) -> dict[str, Any]:
    """Decodifica un token exigiendo que sea de tipo `access`."""
    return decode_token(token, expected_type=TOKEN_TYPE_ACCESS)


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decodifica un token exigiendo que sea de tipo `refresh`."""
    return decode_token(token, expected_type=TOKEN_TYPE_REFRESH)


def token_subject(token: str, *, expected_type: str | None = TOKEN_TYPE_ACCESS) -> uuid.UUID:
    """Devuelve el `sub` del token como UUID; lanza `Unauthorized` si no lo es."""
    claims = decode_token(token, expected_type=expected_type)
    try:
        return uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise Unauthorized() from exc


# ---------------------------------------------------------------------------
# Tokens opacos de refresco
# ---------------------------------------------------------------------------


def generate_refresh_token() -> tuple[str, str]:
    """Genera un refresh token opaco de 256 bits.

    Devuelve `(token_en_claro, token_hash)`. El claro se entrega **una sola vez** al
    cliente; en `refresh_tokens.token_hash` se guarda únicamente el SHA-256 en hex.
    """
    token = secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    """SHA-256 en hexadecimal (64 caracteres) de un refresh token opaco."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expires_at(issued_at: datetime | None = None) -> datetime:
    """Calcula el vencimiento de un refresh token según `JWT_REFRESH_TTL_DAYS`."""
    base = issued_at or _now()
    return base + timedelta(days=settings.jwt_refresh_ttl_days)


# ---------------------------------------------------------------------------
# Comparación segura
# ---------------------------------------------------------------------------


def secure_compare(left: str | bytes | None, right: str | bytes | None) -> bool:
    """Compara dos secretos en tiempo constante, tolerando `None`."""
    if left is None or right is None:
        return False
    left_bytes = left.encode("utf-8") if isinstance(left, str) else left
    right_bytes = right.encode("utf-8") if isinstance(right, str) else right
    return hmac.compare_digest(left_bytes, right_bytes)


#: Alias explícito por legibilidad en los servicios.
constant_time_compare = secure_compare


def new_opaque_token(nbytes: int = REFRESH_TOKEN_BYTES) -> str:
    """Token opaco genérico y seguro en URL (verificación de correo, enlaces mágicos…)."""
    return secrets.token_urlsafe(nbytes)


__all__ = [
    "REFRESH_TOKEN_BYTES",
    "TOKEN_TYPE_ACCESS",
    "TOKEN_TYPE_REFRESH",
    "constant_time_compare",
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "decode_refresh_token",
    "decode_token",
    "generate_refresh_token",
    "hash_password",
    "hash_refresh_token",
    "needs_rehash",
    "new_opaque_token",
    "pwd_context",
    "refresh_token_expires_at",
    "secure_compare",
    "token_subject",
    "verify_password",
]
