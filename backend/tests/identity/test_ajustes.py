"""Pruebas de las preferencias del usuario (§7.1, P21).

`PUT /settings` es una actualización **parcial**: solo toca lo que el cliente
envió. El objetivo diario preferido no vive en `user_settings` sino en
`daily_goals` (propiedad de `gamification`), y se cambia con su servicio.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.enums import EventType
from app.models.gamification import DailyGoal, DomainEvent
from app.models.identity import User, UserSettings

pytestmark = pytest.mark.db


def test_get_settings_devuelve_los_valores_por_defecto(cliente, autorizacion):
    """Sin haber tocado nada, los ajustes son los `server_default` del contrato."""
    respuesta = cliente.get("/api/v1/settings", headers=autorizacion)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["theme"] == "system"
    assert cuerpo["reminder_mode"] == "smart"
    assert cuerpo["sound_enabled"] is True
    assert cuerpo["notify_missions"] is False
    assert cuerpo["content_language"] == "es"
    assert cuerpo["timezone"] == "America/Santiago"
    assert cuerpo["locale"] == "es-CL"
    assert cuerpo["has_push_token"] is False
    assert "push_token" not in cuerpo


def test_put_settings_actualiza_tema_notificaciones_idioma_y_zona(
    cliente, db, autorizacion, registrado
):
    """Se actualizan tema, avisos, idioma, zona horaria y se emite `SETTINGS_UPDATED`."""
    usuario_id = uuid.UUID(registrado["user"]["id"])

    respuesta = cliente.put(
        "/api/v1/settings",
        json={
            "theme": "dark",
            "notify_missions": True,
            "reminder_mode": "manual",
            "reminder_time_local": "19:30:00",
            "content_language": "en",
            "locale": "en-US",
            "timezone": "Europe/Madrid",
            "push_enabled": True,
            "push_token": "token-del-dispositivo",
        },
        headers=autorizacion,
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["theme"] == "dark"
    assert cuerpo["notify_missions"] is True
    assert cuerpo["reminder_mode"] == "manual"
    assert cuerpo["reminder_time_local"] == "19:30:00"
    assert cuerpo["content_language"] == "en"
    assert cuerpo["locale"] == "en-US"
    assert cuerpo["timezone"] == "Europe/Madrid"
    # El token de push se guarda pero nunca se devuelve (§8.7).
    assert cuerpo["has_push_token"] is True
    assert "push_token" not in cuerpo

    usuario = db.get(User, usuario_id)
    assert usuario.timezone == "Europe/Madrid"
    assert usuario.previous_timezone == "America/Santiago"
    assert usuario.timezone_changed_at is not None

    evento = db.execute(
        sa.select(DomainEvent).where(
            DomainEvent.user_id == usuario_id,
            DomainEvent.event_type == EventType.SETTINGS_UPDATED,
        )
    ).scalar_one()
    assert "theme" in evento.payload["changed"]
    assert "timezone" in evento.payload["changed"]


def test_put_settings_es_parcial(cliente, db, autorizacion, registrado):
    """Lo que no se envía no se toca."""
    cliente.put("/api/v1/settings", json={"theme": "light"}, headers=autorizacion)

    respuesta = cliente.put("/api/v1/settings", json={"sound_enabled": False}, headers=autorizacion)

    cuerpo = respuesta.json()
    assert cuerpo["theme"] == "light"
    assert cuerpo["sound_enabled"] is False
    assert cuerpo["haptics_enabled"] is True

    ajustes = db.execute(
        sa.select(UserSettings).where(
            UserSettings.user_id == uuid.UUID(registrado["user"]["id"])
        )
    ).scalar_one()
    assert ajustes.theme.value == "light"


def test_put_settings_solo_permite_un_cambio_de_zona_cada_24h(cliente, db, autorizacion, registrado):
    """El segundo cambio de zona en menos de 24 h se ignora: manda el servidor (§8.6)."""
    cliente.put("/api/v1/settings", json={"timezone": "Europe/Madrid"}, headers=autorizacion)

    respuesta = cliente.put(
        "/api/v1/settings", json={"timezone": "Asia/Tokyo"}, headers=autorizacion
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["timezone"] == "Europe/Madrid"
    assert db.get(User, uuid.UUID(registrado["user"]["id"])).timezone == "Europe/Madrid"


def test_put_settings_rechaza_una_zona_horaria_inexistente(cliente, autorizacion):
    """Una zona que no es IANA es `422 VALIDATION_ERROR`."""
    respuesta = cliente.put(
        "/api/v1/settings", json={"timezone": "Marte/Olympus"}, headers=autorizacion
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["code"] == "VALIDATION_ERROR"


def test_put_settings_cambia_el_objetivo_diario_preferido(
    cliente, db, configuracion, autorizacion, registrado
):
    """Subir el objetivo rige el mismo día; lo escribe `gamification` (§6.11)."""
    respuesta = cliente.put(
        "/api/v1/settings",
        json={"daily_goal": {"type": "minutos", "target": 45}},
        headers=autorizacion,
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["daily_goal"]["type"] == "minutos"
    assert respuesta.json()["daily_goal"]["target"] == 45

    objetivo = db.execute(
        sa.select(DailyGoal).where(DailyGoal.user_id == uuid.UUID(registrado["user"]["id"]))
    ).scalar_one()
    assert objetivo.target == 45


def test_settings_exige_token(cliente):
    """Las preferencias son privadas: sin token, `401`."""
    assert cliente.get("/api/v1/settings").status_code == 401
    assert cliente.put("/api/v1/settings", json={"theme": "dark"}).status_code == 401
