"""Cuenta y preferencias: ajustes (P21), zona horaria, onboarding y baja de cuenta.

Reglas del contrato que este archivo hace cumplir:

- §8.6 · La zona horaria es IANA y solo se puede cambiar **una vez cada 24 h**;
  al cambiarla se guarda la anterior en `users.previous_timezone`, que es lo que
  habilita el ajuste de racha por viaje.
- §4.2 · `SETTINGS_UPDATED` viaja con la lista de campos cambiados; `USER_DELETED`
  con el motivo. Ninguno otorga recompensas, así que se escriben directamente en
  `domain_events` con `crear_evento_dominio` en vez de arrancar el motor completo.
- §8.7 · `password_hash` y `push_token` nunca se serializan al cliente.
- El objetivo diario preferido **no** se guarda aquí: es propiedad de
  `gamification` (`daily_goals`) y se cambia con `rachas.cambiar_objetivo`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.core.time import is_valid_timezone, user_local_date, utcnow
from app.models.enums import EventType, GoalType
from app.models.gamification import DailyGoal, DomainEvent
from app.models.identity import Character, User, UserSettings
from app.modules.gamification import eventos as bus
from app.modules.gamification import rachas
from app.modules.gamification.servicio_config import ServicioConfig

#: Ventana mínima entre dos cambios efectivos de zona horaria (§8.6).
VENTANA_CAMBIO_ZONA = dt.timedelta(hours=24)

#: Clave de `game_configs` con el máximo de cambios de zona por 24 h.
CLAVE_MAX_CAMBIOS_ZONA = "streak.tz_changes_max_per_24h"

#: Campos de `user_settings` que `PUT /settings` puede tocar directamente.
CAMPOS_AJUSTES: tuple[str, ...] = (
    "theme",
    "reduce_motion",
    "sound_enabled",
    "haptics_enabled",
    "push_enabled",
    "push_token",
    "reminder_mode",
    "reminder_time_local",
    "last_call_enabled",
    "quiet_hours_start",
    "quiet_hours_end",
    "notify_path_ready",
    "notify_streak",
    "notify_missions",
    "content_language",
)

#: Campos de `users` que `PUT /settings` puede tocar.
CAMPOS_USUARIO: tuple[str, ...] = ("timezone", "locale")


# ---------------------------------------------------------------------------
# Eventos de dominio de `identity`
# ---------------------------------------------------------------------------


def emitir_evento(
    db: Session,
    *,
    usuario: User | None,
    tipo: EventType,
    payload: dict[str, Any],
    sufijo: str,
    momento: dt.datetime | None = None,
) -> DomainEvent | None:
    """Escribe un evento de `identity` que **no** otorga recompensas (§4.2).

    Los eventos de identidad que sí las otorgan (`CHARACTER_CREATED`) pasan por
    `eventos.registrar_evento`; estos son de analítica y notificaciones, así que
    basta con persistirlos en `domain_events` con una clave determinista.
    """
    instante = momento or utcnow()
    zona = usuario.timezone if usuario is not None else None
    usuario_id = usuario.id if usuario is not None else None
    clave = f"{tipo.value.lower()}:{usuario_id}:{sufijo}"[:120]
    return bus.crear_evento_dominio(
        db,
        usuario_id=usuario_id,
        tipo=tipo,
        payload=bus.validar_payload(tipo, payload),
        idempotency_key=clave,
        occurred_at=instante,
        local_date=user_local_date(instante, zona),
        timezone=zona,
        source_module="identity",
    )


# ---------------------------------------------------------------------------
# Ajustes
# ---------------------------------------------------------------------------


def obtener_o_crear_ajustes(db: Session, usuario_id: uuid.UUID) -> UserSettings:
    """Fila de `user_settings` del usuario, creada con los valores por defecto."""
    ajustes = db.execute(
        sa.select(UserSettings).where(UserSettings.user_id == usuario_id)
    ).scalar_one_or_none()
    if ajustes is None:
        ajustes = UserSettings(user_id=usuario_id)
        db.add(ajustes)
        db.flush()
        db.refresh(ajustes)
    return ajustes


def objetivo_diario(db: Session, usuario_id: uuid.UUID) -> DailyGoal | None:
    """Objetivo diario vigente del usuario, si ya existe (no lo crea)."""
    return db.execute(sa.select(DailyGoal).where(DailyGoal.user_id == usuario_id)).scalar_one_or_none()


def vista_ajustes(db: Session, usuario: User) -> dict[str, Any]:
    """Preferencias del usuario en la forma que devuelve `SettingsOut`."""
    ajustes = obtener_o_crear_ajustes(db, usuario.id)
    objetivo = objetivo_diario(db, usuario.id)
    datos: dict[str, Any] = {
        campo: getattr(ajustes, campo) for campo in CAMPOS_AJUSTES if campo != "push_token"
    }
    datos["has_push_token"] = bool(ajustes.push_token)
    datos["last_reminder_sent_on"] = ajustes.last_reminder_sent_on
    datos["timezone"] = usuario.timezone
    datos["locale"] = usuario.locale
    datos["daily_goal"] = (
        None
        if objetivo is None
        else {
            "type": objetivo.goal_type,
            "target": objetivo.target,
            "effective_from": objetivo.effective_from,
            "pending_type": objetivo.pending_type,
            "pending_target": objetivo.pending_target,
            "pending_from": objetivo.pending_from,
        }
    )
    return datos


def cambiar_zona_horaria(db: Session, usuario: User, zona: str, *, momento: dt.datetime | None = None) -> bool:
    """Cambia la zona IANA del usuario respetando el límite de 1 cada 24 h (§8.6).

    Devuelve `True` si el cambio se aplicó. Si la zona no es válida lanza
    `VALIDATION_ERROR`; si el cupo de 24 h está gastado se ignora en silencio
    (el servidor manda: la respuesta devuelve la zona realmente vigente).
    """
    if zona == usuario.timezone:
        return False
    if not is_valid_timezone(zona):
        raise ValidationFailed(
            "Esa zona horaria no existe.",
            field_errors=[{"field": "timezone", "message": "Usa una zona IANA, por ejemplo America/Santiago."}],
        )

    instante = momento or utcnow()
    cfg = ServicioConfig(db)
    maximo = cfg.obtener_int(CLAVE_MAX_CAMBIOS_ZONA, 1)
    if (
        maximo <= 1
        and usuario.timezone_changed_at is not None
        and instante - usuario.timezone_changed_at < VENTANA_CAMBIO_ZONA
    ):
        return False

    usuario.previous_timezone = usuario.timezone
    usuario.timezone = zona
    usuario.timezone_changed_at = instante
    db.flush()
    return True


def actualizar_ajustes(db: Session, usuario: User, datos: dict[str, Any]) -> dict[str, Any]:
    """Aplica una actualización **parcial** de las preferencias (`PUT /settings`).

    `datos` es el `model_dump(exclude_unset=True)` de `SettingsIn`: solo se toca
    lo que el cliente envió. Emite `SETTINGS_UPDATED` con la lista de cambios.
    """
    ajustes = obtener_o_crear_ajustes(db, usuario.id)
    cambiados: list[str] = []

    for campo in CAMPOS_AJUSTES:
        if campo not in datos:
            continue
        valor = datos[campo]
        if getattr(ajustes, campo) != valor:
            setattr(ajustes, campo, valor)
            cambiados.append(campo)

    if "locale" in datos and datos["locale"] and datos["locale"] != usuario.locale:
        usuario.locale = datos["locale"]
        cambiados.append("locale")

    if "timezone" in datos and datos["timezone"] and cambiar_zona_horaria(db, usuario, datos["timezone"]):
        cambiados.append("timezone")

    objetivo = datos.get("daily_goal")
    if objetivo:
        cfg = ServicioConfig(db)
        hoy = user_local_date(utcnow(), usuario.timezone)
        rachas.cambiar_objetivo(
            db,
            cfg,
            usuario.id,
            hoy,
            goal_type=GoalType(objetivo["type"]),
            target=int(objetivo["target"]),
        )
        cambiados.append("daily_goal")

    db.flush()

    if cambiados:
        emitir_evento(
            db,
            usuario=usuario,
            tipo=EventType.SETTINGS_UPDATED,
            payload={"changed": sorted(set(cambiados))},
            sufijo=utcnow().isoformat(),
        )
        db.flush()

    return vista_ajustes(db, usuario)


# ---------------------------------------------------------------------------
# Onboarding y baja
# ---------------------------------------------------------------------------


def tiene_personaje(db: Session, usuario_id: uuid.UUID) -> bool:
    """`True` si el usuario ya creó su personaje (P03 completado)."""
    return (
        db.execute(
            sa.select(sa.literal(1)).select_from(Character).where(Character.user_id == usuario_id).limit(1)
        ).scalar_one_or_none()
        is not None
    )


def tiene_ruta(db: Session, usuario_id: uuid.UUID) -> bool:
    """`True` si el usuario ya tiene una ruta propia o está estudiando una del Reino.

    Se consulta con SQL textual acotado a las dos tablas de otros módulos
    (`learning_paths` de `content` y `user_path_progress` de `progress`) para no
    importar sus modelos y respetar los límites del monolito modular (§1.3).
    """
    consulta = sa.text(
        """
        SELECT 1
        WHERE EXISTS (SELECT 1 FROM learning_paths WHERE user_id = :uid)
           OR EXISTS (SELECT 1 FROM user_path_progress WHERE user_id = :uid)
        LIMIT 1
        """
    )
    return db.execute(consulta, {"uid": usuario_id}).scalar_one_or_none() is not None


def estado_onboarding(db: Session, usuario_id: uuid.UUID) -> tuple[bool, bool]:
    """Devuelve `(has_character, has_path)` para `GET /auth/me`."""
    return tiene_personaje(db, usuario_id), tiene_ruta(db, usuario_id)


def borrar_cuenta(db: Session, usuario: User, *, reason: str | None = None) -> User:
    """Da de baja la cuenta a petición de su dueño (`DELETE /auth/account`).

    El borrado es **lógico** (§7.1) pero efectivo: la cuenta deja de autenticarse
    (`is_active = false`, `deleted_at`), pierde su hash de contraseña y su token
    de push, todos sus refresh tokens quedan revocados y el correo se libera
    (se sustituye por un alias irreversible) para que la persona pueda volver a
    registrarse. Emite `USER_DELETED`, que es lo que `ingestion` consume para
    purgar sus documentos.
    """
    from app.modules.identity.servicio_auth import revocar_todos_los_refresh

    instante = utcnow()
    dominio = usuario.email.split("@")[-1] if "@" in usuario.email else None

    revocar_todos_los_refresh(db, usuario.id, momento=instante)

    ajustes = db.execute(
        sa.select(UserSettings).where(UserSettings.user_id == usuario.id)
    ).scalar_one_or_none()
    if ajustes is not None:
        ajustes.push_enabled = False
        ajustes.push_token = None

    usuario.is_active = False
    usuario.deleted_at = instante
    usuario.password_hash = None
    usuario.auth_provider_id = None
    usuario.email = f"deleted+{usuario.id.hex}@atenea.invalid"
    db.flush()

    emitir_evento(
        db,
        usuario=usuario,
        tipo=EventType.USER_DELETED,
        payload={"reason": reason or "user_request", "email_domain": dominio},
        sufijo=instante.isoformat(),
        momento=instante,
    )
    db.flush()
    return usuario


__all__ = [
    "CAMPOS_AJUSTES",
    "CAMPOS_USUARIO",
    "CLAVE_MAX_CAMBIOS_ZONA",
    "VENTANA_CAMBIO_ZONA",
    "actualizar_ajustes",
    "borrar_cuenta",
    "cambiar_zona_horaria",
    "emitir_evento",
    "estado_onboarding",
    "objetivo_diario",
    "obtener_o_crear_ajustes",
    "tiene_personaje",
    "tiene_ruta",
    "vista_ajustes",
]
