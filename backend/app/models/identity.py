"""Modelos del módulo `identity`: cuentas, sesiones, ajustes, personaje y avatar.

Este archivo implementa el catálogo de tablas del contrato §3.1:
`users`, `refresh_tokens`, `user_settings`, `characters`, `avatar_configs`
y `equipped_items`.

`identity` es el módulo raíz de la pirámide de dependencias: no conoce a ningún
otro módulo y todos los demás lo referencian a través de `users.id`. La única
excepción es `equipped_items`, que apunta a `user_items.id` (propiedad de
`economy`): la escritura de esa tabla está **delegada** a `economy` (contrato
§1.3), pero el modelo vive aquí porque el equipamiento visible es parte de la
identidad del personaje.

Reglas aplicadas (contrato §1.4):

- Toda clave foránea se declara con el destino **en texto** (`"users.id"`).
- `relationship()` solo entre clases de este mismo archivo.
- Los `server_default` de columnas de enum guardan el **nombre del miembro en
  MAYÚSCULAS** (`"EMAIL"`, `"LEARNER"`, `"SYSTEM"`…), nunca su valor en
  minúsculas: con `native_enum=False` SQLAlchemy persiste el nombre y leer un
  valor en minúsculas revienta con `LookupError`.
- Fechas siempre `DateTime(timezone=True)` en UTC.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AddressForm,
    AuthProvider,
    BodyType,
    CharacterArchetype,
    ItemSlot,
    ReminderMode,
    ThemePreference,
    UserRole,
)

__all__ = [
    "AvatarConfig",
    "Character",
    "EquippedItem",
    "RefreshToken",
    "User",
    "UserSettings",
]


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Cuenta de la persona: credenciales, rol, zona horaria y estado.

    Es la raíz de todos los datos personales del sistema: cualquier tabla con
    datos de usuario cuelga de `users.id` con `ondelete="CASCADE"`. La baja del
    usuario es **lógica** (`is_active`, `deleted_at`); el borrado físico solo
    ocurre por petición explícita de derecho al olvido.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(sa.String(320), nullable=False)
    """Correo normalizado a minúsculas por la aplicación (lo garantiza un CHECK)."""

    password_hash: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    """Hash bcrypt; nulo si la cuenta proviene de un proveedor social."""

    auth_provider: Mapped[AuthProvider] = mapped_column(
        sa.Enum(AuthProvider, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=AuthProvider.EMAIL,
        # Se guarda el NOMBRE del miembro, no su valor (contrato §1.4, regla 6).
        server_default=AuthProvider.EMAIL.name,
    )
    auth_provider_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    """Identificador de la cuenta en el proveedor social (nulo con AuthProvider.EMAIL)."""

    role: Mapped[UserRole] = mapped_column(
        sa.Enum(UserRole, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=UserRole.LEARNER,
        server_default=UserRole.LEARNER.name,
    )
    timezone: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, default="America/Santiago", server_default="America/Santiago"
    )
    """Zona IANA; base del cálculo de `local_date` para racha y objetivo diario."""

    locale: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, default="es-CL", server_default="es-CL"
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    """Baja lógica: la cuenta deja de autenticarse sin borrar sus datos."""

    email_verified_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    timezone_changed_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    """Control anti-abuso: solo un cambio de zona efectivo cada 24 h."""

    previous_timezone: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    """Zona anterior; habilita el ajuste de racha por viaje."""

    deleted_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    """Borrado lógico a petición del usuario; las consultas filtran `deleted_at IS NULL`."""

    __table_args__ = (
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("auth_provider", "auth_provider_id"),
        sa.Index("ix_users_deleted_at", "deleted_at"),
        sa.CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    # -- Relaciones internas del archivo (nunca hacia otros archivos de modelos) --
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    password_resets: Mapped[list[PasswordReset]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    settings: Mapped[UserSettings | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    character: Mapped[Character | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class RefreshToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Token de refresco rotatorio, con revocación y cadena de reemplazo.

    Cada refresco emite un token nuevo y marca el anterior como revocado,
    apuntando a su sucesor en `replaced_by_id`. Si llega un token ya revocado
    que tiene sucesor, se detecta reuso y se revoca toda la cadena del usuario.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    """SHA-256 en hexadecimal del token; el token en claro nunca se guarda."""

    issued_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[dt.datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    """Vencimiento calculado con `JWT_REFRESH_TTL_DAYS`."""

    revoked_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Token que lo sustituyó en la rotación; base de la detección de reuso."""

    user_agent: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(sa.String(45), nullable=True)
    """IPv4 o IPv6 del emisor (45 caracteres cubren IPv6 con sufijo IPv4)."""

    __table_args__ = (
        sa.UniqueConstraint("token_hash"),
        sa.Index("ix_refresh_tokens_user_id", "user_id"),
        sa.Index("ix_refresh_tokens_expires_at", "expires_at"),
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
    replaced_by: Mapped[RefreshToken | None] = relationship(
        remote_side="RefreshToken.id", foreign_keys=[replaced_by_id]
    )


class PasswordReset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Permiso de un solo uso para elegir una contraseña nueva.

    Sin esto, olvidar la contraseña significaba perder la cuenta: `POST
    /auth/password` exige la sesión y la contraseña actual, y `DELETE
    /auth/account` también exige sesión, así que no había forma de entrar ni de
    salir. La pantalla de acceso tenía el botón y una hoja que prometía una
    versión futura.

    Del mismo corte que `RefreshToken`, y por las mismas razones:

    - Solo se guarda el **SHA-256** del token. Quien lea la base no puede
      restablecer la contraseña de nadie.
    - Vive poco (`PASSWORD_RESET_TTL_MIN`) y se gasta al usarse (`used_at`).
    - Se anota quién lo pidió y desde dónde, que es lo único que permite
      distinguir después una recuperación legítima de un intento de secuestro.
    """

    __tablename__ = "password_resets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    """SHA-256 en hexadecimal del token; el token en claro solo viaja al correo."""

    expires_at: Mapped[dt.datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    used_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    """Cuándo se gastó. Un permiso usado no vuelve a servir."""

    requested_user_agent: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    requested_ip: Mapped[str | None] = mapped_column(sa.String(45), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("token_hash"),
        sa.Index("ix_password_resets_user_id", "user_id"),
        sa.Index("ix_password_resets_expires_at", "expires_at"),
    )

    user: Mapped[User] = relationship(back_populates="password_resets")


class UserSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Preferencias de apariencia, notificaciones y contenido. Una fila por usuario.

    El planificador de notificaciones lee de aquí las horas de silencio, el modo
    de recordatorio y los interruptores por tipo antes de encolar cualquier aviso.
    """

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    theme: Mapped[ThemePreference] = mapped_column(
        sa.Enum(ThemePreference, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ThemePreference.SYSTEM,
        server_default=ThemePreference.SYSTEM.name,
    )
    reduce_motion: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    """Accesibilidad: desactiva las animaciones de recompensa."""

    sound_enabled: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    haptics_enabled: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    push_enabled: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    """Permiso de push concedido por el sistema operativo del dispositivo."""

    push_token: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    """Token FCM/APNs del dispositivo actual."""

    reminder_mode: Mapped[ReminderMode] = mapped_column(
        sa.Enum(ReminderMode, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ReminderMode.SMART,
        server_default=ReminderMode.SMART.name,
    )
    reminder_time_local: Mapped[dt.time | None] = mapped_column(sa.Time, nullable=True)
    """Hora local fija del recordatorio cuando `reminder_mode = MANUAL`."""

    last_call_enabled: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    """Segundo aviso de racha a las 21:30 hora local (opt-in)."""

    quiet_hours_start: Mapped[dt.time] = mapped_column(
        sa.Time,
        nullable=False,
        default=dt.time(22, 0),
        server_default=sa.text("'22:00:00'"),
    )
    quiet_hours_end: Mapped[dt.time] = mapped_column(
        sa.Time,
        nullable=False,
        default=dt.time(8, 0),
        server_default=sa.text("'08:00:00'"),
    )
    notify_path_ready: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    notify_streak: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    notify_missions: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    content_language: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, default="es", server_default="es"
    )
    """Idioma en el que la IA genera el contenido (independiente de `users.locale`)."""

    last_reminder_sent_on: Mapped[dt.date | None] = mapped_column(sa.Date, nullable=True)
    """Antifatiga: como máximo un recordatorio por fecha local del usuario."""

    __table_args__ = (sa.UniqueConstraint("user_id"),)

    user: Mapped[User] = relationship(back_populates="settings")


class Character(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Personaje del usuario: identidad de juego, nivel y contadores cacheados.

    `xp_total`, `level` y `total_study_seconds` son **cachés**: la fuente de
    verdad es el ledger `xp_transactions` y las tablas de progreso. Se recalculan
    y reconcilian en el proceso nocturno; nunca se editan desde el cliente
    (el servidor es la única autoridad sobre las recompensas).
    """

    __tablename__ = "characters"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    """Nombre visible del personaje; la API lo limita a 3–20 caracteres."""

    archetype: Mapped[CharacterArchetype] = mapped_column(
        sa.Enum(CharacterArchetype, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    """Orden elegida en el onboarding: puramente narrativa, **sin efecto educativo**."""

    level: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1")
    )
    """Nivel global cacheado, derivado de `xp_total` por la curva de §6.1."""

    xp_total: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=0, server_default=sa.text("0")
    )
    """XP acumulado cacheado; debe cuadrar con `SUM(xp_transactions.amount)`."""

    rank_title: Mapped[str] = mapped_column(
        sa.String(48), nullable=False, default="Aprendiz", server_default="Aprendiz"
    )
    """Título del rango vigente, tomado de la tabla de rangos de `game_configs`."""

    total_study_seconds: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    """Tiempo de estudio activo acumulado; nunca alimenta XP ni dominio."""

    onboarded_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    """Momento en que terminó la creación del personaje."""

    __table_args__ = (
        sa.UniqueConstraint("user_id"),
        sa.CheckConstraint("level >= 1 AND level <= 99", name="level_range"),
        sa.CheckConstraint("xp_total >= 0", name="xp_total_non_negative"),
    )

    user: Mapped[User] = relationship(back_populates="character")
    avatar_config: Mapped[AvatarConfig | None] = relationship(
        back_populates="character",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    equipped_items: Mapped[list[EquippedItem]] = relationship(
        back_populates="character", cascade="all, delete-orphan", passive_deletes=True
    )


class AvatarConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Rasgos gratuitos del avatar: piel, rostro, cabello, orejas y trato.

    Nada de lo que hay aquí es un ítem del inventario ni se compra con oro: son
    las opciones de creación de personaje, siempre disponibles. Lo que sí es
    equipamiento vive en `equipped_items`.
    """

    __tablename__ = "avatar_configs"

    character_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )
    body_type: Mapped[BodyType] = mapped_column(
        sa.Enum(BodyType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=BodyType.NEUTRAL,
        server_default=BodyType.NEUTRAL.name,
    )
    skin_tone: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default="skin_03", server_default="skin_03"
    )
    """Clave de la paleta de piel (6 tonos en el MVP)."""

    face_id: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, default="face_01", server_default="face_01"
    )
    ear_style: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default="round", server_default="round"
    )
    """`round` o `pointed`."""

    hair_style_id: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, default="hair_01", server_default="hair_01"
    )
    hair_color: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default="hair_black", server_default="hair_black"
    )
    address_form: Mapped[AddressForm] = mapped_column(
        sa.Enum(AddressForm, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=AddressForm.NEUTRAL,
        server_default=AddressForm.NEUTRAL.name,
    )
    """Forma gramatical con la que todos los textos se dirigen al usuario."""

    accent_color: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    """Color de acento del perfil en formato `#RRGGBB`."""

    asset_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1")
    )
    """Versión del manifiesto de assets con la que se resolvieron las claves."""

    __table_args__ = (sa.UniqueConstraint("character_id"),)

    character: Mapped[Character] = relationship(back_populates="avatar_config")


class EquippedItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Qué instancia del inventario ocupa cada ranura del personaje.

    El único por (`character_id`, `slot`) hace imposible equipar dos ítems en la
    misma ranura. `user_item_id` apunta a `user_items` (módulo `economy`, FK por
    texto): el servicio que equipa debe comprobar que la instancia pertenece al
    mismo usuario y que su `slot` coincide con el de esta fila.
    """

    __tablename__ = "equipped_items"

    character_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )
    slot: Mapped[ItemSlot] = mapped_column(
        sa.Enum(ItemSlot, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    user_item_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("user_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    """Instancia equipada; debe pertenecer al mismo usuario que el personaje."""

    equipped_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("character_id", "slot"),
        sa.Index("ix_equipped_items_user_item_id", "user_item_id"),
    )

    character: Mapped[Character] = relationship(back_populates="equipped_items")
