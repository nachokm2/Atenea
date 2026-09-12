"""Rutas HTTP del módulo `identity` (contrato §7.1 y §7.2).

| Método | Ruta | Auth |
|---|---|---|
| POST | `/auth/register` | No |
| POST | `/auth/login` | No |
| POST | `/auth/refresh` | No (usa el refresh) |
| POST | `/auth/logout` | Sí |
| GET | `/auth/me` | Sí |
| POST | `/auth/password` | Sí |
| DELETE | `/auth/account` | Sí |
| GET · PUT | `/settings` | Sí |
| POST | `/characters` | Sí (**Idempotency-Key**) |
| GET · PATCH | `/characters/me` | Sí |
| GET | `/avatar` | Sí |
| PUT | `/avatar/traits` | Sí |
| PUT | `/avatar/equipment` | Sí |

El router se expone como `router = APIRouter()` **sin prefijo**: el `/api/v1` y el
montaje los pone el agente de integración en `app/api/v1/__init__.py`.

Nota de integración: `GET /avatar` y `PUT /avatar/equipment` también existen en
`app.modules.economy.router`. Son la misma respuesta (`AvatarOut`) resuelta por
`economy.equipamiento`; el router raíz debe montar **solo uno** de los dos para
esas dos rutas (este incluye además `PUT /avatar/traits`, que es de `identity`).

TODO(A1/A8): aplicar el límite de peticiones de §8.7 (60/min general) cuando
`slowapi` esté montado en `app/main.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Request, Response, status

from app.core.deps import CurrentUser, DbSession, IdempotencyDep
from app.modules.gamification.servicio_config import ServicioConfig
from app.modules.identity import avatar as servicio_avatar
from app.modules.identity import personaje as servicio_personaje
from app.modules.identity import servicio_auth, servicio_usuario
from app.modules.identity.schemas import (
    AccountDeleteIn,
    AuthTokens,
    AvatarEquipmentIn,
    AvatarOut,
    AvatarTraitsIn,
    CharacterCreateIn,
    CharacterOut,
    CharacterUpdateIn,
    LoginIn,
    LogoutIn,
    MeOut,
    PasswordChangeIn,
    RefreshIn,
    RegisterIn,
    SettingsIn,
    SettingsOut,
    UserOut,
)

router = APIRouter()


def _cliente(request: Request) -> tuple[str | None, str | None]:
    """Agente de usuario e IP de la petición, para la traza de `refresh_tokens`."""
    agente = request.headers.get("User-Agent")
    ip = request.client.host if request.client else None
    return agente, ip


def _tokens(par: servicio_auth.ParTokens) -> AuthTokens:
    """Adapta el par emitido al esquema `AuthTokens` del contrato."""
    return AuthTokens(
        access_token=par.access_token,
        refresh_token=par.refresh_token,
        token_type=par.token_type,
        expires_in=par.expires_in,
        user=UserOut.model_validate(par.user),
    )


# ---------------------------------------------------------------------------
# Autenticación (§7.1)
# ---------------------------------------------------------------------------


@router.post(
    "/auth/register",
    response_model=AuthTokens,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
    summary="Crear cuenta con correo y contraseña",
)
def registrar(
    cuerpo: RegisterIn,
    request: Request,
    db: DbSession,
    x_timezone: str | None = Header(default=None, alias="X-Timezone"),
) -> AuthTokens:
    """Crea la cuenta. No pide nombre: eso se define al crear el personaje."""
    agente, ip = _cliente(request)
    par = servicio_auth.registrar(
        db,
        email=str(cuerpo.email),
        password=cuerpo.password,
        timezone=cuerpo.timezone or x_timezone,
        locale=cuerpo.locale,
        user_agent=agente,
        ip_address=ip,
    )
    return _tokens(par)


@router.post("/auth/login", response_model=AuthTokens, tags=["auth"], summary="Iniciar sesión")
def iniciar_sesion(cuerpo: LoginIn, request: Request, db: DbSession) -> AuthTokens:
    """Valida credenciales y emite un par de tokens nuevo."""
    agente, ip = _cliente(request)
    par = servicio_auth.iniciar_sesion(
        db, email=str(cuerpo.email), password=cuerpo.password, user_agent=agente, ip_address=ip
    )
    return _tokens(par)


@router.post(
    "/auth/refresh",
    response_model=AuthTokens,
    tags=["auth"],
    summary="Rotar el refresh token",
)
def refrescar(cuerpo: RefreshIn, request: Request, db: DbSession) -> AuthTokens:
    """Rota el refresh token. Detecta el reuso y revoca la cadena (§8.7)."""
    agente, ip = _cliente(request)
    par = servicio_auth.refrescar(
        db, refresh_token=cuerpo.refresh_token, user_agent=agente, ip_address=ip
    )
    return _tokens(par)


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["auth"],
    summary="Cerrar sesión",
)
def cerrar_sesion(user: CurrentUser, db: DbSession, cuerpo: LogoutIn | None = None) -> Response:
    """Revoca el refresh recibido; sin cuerpo cierra todas las sesiones."""
    servicio_auth.cerrar_sesion(
        db, user, refresh_token=cuerpo.refresh_token if cuerpo else None
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/auth/me",
    response_model=MeOut,
    tags=["auth"],
    summary="Usuario, personaje y estado de onboarding",
)
def yo(user: CurrentUser, db: DbSession) -> MeOut:
    """Devuelve el usuario, su personaje y el estado de onboarding (§7.1)."""
    cfg = ServicioConfig(db)
    personaje = servicio_personaje.buscar_personaje(db, user.id)
    tiene_personaje = personaje is not None
    return MeOut(
        user=UserOut.model_validate(user),
        character=(
            None
            if personaje is None
            else CharacterOut.model_validate(
                servicio_personaje.vista_personaje(db, personaje, cfg=cfg)
            )
        ),
        has_character=tiene_personaje,
        has_path=servicio_usuario.tiene_ruta(db, user.id),
        settings=SettingsOut.model_validate(servicio_usuario.vista_ajustes(db, user)),
    )


@router.post(
    "/auth/password",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["auth"],
    summary="Cambiar la contraseña",
)
def cambiar_contrasena(cuerpo: PasswordChangeIn, user: CurrentUser, db: DbSession) -> Response:
    """Cambia la contraseña y revoca todos los refresh tokens del usuario."""
    servicio_auth.cambiar_contrasena(
        db, user, current_password=cuerpo.current_password, new_password=cuerpo.new_password
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/auth/account",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["auth"],
    summary="Dar de baja la cuenta",
)
def borrar_cuenta(user: CurrentUser, db: DbSession, cuerpo: AccountDeleteIn | None = None) -> Response:
    """Baja de la cuenta a petición de su dueño: deja de autenticarse al instante."""
    servicio_usuario.borrar_cuenta(db, user, reason=cuerpo.reason if cuerpo else None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Ajustes (§7.1, P21)
# ---------------------------------------------------------------------------


@router.get("/settings", response_model=SettingsOut, tags=["ajustes"], summary="Preferencias")
def obtener_ajustes(user: CurrentUser, db: DbSession) -> SettingsOut:
    """Preferencias de apariencia, notificaciones, idioma y objetivo diario."""
    return SettingsOut.model_validate(servicio_usuario.vista_ajustes(db, user))


@router.put(
    "/settings",
    response_model=SettingsOut,
    tags=["ajustes"],
    summary="Actualizar preferencias",
)
def actualizar_ajustes(cuerpo: SettingsIn, user: CurrentUser, db: DbSession) -> SettingsOut:
    """Actualiza tema, notificaciones, idioma, zona horaria y objetivo diario."""
    datos = cuerpo.model_dump(exclude_unset=True)
    return SettingsOut.model_validate(servicio_usuario.actualizar_ajustes(db, user, datos))


# ---------------------------------------------------------------------------
# Personaje (§7.2)
# ---------------------------------------------------------------------------


@router.post(
    "/characters",
    response_model=CharacterOut,
    status_code=status.HTTP_201_CREATED,
    tags=["personaje"],
    summary="Crear el personaje (P03)",
)
def crear_personaje(
    cuerpo: CharacterCreateIn,
    user: CurrentUser,
    db: DbSession,
    idempotency: IdempotencyDep,
    response: Response,
) -> CharacterOut:
    """Crea el personaje, otorga la bolsa de bienvenida y el kit inicial.

    Devuelve el `RewardsReceipt` en `rewards`. Reintentar con la misma
    `Idempotency-Key` responde `200` con el mismo recibo, sin otorgar nada nuevo.
    """
    clave = idempotency.require()
    ya_existia = servicio_personaje.buscar_personaje(db, user.id) is not None

    personaje, recibo = servicio_personaje.crear_personaje(
        db,
        user,
        name=cuerpo.name,
        archetype=cuerpo.archetype,
        traits=cuerpo.traits.model_dump(exclude_unset=True) if cuerpo.traits else None,
        idempotency_key=clave,
    )
    if ya_existia:
        response.status_code = status.HTTP_200_OK
    return CharacterOut.model_validate(
        servicio_personaje.vista_personaje(db, personaje, rewards=recibo)
    )


@router.get(
    "/characters/me",
    response_model=CharacterOut,
    tags=["personaje"],
    summary="Personaje con nivel, XP y rango",
)
def obtener_personaje(user: CurrentUser, db: DbSession) -> CharacterOut:
    """Personaje del usuario; nivel, XP y rango salen del motor, no del cliente."""
    personaje = servicio_personaje.obtener_personaje(db, user.id)
    return CharacterOut.model_validate(servicio_personaje.vista_personaje(db, personaje))


@router.patch(
    "/characters/me",
    response_model=CharacterOut,
    tags=["personaje"],
    summary="Renombrar o cambiar de Orden",
)
def actualizar_personaje(cuerpo: CharacterUpdateIn, user: CurrentUser, db: DbSession) -> CharacterOut:
    """Renombra el personaje o le cambia el arquetipo (gratis en el MVP)."""
    personaje = servicio_personaje.actualizar_personaje(
        db, user, name=cuerpo.name, archetype=cuerpo.archetype
    )
    return CharacterOut.model_validate(servicio_personaje.vista_personaje(db, personaje))


# ---------------------------------------------------------------------------
# Avatar (§7.2)
# ---------------------------------------------------------------------------


@router.get("/avatar", response_model=AvatarOut, tags=["avatar"], summary="Avatar resuelto")
def obtener_avatar(user: CurrentUser, db: DbSession) -> AvatarOut:
    """Rasgos, arquetipo, equipo y manifiesto de capas ordenado por `z`."""
    return AvatarOut.model_validate(servicio_avatar.vista_avatar(db, user.id))


@router.put(
    "/avatar/traits",
    response_model=AvatarOut,
    tags=["avatar"],
    summary="Cambiar los rasgos del avatar",
)
def actualizar_rasgos(cuerpo: AvatarTraitsIn, user: CurrentUser, db: DbSession) -> AvatarOut:
    """Cambia piel, rostro, orejas, cabello, color y forma de tratamiento."""
    cambios = cuerpo.model_dump(exclude_unset=True)
    return AvatarOut.model_validate(servicio_avatar.actualizar_rasgos(db, user, cambios))


@router.put(
    "/avatar/equipment",
    response_model=AvatarOut,
    tags=["avatar"],
    summary="Aplicar el equipamiento visible",
)
def actualizar_equipamiento(cuerpo: AvatarEquipmentIn, user: CurrentUser, db: DbSession) -> AvatarOut:
    """Mapa atómico `{"weapon": "<user_item_id>", "cape": null}` (§7.2)."""
    return AvatarOut.model_validate(
        servicio_avatar.actualizar_equipamiento(db, user, cuerpo.equipment)
    )


__all__ = ["router"]
