"""Dependencias comunes de FastAPI: sesión, usuario autenticado e idempotencia.

`get_current_user` necesita el modelo `User`, que pertenece a otro agente
(`app/models/identity.py`). Para evitar el ciclo de importación el modelo se
importa **de forma perezosa dentro de la función**; en tiempo de comprobación de
tipos se usa `TYPE_CHECKING`.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AteneaError, Forbidden, Unauthorized
from app.core.logging import bind_user
from app.core.security import TOKEN_TYPE_ACCESS, decode_token

if TYPE_CHECKING:  # pragma: no cover - solo para el comprobador de tipos
    from app.models.identity import User

#: Esquema Bearer sin error automático: los 401 los emite `Unauthorized` (§8.1).
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="AteneaBearer")

DbSession = Annotated[Session, Depends(get_db)]
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def _load_user(db: Session, user_id: uuid.UUID) -> "User":
    """Carga un usuario activo y no borrado; lanza `Unauthorized` si no procede."""
    from app.models.identity import User  # import perezoso: evita el ciclo con app.models

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_active or user.deleted_at is not None:
        raise Unauthorized()
    return user


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: BearerCredentials = None,
) -> "User":
    """Valida el JWT de acceso, carga el usuario y lo deja en `request.state.user`.

    Lanza `Unauthorized` (401 `UNAUTHORIZED`) si falta la cabecera, el token es
    inválido o caducado, o la cuenta está inactiva o borrada.
    """
    if credentials is None or not credentials.credentials:
        raise Unauthorized()

    claims = decode_token(credentials.credentials, expected_type=TOKEN_TYPE_ACCESS)
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise Unauthorized() from exc

    user = _load_user(db, user_id)
    request.state.user = user
    request.state.user_id = user.id
    request.state.token_claims = claims
    bind_user(user.id)
    return user


def get_current_user_optional(
    request: Request,
    db: DbSession,
    credentials: BearerCredentials = None,
) -> "User | None":
    """Igual que `get_current_user`, pero devuelve `None` en rutas semipúblicas.

    Un token presente pero inválido **sí** falla: solo la ausencia de token es
    aceptable aquí.
    """
    if credentials is None or not credentials.credentials:
        return None
    return get_current_user(request, db, credentials)


CurrentUser = Annotated[Any, Depends(get_current_user)]
CurrentUserOptional = Annotated[Any, Depends(get_current_user_optional)]


def require_role(*roles: str):
    """Fábrica de dependencias que exige uno de los roles indicados.

    Uso::

        @router.get("/admin/x", dependencies=[Depends(require_role("admin"))])
    """
    allowed = {str(role) for role in roles}

    def _checker(user: CurrentUser) -> Any:
        if str(getattr(user, "role", "")) not in allowed:
            raise Forbidden()
        return user

    return _checker


# ---------------------------------------------------------------------------
# Idempotencia (§8.3)
# ---------------------------------------------------------------------------


class Idempotency:
    """Valor de la cabecera `Idempotency-Key` de la petición (§8.3).

    Se inyecta con el alias `IdempotencyDep`::

        @router.post("/shop/purchase")
        def purchase(idem: IdempotencyDep, ...):
            key = idem.require()

    La clave debe ser un UUID v4. `require()` lanza `400 IDEMPOTENCY_KEY_REQUIRED`
    cuando falta en una operación que otorga recompensas.
    """

    __slots__ = ("key",)

    def __init__(self, idempotency_key: str | None = None) -> None:
        self.key: str | None = idempotency_key.strip() if idempotency_key else None

    @property
    def present(self) -> bool:
        """Indica si el cliente envió la cabecera."""
        return bool(self.key)

    @property
    def is_valid_uuid(self) -> bool:
        """Indica si la clave tiene forma de UUID."""
        if not self.key:
            return False
        try:
            uuid.UUID(self.key)
        except ValueError:
            return False
        return True

    def require(self) -> str:
        """Devuelve la clave o lanza el error del contrato si falta o es inválida."""
        if not self.key:
            raise AteneaError(code="IDEMPOTENCY_KEY_REQUIRED")
        if not self.is_valid_uuid:
            raise AteneaError(
                "La cabecera Idempotency-Key debe ser un UUID v4.",
                code="IDEMPOTENCY_KEY_REQUIRED",
            )
        return self.key

    def __str__(self) -> str:  # pragma: no cover - ayuda de depuración
        return self.key or ""


def get_idempotency(
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="UUID v4 que hace idempotente la operación (contrato §8.3).",
    ),
) -> Idempotency:
    """Dependencia que lee la cabecera `Idempotency-Key` y la envuelve en `Idempotency`.

    Se declara como función (y no como dependencia de clase) porque este módulo usa
    `from __future__ import annotations`: FastAPI no sabe resolver las anotaciones
    diferidas del `__init__` de una clase y la cabecera acabaría leyéndose como
    parámetro de consulta.
    """
    return Idempotency(idempotency_key)


IdempotencyDep = Annotated[Idempotency, Depends(get_idempotency)]


def get_request_id(request: Request) -> str | None:
    """Devuelve el `request_id` de la petición en curso (lo fija el middleware)."""
    return getattr(request.state, "request_id", None) or request.headers.get("X-Request-Id")


RequestId = Annotated[str | None, Depends(get_request_id)]


__all__ = [
    "BearerCredentials",
    "CurrentUser",
    "CurrentUserOptional",
    "DbSession",
    "Idempotency",
    "IdempotencyDep",
    "RequestId",
    "bearer_scheme",
    "get_current_user",
    "get_current_user_optional",
    "get_db",
    "get_idempotency",
    "get_request_id",
    "require_role",
]
