"""Esquemas Pydantic v2 del módulo `identity` (entradas `In`, salidas `Out`, §8.8).

Los nombres de campo son **literalmente** los del contrato (§7.1 y §7.2): no se
traducen ni se abrevian. Los enums se serializan por su **valor** (`"arcane"`,
`"system"`), que es lo que Pydantic hace con un `StrEnum` (§1.4 regla 6).

Un esquema de salida jamás hereda de un modelo SQLAlchemy: se construye con
`model_config = ConfigDict(from_attributes=True)`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import (
    AddressForm,
    AuthProvider,
    BodyType,
    CharacterArchetype,
    GoalType,
    ReminderMode,
    ThemePreference,
    UserRole,
)
from app.modules.gamification.recompensas import ReciboRecompensas

#: Longitud mínima y máxima del nombre del personaje en la API (§3.1 `characters`).
NOMBRE_MIN = 3
NOMBRE_MAX = 20

#: Longitud mínima y máxima de la contraseña (§8.7: bcrypt trunca a 72 bytes).
PASSWORD_MIN = 8
PASSWORD_MAX = 128


class EsquemaBase(BaseModel):
    """Base común: se puede construir desde el ORM y no acepta campos desconocidos."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class EntradaBase(BaseModel):
    """Base de las entradas: rechaza campos no declarados para no tragar errores."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Autenticación (§7.1)
# ---------------------------------------------------------------------------


class RegisterIn(EntradaBase):
    """Cuerpo de `POST /auth/register`. No pide nombre: eso es del personaje."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=10)


class LoginIn(EntradaBase):
    """Cuerpo de `POST /auth/login`."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class RefreshIn(EntradaBase):
    """Cuerpo de `POST /auth/refresh`: el token opaco de refresco."""

    refresh_token: str = Field(min_length=1, max_length=512)


class LogoutIn(EntradaBase):
    """Cuerpo de `POST /auth/logout`. Sin token se cierran todas las sesiones."""

    refresh_token: str | None = Field(default=None, max_length=512)


class PasswordChangeIn(EntradaBase):
    """Cuerpo de `POST /auth/password`: revoca todos los refresh al cambiarla."""

    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX)
    new_password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class PasswordForgotIn(EntradaBase):
    """Cuerpo de `POST /auth/password/forgot`: solo el correo."""

    email: EmailStr


class PasswordResetIn(EntradaBase):
    """Cuerpo de `POST /auth/password/reset`: el permiso y la contraseña nueva."""

    token: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class AccountDeleteIn(EntradaBase):
    """Cuerpo opcional de `DELETE /auth/account`."""

    reason: str | None = Field(default=None, max_length=255)


class UserOut(EsquemaBase):
    """Usuario tal como lo ve su dueño. Nunca incluye `password_hash` (§8.7)."""

    id: uuid.UUID
    email: str
    role: UserRole
    auth_provider: AuthProvider
    timezone: str
    locale: str
    is_active: bool
    email_verified_at: dt.datetime | None = None
    last_login_at: dt.datetime | None = None
    created_at: dt.datetime


class AuthTokens(EsquemaBase):
    """Par de tokens emitido por registro, login y refresco (§7.1)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ---------------------------------------------------------------------------
# Ajustes (§7.1, P21)
# ---------------------------------------------------------------------------


class DailyGoalPreferenceIn(EntradaBase):
    """Objetivo diario preferido dentro de `PUT /settings`."""

    type: GoalType
    target: int = Field(ge=1, le=1000)


class DailyGoalPreferenceOut(EsquemaBase):
    """Objetivo diario vigente y su cambio programado (§6.11)."""

    type: GoalType
    target: int
    effective_from: dt.date | None = None
    pending_type: GoalType | None = None
    pending_target: int | None = None
    pending_from: dt.date | None = None


class SettingsOut(EsquemaBase):
    """Preferencias del usuario (`GET`/`PUT /settings`).

    `push_token` **no** se devuelve: es una credencial de dispositivo.
    """

    theme: ThemePreference
    reduce_motion: bool
    sound_enabled: bool
    haptics_enabled: bool
    push_enabled: bool
    has_push_token: bool = False
    reminder_mode: ReminderMode
    reminder_time_local: dt.time | None = None
    last_call_enabled: bool
    quiet_hours_start: dt.time
    quiet_hours_end: dt.time
    notify_path_ready: bool
    notify_streak: bool
    notify_missions: bool
    content_language: str
    last_reminder_sent_on: dt.date | None = None
    timezone: str
    locale: str
    daily_goal: DailyGoalPreferenceOut | None = None


class PushTokenIn(EntradaBase):
    """Cuerpo de `POST /devices/push-token`.

    `null` da de baja el dispositivo: es la forma de decir "ya no me avises
    aquí" sin tener que borrar la cuenta.
    """

    push_token: str | None = Field(default=None, max_length=255)


class SettingsIn(EntradaBase):
    """Actualización parcial de las preferencias: solo se aplica lo enviado."""

    theme: ThemePreference | None = None
    reduce_motion: bool | None = None
    sound_enabled: bool | None = None
    haptics_enabled: bool | None = None
    push_enabled: bool | None = None
    push_token: str | None = Field(default=None, max_length=255)
    reminder_mode: ReminderMode | None = None
    reminder_time_local: dt.time | None = None
    last_call_enabled: bool | None = None
    quiet_hours_start: dt.time | None = None
    quiet_hours_end: dt.time | None = None
    notify_path_ready: bool | None = None
    notify_streak: bool | None = None
    notify_missions: bool | None = None
    content_language: str | None = Field(default=None, max_length=10)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=10)
    daily_goal: DailyGoalPreferenceIn | None = None


# ---------------------------------------------------------------------------
# Avatar (§7.2)
# ---------------------------------------------------------------------------


class AvatarTraitsIn(EntradaBase):
    """Rasgos gratuitos del avatar: piel, rostro, orejas, cabello y trato.

    Ninguno es un ítem del inventario; todos están siempre disponibles.
    """

    body_type: BodyType | None = None
    skin_tone: str | None = Field(default=None, max_length=16)
    face_id: str | None = Field(default=None, max_length=32)
    ear_style: str | None = Field(default=None, max_length=16)
    hair_style_id: str | None = Field(default=None, max_length=32)
    hair_color: str | None = Field(default=None, max_length=16)
    address_form: AddressForm | None = None
    accent_color: str | None = Field(default=None, max_length=9)

    @field_validator("accent_color")
    @classmethod
    def _validar_color(cls, valor: str | None) -> str | None:
        """El color de acento es `#RRGGBB` (con o sin canal alfa)."""
        if valor is None:
            return None
        texto = valor.strip()
        if not texto.startswith("#") or len(texto) not in (7, 9):
            raise ValueError("El color de acento debe tener el formato #RRGGBB.")
        try:
            int(texto[1:], 16)
        except ValueError as exc:
            raise ValueError("El color de acento debe tener el formato #RRGGBB.") from exc
        return texto.lower()


class AvatarTraitsOut(EsquemaBase):
    """Rasgos del avatar tal como los pinta el cliente."""

    body_type: BodyType
    skin_tone: str
    face_id: str
    ear_style: str
    hair_style_id: str
    hair_color: str
    address_form: AddressForm
    accent_color: str | None = None
    asset_version: int


class AvatarLayerOut(EsquemaBase):
    """Una capa del avatar, ya resuelta y lista para pintar (06c §2.3 y §2.7).

    `key` es el nombre de la capa en la pila de dibujado (`cape_back`, `head`…),
    no el código del ítem: es lo que decide el orden y lo que nombran las
    supresiones. `src` es el archivo, y `x/y/w/h` su rectángulo dentro del lienzo
    maestro de 1024×1024.

    Ya no hay `offset`: nunca llevó valor, nadie lo leía, y lo que el cliente
    necesita para colocar una pieza es el rectángulo completo, no un
    desplazamiento suelto.
    """

    slot: str
    item_code: str
    key: str
    z: int
    src: str | None = None
    x: int = 0
    y: int = 0
    w: int | None = None
    h: int | None = None
    tint: str | None = None


class AvatarOut(EsquemaBase):
    """Respuesta de `GET /avatar`, `PUT /avatar/traits` y `PUT /avatar/equipment`."""

    traits: dict[str, Any] = Field(default_factory=dict)
    archetype: str
    equipment: dict[str, Any] = Field(default_factory=dict)
    layers: list[AvatarLayerOut] = Field(default_factory=list)
    etag: str


class AvatarEquipmentIn(EntradaBase):
    """Mapa atómico `{"weapon": "<user_item_id>", "cape": null}` de `PUT /avatar/equipment`."""

    equipment: dict[str, uuid.UUID | None] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Personaje (§7.2)
# ---------------------------------------------------------------------------


def _validar_nombre(valor: str) -> str:
    """Normaliza y valida el nombre visible del personaje (3–20 caracteres)."""
    texto = " ".join(valor.split())
    if len(texto) < NOMBRE_MIN or len(texto) > NOMBRE_MAX:
        raise ValueError(f"El nombre debe tener entre {NOMBRE_MIN} y {NOMBRE_MAX} caracteres.")
    return texto


class CharacterCreateIn(EntradaBase):
    """Cuerpo de `POST /characters` (P03): nombre, arquetipo y rasgos.

    El arquetipo es **libre**: ninguna Orden está restringida por género ni por
    la forma de tratamiento elegida.
    """

    name: str
    archetype: CharacterArchetype
    traits: AvatarTraitsIn | None = None

    @field_validator("name")
    @classmethod
    def _nombre(cls, valor: str) -> str:
        return _validar_nombre(valor)


class CharacterUpdateIn(EntradaBase):
    """Cuerpo de `PATCH /characters/me`: renombrar o cambiar de Orden."""

    name: str | None = None
    archetype: CharacterArchetype | None = None

    @field_validator("name")
    @classmethod
    def _nombre(cls, valor: str | None) -> str | None:
        return None if valor is None else _validar_nombre(valor)


class CharacterOut(EsquemaBase):
    """Personaje con nivel, XP y rango **leídos del motor**, nunca del cliente.

    `rewards` solo viaja en `POST /characters` (§7.2); en las lecturas es `null`.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    archetype: CharacterArchetype
    level: int
    xp_total: int
    rank_title: str
    xp_to_next: int
    progress_pct: float
    total_study_seconds: int
    onboarded_at: dt.datetime | None = None
    created_at: dt.datetime
    traits: AvatarTraitsOut | None = None
    rewards: ReciboRecompensas | None = None


# ---------------------------------------------------------------------------
# Sesión actual (§7.1)
# ---------------------------------------------------------------------------


class MeOut(EsquemaBase):
    """Respuesta de `GET /auth/me`: usuario, personaje y estado de onboarding."""

    user: UserOut
    character: CharacterOut | None = None
    has_character: bool
    has_path: bool
    settings: SettingsOut


__all__ = [
    "NOMBRE_MAX",
    "NOMBRE_MIN",
    "PASSWORD_MAX",
    "PASSWORD_MIN",
    "AccountDeleteIn",
    "AuthTokens",
    "AvatarEquipmentIn",
    "AvatarLayerOut",
    "AvatarOut",
    "AvatarTraitsIn",
    "AvatarTraitsOut",
    "CharacterCreateIn",
    "CharacterOut",
    "CharacterUpdateIn",
    "DailyGoalPreferenceIn",
    "DailyGoalPreferenceOut",
    "EntradaBase",
    "EsquemaBase",
    "LoginIn",
    "LogoutIn",
    "MeOut",
    "PasswordChangeIn",
    "RefreshIn",
    "RegisterIn",
    "SettingsIn",
    "SettingsOut",
    "UserOut",
]
