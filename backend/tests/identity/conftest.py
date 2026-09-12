"""Fixtures del módulo `identity`.

Las pruebas usan la **base real de desarrollo** dentro de una transacción que
siempre se revierte: la sesión se abre sobre una conexión con una transacción
externa y `join_transaction_mode="create_savepoint"`, de modo que los
`begin_nested()` del código de producción (inserción de `domain_events`, por
ejemplo) funcionen igual que en la API y nada quede escrito al terminar.

La app de pruebas monta **solo** el router de `identity` y sustituye `get_db`:
así se prueba el contrato de la API sin depender de `app/main.py` ni del router
raíz, que pertenecen a otros agentes. `get_current_user` **no** se sustituye: el
flujo de token real (registro → access token → `Authorization: Bearer`) es parte
de lo que hay que verificar.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import register_exception_handlers
from app.models.enums import EventType, GoldSource, XPSource
from app.models.gamification import GameConfig, RewardRule
from app.modules.gamification.servicio_config import ServicioConfig, invalidar_cache
from app.modules.identity.router import router

#: Versión de `game_configs` propia de esta suite. La tabla es única por
#: (key, version): con una versión distinta por módulo, dos suites pueden
#: sembrar la misma clave a la vez sin esperarse una a otra.
VERSION_SEMILLA = 3

URL_PRUEBAS = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea_test"
)

#: Contraseña válida según las reglas de fuerza de `servicio_auth`.
PASSWORD = "Atenea2026!"

#: Semilla mínima de `game_configs` que necesita el onboarding de identidad.
#: Todos los valores son los de §5.2, §5.3, §5.4 y §5.6 del contrato.
CONFIGURACION_SEMILLA: dict[str, Any] = {
    "level.base": 80,
    "level.exponent": 2.2,
    "level.max": 50,
    "level.round_to": 10,
    "level.rank_titles": {
        "1": "Aprendiz",
        "5": "Iniciado/a",
        "10": "Escriba",
        "15": "Erudito/a",
        "20": "Adepto/a",
        "25": "Guardián/a del Saber",
        "30": "Sabio/a",
        "35": "Maestro/a",
        "40": "Gran Maestro/a",
        "45": "Archimaestro/a",
        "50": "Leyenda del Reino",
    },
    "knowledge.level.base": 50,
    "knowledge.level.exponent": 2.2,
    "knowledge.rank_titles": {"1": "Novato/a en", "5": "Practicante de", "10": "Competente en"},
    "gold.welcome": 100,
    "gold.level_up_bonus": 50,
    "gold.rank_up_bonus": 100,
    "gold.daily_softcap": [{"limit": 500, "mult": 0.5}, {"limit": 1000, "mult": 0.1}],
    "goal.default": {"type": "minutos", "target": 20},
    "goal.change_effective": "next_day",
    "goal.activity_units": {"lesson": 1, "questions_block": 1, "questions_per_block": 5},
    "goal.bonus_gold_base": 10,
    "goal.bonus_gold_cap_days": 20,
    "streak.sync_tolerance_min": 10,
    "streak.min_daily_educational_xp": 30,
    "streak.grace_per_month": 1,
    "streak.travel_skip_per_30d": 1,
    "streak.tz_changes_max_per_24h": 1,
    "streak.milestones": [7, 14, 30, 60, 100, 365],
    "streak.repeat_milestone_every": 50,
    "items.slots_active": [
        "head",
        "body",
        "cape",
        "gloves",
        "boots",
        "weapon",
        "offhand",
        "accessory",
    ],
    "items.slots_reserved": ["pet", "mount"],
    "missions.daily.count": 3,
}


def _tipo_de(valor: Any) -> str:
    """Traduce el valor de semilla al `value_type` de `game_configs`."""
    if isinstance(valor, dict):
        return "map"
    if isinstance(valor, list):
        return "list"
    if isinstance(valor, bool):
        return "bool"
    if isinstance(valor, float):
        return "decimal"
    if isinstance(valor, int):
        return "int"
    return "string"


@pytest.fixture(scope="session")
def engine() -> Any:
    """Motor síncrono contra la base de desarrollo."""
    motor = sa.create_engine(URL_PRUEBAS, future=True, pool_pre_ping=True)
    try:
        with motor.connect() as conexion:
            conexion.execute(sa.text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - entorno sin base
        pytest.skip(f"Base de datos de pruebas no disponible: {exc}")
    yield motor
    motor.dispose()


@pytest.fixture
def db(engine: Any) -> Session:
    """Sesión transaccional que se revierte por completo al final de cada prueba."""
    invalidar_cache()
    conexion = engine.connect()
    transaccion = conexion.begin()
    sesion = Session(
        bind=conexion,
        future=True,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield sesion
    finally:
        sesion.close()
        transaccion.rollback()
        conexion.close()
        invalidar_cache()


@pytest.fixture
def configuracion(db: Session) -> dict[str, Any]:
    """Deja en pie la configuración de juego que necesita el onboarding.

    La base de desarrollo puede estar ya sembrada por el agente de integración,
    así que la semilla es **idempotente**: solo se inserta la clave que falta y
    al final se devuelven los valores **vigentes** (los que el motor usará), no
    los que esta prueba quería poner.

    La bolsa de bienvenida tampoco es un literal del código: es una fila de
    `reward_rules` que apunta a la clave `gold.welcome` de `game_configs` (§5.3).
    """
    invalidar_cache()
    cfg = ServicioConfig(db)
    for clave, valor in CONFIGURACION_SEMILLA.items():
        if cfg.resolver(clave) is not None:
            continue
        version = db.execute(sa.text("SELECT nextval('game_config_version_seq')")).scalar()
        db.add(
            GameConfig(
                key=clave,
                version=VERSION_SEMILLA,
                config_version=int(version or 1),
                value=valor,
                value_type=_tipo_de(valor),
                is_public=True,
                description="Semilla de pruebas del módulo identity.",
            )
        )
    db.flush()
    invalidar_cache()

    regla = db.execute(
        sa.select(RewardRule).where(
            RewardRule.event_type == EventType.CHARACTER_CREATED, RewardRule.is_active.is_(True)
        )
    ).first()
    if regla is None:
        db.add(
            RewardRule(
                code="welcome_bag",
                event_type=EventType.CHARACTER_CREATED,
                condition={},
                xp_amount=0,
                gold_amount=0,
                gold_config_key="gold.welcome",
                gold_source=GoldSource.WELCOME,
                xp_source=XPSource.ADJUSTMENT,
                is_educational=False,
                first_time_only=True,
                respects_daily_cap=False,
                respects_repeat_multiplier=False,
                priority=10,
            )
        )
        db.flush()

    invalidar_cache()
    vigente = ServicioConfig(db)
    return {clave: vigente.obtener(clave) for clave in CONFIGURACION_SEMILLA}


@pytest.fixture
def cliente(db: Session) -> TestClient:
    """Cliente HTTP con el router de `identity` y la sesión de prueba."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as cliente_http:
        yield cliente_http


@pytest.fixture
def password() -> str:
    """Contraseña válida reutilizable en todas las pruebas."""
    return PASSWORD


@pytest.fixture
def correo() -> str:
    """Correo único por prueba (la columna `users.email` es única)."""
    return f"identidad-{uuid.uuid4().hex[:12]}@atenea-qa.cl"


@pytest.fixture
def registrado(cliente: TestClient, correo: str) -> dict[str, Any]:
    """Registra una cuenta y devuelve el cuerpo de `AuthTokens`."""
    respuesta = cliente.post(
        "/api/v1/auth/register", json={"email": correo, "password": PASSWORD}
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


@pytest.fixture
def autorizacion(registrado: dict[str, Any]) -> dict[str, str]:
    """Cabecera `Authorization` del usuario recién registrado."""
    return {"Authorization": f"Bearer {registrado['access_token']}"}
