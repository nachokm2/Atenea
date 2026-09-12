"""Pruebas del personaje y del avatar (§7.2).

La creación del personaje (P03) es el caso crítico: debe inicializar el monedero,
la racha y el objetivo diario, otorgar la bolsa de bienvenida **a través del
motor** (nunca con un literal) y devolver el `RewardsReceipt` en `rewards`.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.economy import GoldTransaction, Wallet
from app.models.enums import EventType, GoldSource
from app.models.gamification import DailyGoal, DomainEvent, Streak
from app.models.identity import AvatarConfig, Character

pytestmark = pytest.mark.db


def _clave() -> dict[str, str]:
    """Cabecera `Idempotency-Key` nueva (UUID v4, §8.3)."""
    return {"Idempotency-Key": str(uuid.uuid4())}


def _crear(cliente, autorizacion, **extra):
    """Llama a `POST /api/v1/characters` con un cuerpo válido."""
    cuerpo = {"name": "Atenea", "archetype": "arcane"}
    cuerpo.update(extra.pop("cuerpo", {}))
    cabeceras = {**autorizacion, **extra.pop("cabeceras", _clave())}
    return cliente.post("/api/v1/characters", json=cuerpo, headers=cabeceras)


# ---------------------------------------------------------------------------
# Creación (P03)
# ---------------------------------------------------------------------------


def test_crear_personaje_inicializa_monedero_racha_y_devuelve_recibo(
    cliente, db, configuracion, autorizacion, registrado
):
    """P03 crea el personaje, el monedero, la racha y el objetivo, y devuelve el recibo."""
    usuario_id = uuid.UUID(registrado["user"]["id"])

    respuesta = _crear(
        cliente,
        autorizacion,
        cuerpo={"traits": {"skin_tone": "skin_05", "address_form": "f", "hair_color": "hair_red"}},
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["name"] == "Atenea"
    assert cuerpo["archetype"] == "arcane"
    assert cuerpo["level"] == 1
    assert cuerpo["rank_title"] == "Aprendiz"
    assert cuerpo["onboarded_at"] is not None
    assert cuerpo["traits"]["skin_tone"] == "skin_05"
    assert cuerpo["traits"]["address_form"] == "f"

    # El recibo canónico de §7.10 viaja completo en `rewards`.
    recibo = cuerpo["rewards"]
    assert recibo is not None
    assert recibo["event_type"] == EventType.CHARACTER_CREATED.value
    # La bolsa de bienvenida sale de `gold.welcome`; la cascada puede sumar más
    # (el logro de bienvenida, por ejemplo), pero nunca menos.
    bolsa = db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(GoldTransaction.amount), 0)).where(
            GoldTransaction.user_id == usuario_id, GoldTransaction.source == GoldSource.WELCOME
        )
    ).scalar_one()
    assert bolsa == configuracion["gold.welcome"]
    assert recibo["gold"]["amount"] >= configuracion["gold.welcome"]
    assert "gold" in recibo["presentation_order"]

    # Estado de juego inicializado por sus dueños (`economy` y `gamification`).
    personaje = db.execute(
        sa.select(Character).where(Character.user_id == usuario_id)
    ).scalar_one()
    billetera = db.execute(sa.select(Wallet).where(Wallet.user_id == usuario_id)).scalar_one()
    assert billetera.balance == recibo["gold"]["balance_after"]
    assert billetera.balance >= configuracion["gold.welcome"]
    assert db.execute(sa.select(Streak).where(Streak.user_id == usuario_id)).scalar_one() is not None
    objetivo = db.execute(sa.select(DailyGoal).where(DailyGoal.user_id == usuario_id)).scalar_one()
    assert objetivo.goal_type.value == configuracion["goal.default"]["type"]
    assert objetivo.target == configuracion["goal.default"]["target"]
    assert db.execute(
        sa.select(AvatarConfig).where(AvatarConfig.character_id == personaje.id)
    ).scalar_one() is not None
    assert db.execute(
        sa.select(DomainEvent).where(
            DomainEvent.user_id == usuario_id,
            DomainEvent.event_type == EventType.CHARACTER_CREATED,
        )
    ).scalar_one() is not None


def test_crear_personaje_exige_la_cabecera_de_idempotencia(cliente, configuracion, autorizacion):
    """Sin `Idempotency-Key` responde `400 IDEMPOTENCY_KEY_REQUIRED` (§8.3)."""
    respuesta = cliente.post(
        "/api/v1/characters", json={"name": "Atenea", "archetype": "steel"}, headers=autorizacion
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_reintentar_con_la_misma_clave_devuelve_el_mismo_recibo(
    cliente, db, configuracion, autorizacion, registrado
):
    """Repetir con la misma clave responde `200`, mismo `receipt_id` y sin otorgar nada."""
    cabeceras = _clave()
    primera = _crear(cliente, autorizacion, cabeceras=cabeceras)
    assert primera.status_code == 201, primera.text

    segunda = _crear(cliente, autorizacion, cabeceras=cabeceras)

    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["rewards"]["receipt_id"] == primera.json()["rewards"]["receipt_id"]
    # El saldo no se movió con el reintento: nada se otorga dos veces (§7.10 regla 4).
    usuario_id = uuid.UUID(registrado["user"]["id"])
    billetera = db.execute(sa.select(Wallet).where(Wallet.user_id == usuario_id)).scalar_one()
    assert billetera.balance == primera.json()["rewards"]["gold"]["balance_after"]


def test_segundo_personaje_con_otra_clave_es_conflicto(cliente, configuracion, autorizacion):
    """Con personaje ya creado y clave nueva → `409 CHARACTER_ALREADY_EXISTS`."""
    assert _crear(cliente, autorizacion).status_code == 201

    respuesta = _crear(cliente, autorizacion, cuerpo={"name": "Otro", "archetype": "steel"})

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["code"] == "CHARACTER_ALREADY_EXISTS"


def test_el_arquetipo_no_depende_del_genero(cliente, configuracion, autorizacion):
    """Cualquier Orden se combina con cualquier forma de tratamiento (§7.2)."""
    respuesta = _crear(
        cliente,
        autorizacion,
        cuerpo={
            "name": "Valeria",
            "archetype": "steel",
            "traits": {"address_form": "f", "ear_style": "pointed"},
        },
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["archetype"] == "steel"
    assert cuerpo["traits"]["address_form"] == "f"


def test_nombre_demasiado_corto_es_validacion(cliente, configuracion, autorizacion):
    """El nombre del personaje tiene 3–20 caracteres en la API."""
    respuesta = _crear(cliente, autorizacion, cuerpo={"name": "Ab", "archetype": "arcane"})

    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Lectura y actualización
# ---------------------------------------------------------------------------


def test_get_characters_me_sin_personaje_es_404(cliente, configuracion, autorizacion):
    """Antes de P03 no hay personaje que devolver."""
    respuesta = cliente.get("/api/v1/characters/me", headers=autorizacion)

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "NOT_FOUND"


def test_get_characters_me_lee_nivel_y_rango_del_motor(cliente, configuracion, autorizacion):
    """El nivel, el XP y el rango salen de la curva de §6.1, no del cliente."""
    assert _crear(cliente, autorizacion).status_code == 201

    respuesta = cliente.get("/api/v1/characters/me", headers=autorizacion)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["level"] == 1
    assert cuerpo["xp_total"] == 0
    assert cuerpo["rank_title"] == "Aprendiz"
    assert cuerpo["xp_to_next"] > 0
    assert cuerpo["rewards"] is None


def test_patch_characters_me_renombra_y_cambia_de_orden(cliente, configuracion, autorizacion):
    """`PATCH /characters/me` renombra o cambia el arquetipo (gratis en el MVP)."""
    assert _crear(cliente, autorizacion).status_code == 201

    respuesta = cliente.patch(
        "/api/v1/characters/me", json={"name": "Minerva", "archetype": "forest"}, headers=autorizacion
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["name"] == "Minerva"
    assert respuesta.json()["archetype"] == "forest"


def test_me_refleja_el_onboarding_tras_crear_el_personaje(cliente, configuracion, autorizacion):
    """`GET /auth/me` pasa a `has_character = true` y trae el personaje."""
    assert _crear(cliente, autorizacion).status_code == 201

    cuerpo = cliente.get("/api/v1/auth/me", headers=autorizacion).json()

    assert cuerpo["has_character"] is True
    assert cuerpo["has_path"] is False
    assert cuerpo["character"]["name"] == "Atenea"


# ---------------------------------------------------------------------------
# Avatar
# ---------------------------------------------------------------------------


def test_get_avatar_devuelve_rasgos_arquetipo_y_manifiesto(cliente, configuracion, autorizacion):
    """`GET /avatar` trae rasgos, arquetipo, equipo, capas ordenadas y `etag`."""
    assert _crear(cliente, autorizacion).status_code == 201

    respuesta = cliente.get("/api/v1/avatar", headers=autorizacion)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["archetype"] == "arcane"
    assert cuerpo["traits"]["skin_tone"]
    assert cuerpo["equipment"] == {}
    assert cuerpo["layers"] == []
    assert cuerpo["etag"]


def test_get_avatar_sin_personaje_es_404(cliente, configuracion, autorizacion):
    """Sin personaje no hay avatar que pintar."""
    assert cliente.get("/api/v1/avatar", headers=autorizacion).status_code == 404


def test_put_avatar_traits_cambia_los_rasgos_y_emite_el_evento(
    cliente, db, configuracion, autorizacion, registrado
):
    """`PUT /avatar/traits` aplica solo lo enviado y emite `AVATAR_UPDATED`."""
    assert _crear(cliente, autorizacion).status_code == 201
    antes = cliente.get("/api/v1/avatar", headers=autorizacion).json()

    respuesta = cliente.put(
        "/api/v1/avatar/traits",
        json={"hair_style_id": "hair_04", "hair_color": "hair_silver", "accent_color": "#A1B2C3"},
        headers=autorizacion,
    )

    assert respuesta.status_code == 200, respuesta.text
    rasgos = respuesta.json()["traits"]
    assert rasgos["hair_style_id"] == "hair_04"
    assert rasgos["hair_color"] == "hair_silver"
    assert rasgos["accent_color"] == "#a1b2c3"
    # Lo no enviado no se toca.
    assert rasgos["face_id"] == antes["traits"]["face_id"]
    assert respuesta.json()["etag"] != antes["etag"]

    evento = db.execute(
        sa.select(DomainEvent).where(
            DomainEvent.user_id == uuid.UUID(registrado["user"]["id"]),
            DomainEvent.event_type == EventType.AVATAR_UPDATED,
        )
    ).scalar_one()
    assert sorted(evento.payload["changed"]) == ["accent_color", "hair_color", "hair_style_id"]


def test_put_avatar_traits_rechaza_un_color_invalido(cliente, configuracion, autorizacion):
    """El color de acento debe ser `#RRGGBB`."""
    assert _crear(cliente, autorizacion).status_code == 201

    respuesta = cliente.put(
        "/api/v1/avatar/traits", json={"accent_color": "rojo"}, headers=autorizacion
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["code"] == "VALIDATION_ERROR"


def test_put_avatar_equipment_con_ranura_desconocida_es_422(cliente, configuracion, autorizacion):
    """Una ranura que no existe aborta el mapa completo."""
    assert _crear(cliente, autorizacion).status_code == 201

    respuesta = cliente.put(
        "/api/v1/avatar/equipment",
        json={"equipment": {"sombrero": None}},
        headers=autorizacion,
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["code"] == "VALIDATION_ERROR"


def test_put_avatar_equipment_vacio_devuelve_el_avatar(cliente, configuracion, autorizacion):
    """Un mapa vacío es válido: no cambia nada y devuelve el avatar resuelto."""
    assert _crear(cliente, autorizacion).status_code == 201

    respuesta = cliente.put(
        "/api/v1/avatar/equipment", json={"equipment": {}}, headers=autorizacion
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["layers"] == []
