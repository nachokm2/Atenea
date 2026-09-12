"""Fixtures del módulo `economy`.

Las pruebas que tocan datos usan la **base real de desarrollo** dentro de una
transacción que siempre se revierte: la sesión se crea sobre una conexión con una
transacción externa abierta y `join_transaction_mode="create_savepoint"`, de modo que
los `begin_nested()` del código de producción funcionen igual que en la API y nada
quede escrito al terminar.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.content import KnowledgeArea
from app.models.economy import Item, ItemRequirement, ShopListing
from app.models.enums import (
    CharacterArchetype,
    ItemOrigin,
    ItemRarity,
    ItemSlot,
    KnowledgeAreaStatus,
    KnowledgeCategory,
    RequirementType,
)
from app.models.gamification import GameConfig
from app.models.identity import Character, User
from app.models.progress import UserAreaProgress

URL_PRUEBAS = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea_test"
)

#: Semilla mínima de `game_configs` que necesita la economía (valores de §5.3 y §5.4).
CONFIGURACION_SEMILLA: dict[str, Any] = {
    "shop.price_by_rarity": {
        "common": 150,
        "uncommon": 500,
        "rare": 1200,
        "epic": 3000,
        "legendary": 8000,
        "mythic": None,
    },
    "shop.min_level_by_rarity": {
        "common": 1,
        "uncommon": 3,
        "rare": 8,
        "epic": 15,
        "legendary": 25,
    },
    "shop.unlock_level": 3,
    "shop.featured_max": 4,
    "shop.sellable_rarities": ["common", "uncommon", "rare", "epic"],
    "shop.purchase_reversal_seconds": 60,
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
    "items.mastered_threshold": 80,
    "gold.welcome": 100,
    "gold.lesson_completed": 20,
}


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


# ---------------------------------------------------------------------------
# Semillas
# ---------------------------------------------------------------------------


@pytest.fixture
def configuracion(db: Session) -> dict[str, Any]:
    """Carga la semilla de `game_configs` que necesita la economía."""
    # ATENEA_LIMPIEZA_CONFIG: varias suites siembran las mismas claves de
    # `game_configs`, que es única por (key, version). Se borran antes de
    # insertarlas para que el orden de ejecución no importe.
    db.execute(sa.delete(GameConfig).where(GameConfig.key.in_(list(CONFIGURACION_SEMILLA))))
    db.flush()

    for indice, (clave, valor) in enumerate(CONFIGURACION_SEMILLA.items(), start=1):
        db.add(
            GameConfig(
                key=clave,
                version=1,
                config_version=indice,
                value=valor,
                value_type="map" if isinstance(valor, dict) else "list" if isinstance(valor, list) else "int",
                is_public=True,
                description="Semilla de pruebas del módulo economy.",
            )
        )
    db.flush()
    return CONFIGURACION_SEMILLA


@pytest.fixture
def usuario(db: Session) -> User:
    """Usuario de pruebas con zona horaria chilena."""
    fila = User(
        email=f"economia-{uuid.uuid4().hex[:12]}@atenea.test",
        password_hash=None,
        timezone="America/Santiago",
    )
    db.add(fila)
    db.flush()
    return fila


@pytest.fixture
def personaje(db: Session, usuario: User) -> Character:
    """Personaje de nivel 10: por encima de `shop.unlock_level`."""
    fila = Character(
        user_id=usuario.id,
        name="Atenea",
        archetype=CharacterArchetype.ARCANE,
        level=10,
        xp_total=5000,
        rank_title="Iniciado/a",
    )
    db.add(fila)
    db.flush()
    return fila


@pytest.fixture
def area(db: Session) -> KnowledgeArea:
    """Conocimiento canónico de pruebas."""
    fila = KnowledgeArea(
        slug=f"sql-{uuid.uuid4().hex[:8]}",
        name="SQL",
        short_name="SQL",
        category=KnowledgeCategory.DATA,
        is_canonical=True,
    )
    db.add(fila)
    db.flush()
    return fila


# ---------------------------------------------------------------------------
# Fábricas
# ---------------------------------------------------------------------------


@pytest.fixture
def crear_item(db: Session):
    """Fábrica de ítems del catálogo."""

    def _crear(
        *,
        code: str | None = None,
        name: str = "Capa de prueba",
        slot: ItemSlot = ItemSlot.CAPE,
        rarity: ItemRarity = ItemRarity.COMMON,
        origin: ItemOrigin = ItemOrigin.SHOP,
        auto_grant: bool = False,
        requirement_facts: list[str] | None = None,
        render_manifest: dict[str, Any] | None = None,
        knowledge_area_id: uuid.UUID | None = None,
    ) -> Item:
        item = Item(
            code=code or f"item_{uuid.uuid4().hex[:12]}",
            name=name,
            description="Ítem cosmético de pruebas.",
            slot=slot,
            rarity=rarity,
            origin=origin,
            auto_grant=auto_grant,
            requirements={},
            requirement_facts=requirement_facts or [],
            render_manifest=render_manifest or {"layers": [{"key": "capa", "z": 20}]},
            knowledge_area_id=knowledge_area_id,
        )
        db.add(item)
        db.flush()
        return item

    return _crear


@pytest.fixture
def crear_listing(db: Session):
    """Fábrica de listados de tienda."""

    def _crear(
        item: Item,
        *,
        price: int = 150,
        min_level: int = 1,
        is_featured: bool = False,
        is_active: bool = True,
    ) -> ShopListing:
        listing = ShopListing(
            item_id=item.id,
            price=price,
            min_level=min_level,
            is_featured=is_featured,
            is_active=is_active,
        )
        db.add(listing)
        db.flush()
        return listing

    return _crear


@pytest.fixture
def crear_requisito(db: Session):
    """Fábrica de condiciones de desbloqueo (`item_requirements`)."""

    def _crear(
        item: Item,
        *,
        requirement_type: RequirementType,
        group_index: int = 0,
        position: int = 0,
        knowledge_area_id: uuid.UUID | None = None,
        target_value: Decimal | float | None = None,
        target_count: int | None = None,
        achievement_code: str | None = None,
        label_template: str | None = None,
        window_from: dt.datetime | None = None,
        window_to: dt.datetime | None = None,
    ) -> ItemRequirement:
        fila = ItemRequirement(
            item_id=item.id,
            group_index=group_index,
            position=position,
            requirement_type=requirement_type,
            knowledge_area_id=knowledge_area_id,
            target_value=None if target_value is None else Decimal(str(target_value)),
            target_count=target_count,
            achievement_code=achievement_code,
            label_template=label_template,
            window_from=window_from,
            window_to=window_to,
        )
        db.add(fila)
        db.flush()
        return fila

    return _crear


@pytest.fixture
def fijar_dominio(db: Session):
    """Fija el dominio del usuario en un conocimiento (`user_area_progress`)."""

    def _fijar(
        usuario: User,
        area: KnowledgeArea,
        mastery: float,
        *,
        status: KnowledgeAreaStatus = KnowledgeAreaStatus.IN_PROGRESS,
    ) -> UserAreaProgress:
        fila = db.execute(
            sa.select(UserAreaProgress).where(
                UserAreaProgress.user_id == usuario.id,
                UserAreaProgress.knowledge_area_id == area.id,
            )
        ).scalar_one_or_none()
        if fila is None:
            fila = UserAreaProgress(
                user_id=usuario.id,
                knowledge_area_id=area.id,
                xp=0,
                level=1,
                rank_title="Novato/a en",
                mastery=Decimal(str(mastery)),
                status=status,
            )
            db.add(fila)
        else:
            fila.mastery = Decimal(str(mastery))
            fila.status = status
        db.flush()
        return fila

    return _fijar
