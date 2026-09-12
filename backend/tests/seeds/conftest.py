"""Fixtures de las pruebas de `app/seeds`.

Las pruebas se ejecutan contra la base de datos de desarrollo dentro de una
transacción que se **revierte** al terminar: no dejan rastro, ni siquiera cuando la
siembra escribe las diecisiete tablas de catálogo.

La fixture `sembrado` ejecuta `app.seeds.ejecutar.sembrar()` una sola vez por sesión
de pruebas, de modo que todo funciona igual con la base recién migrada (siembra desde
cero) y con la base ya sembrada (la siembra no cambia nada, que es justo lo que hay
que demostrar).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.identity import User
from app.modules.gamification import servicio_config
from app.modules.gamification.servicio_config import ServicioConfig
from app.seeds.ejecutar import Resumen, sembrar

URL_BASE_PRUEBAS = "postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea_test"


@pytest.fixture(scope="session")
def conexion() -> Iterator[sa.Connection]:
    """Conexión única con una transacción externa que se revierte al terminar."""
    motor = sa.create_engine(URL_BASE_PRUEBAS, future=True)
    conn = motor.connect()
    transaccion = conn.begin()
    try:
        yield conn
    finally:
        transaccion.rollback()
        conn.close()
        motor.dispose()


@pytest.fixture(scope="session")
def sembrado(conexion: sa.Connection) -> Iterator[Resumen]:
    """Siembra todos los catálogos una vez, dentro de la transacción de prueba."""
    servicio_config.invalidar_cache()
    sesion = Session(bind=conexion, join_transaction_mode="create_savepoint")
    try:
        resumen = sembrar(sesion)
        sesion.flush()
        yield resumen
    finally:
        sesion.close()
        servicio_config.invalidar_cache()


@pytest.fixture
def db(conexion: sa.Connection, sembrado: Resumen) -> Iterator[Session]:
    """Sesión de prueba sobre un savepoint: cada prueba se revierte al terminar."""
    sesion = Session(bind=conexion, join_transaction_mode="create_savepoint")
    try:
        yield sesion
    finally:
        sesion.rollback()
        sesion.close()


@pytest.fixture
def cfg(db: Session) -> ServicioConfig:
    """Servicio de configuración sin caché, apuntando a la sesión de prueba."""
    servicio_config.invalidar_cache()
    return ServicioConfig(db, ttl_segundos=0)


@pytest.fixture
def usuario(db: Session) -> User:
    """Usuario de prueba: los evaluadores necesitan un `user_id` real."""
    fila = User(
        email=f"semillas-{uuid.uuid4().hex[:12]}@atenea.test",
        password_hash="x" * 20,
        timezone="America/Santiago",
    )
    db.add(fila)
    db.flush()
    return fila
