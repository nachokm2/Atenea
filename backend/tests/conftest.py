"""Configuración raíz de las pruebas de Atenea.

Su primer trabajo, antes de que nadie importe la aplicación, es **apuntar a una
base de datos propia**. Las pruebas siembran catálogos y parámetros de juego, y
`game_configs` tiene una restricción única por `(key, version)`: si compartieran
base con el entorno de desarrollo, dos suites sembrando la misma clave chocarían
entre sí y el resultado dependería del orden de ejecución.

Por eso aquí se fija `DATABASE_URL` a `atenea_test`, se crea el esquema una sola
vez por ejecución y cada prueba recibe una sesión envuelta en una transacción que
siempre se revierte. La base de desarrollo queda intacta.

Para apuntar a otra base, exporta `ATENEA_TEST_DATABASE_URL` antes de ejecutar.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# ATENCIÓN: esto tiene que ocurrir ANTES de importar nada de `app`, porque
# `app.core.config` lee la configuración al importarse y las variables de
# entorno tienen prioridad sobre el archivo `.env`.
# ---------------------------------------------------------------------------
URL_PRUEBAS = os.environ.get(
    "ATENEA_TEST_DATABASE_URL",
    "postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea_test",
)
os.environ["DATABASE_URL"] = URL_PRUEBAS
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "mock")

import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: E402,F401  (puebla Base.metadata con las 52 tablas)
from app.core.db import Base, engine  # noqa: E402


def _crear_esquema() -> None:
    """Deja la base de pruebas con el esquema completo, la extensión y las secuencias.

    `create_all` solo crea lo que describen los modelos: la secuencia que versiona
    `game_configs` la crea la migración con SQL explícito, así que aquí hay que
    crearla también o las suites que piden `nextval` fallarían.
    """
    with engine.begin() as conexion:
        conexion.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    with engine.begin() as conexion:
        conexion.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS game_config_version_seq START 1"))


@sa.event.listens_for(engine, "connect")
def _limites_de_espera(dbapi_conexion, _registro) -> None:
    """Ninguna prueba debe quedarse esperando un candado para siempre.

    Varias suites abren conexiones propias sobre la misma base y pueden pedir la
    misma fila. Sin estos límites, un choque se manifiesta como una ejecución
    colgada; con ellos, falla en segundos y con un mensaje que dice qué pasó.
    """
    with dbapi_conexion.cursor() as cursor:
        # Lo que importa de verdad: un candado que no llega no puede colgar la
        # ejecución. Quince segundos bastan para cualquier espera legítima.
        cursor.execute("SET lock_timeout = '15s'")
        # Varias suites abren **una** conexión para toda la ejecución, dentro de
        # una transacción que se revierte al final. Con el tope en dos minutos,
        # Postgres las mataba en cuanto la suite entera pasó de ese tiempo, y el
        # fallo aparecía como un corte de red en el desmontaje del último caso,
        # que no tenía nada que ver. El tope sigue existiendo para que una
        # transacción olvidada no quede abierta indefinidamente; solo que ahora
        # es más largo que la ejecución completa.
        cursor.execute("SET idle_in_transaction_session_timeout = '30min'")


@pytest.fixture(scope="session", autouse=True)
def esquema_de_pruebas() -> None:
    """Crea el esquema una vez por ejecución completa de la suite."""
    _crear_esquema()


@pytest.fixture()
def conexion_con_reversion(esquema_de_pruebas: None):
    """Conexión con una transacción externa que siempre se revierte.

    Aunque el código bajo prueba llame a `commit()`, la escritura queda dentro de
    esta transacción y desaparece al terminar: las pruebas no se contaminan entre
    sí ni dejan basura en la base.
    """
    conexion = engine.connect()
    transaccion = conexion.begin()
    try:
        yield conexion
    finally:
        transaccion.rollback()
        conexion.close()


@pytest.fixture()
def sesion(conexion_con_reversion) -> Session:
    """Sesión de SQLAlchemy atada a la transacción reversible."""
    sesion = Session(bind=conexion_con_reversion, join_transaction_mode="create_savepoint")
    try:
        yield sesion
    finally:
        sesion.close()
