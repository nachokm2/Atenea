"""Entorno de Alembic para Atenea.

Responsabilidades de este archivo:

1. Tomar la URL de conexión de `app.core.config.settings.database_url` (12-factor),
   nunca de `alembic.ini`.
2. Importar `app.models` para que los **seis** archivos de modelos se registren y
   `Base.metadata` quede completa (52 tablas del contrato) antes del autogenerado.
3. Activar `compare_type=True` (detecta cambios de tipo) y dejar
   `render_as_batch=False` (PostgreSQL soporta `ALTER TABLE` nativo; el modo batch
   es solo para SQLite).
4. Enseñar a Alembic a **renderizar el tipo `pgvector.sqlalchemy.Vector`**: sin esto,
   el autogenerado escribiría un tipo inválido y la migración no importaría `pgvector`.

Prohibido `async` en toda la capa de datos: psycopg3 síncrono.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# `backend/` en el sys.path para poder importar `app.*` cuando alembic se invoca
# desde cualquier directorio.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings
from app.core.db import Base

# Importar el paquete de modelos es lo que puebla `Base.metadata`.
# No se puede sustituir por importaciones sueltas: deben cargarse los seis archivos.
import app.models

# Objeto de configuración de Alembic (lee alembic.ini).
config = context.config

# La URL siempre gana desde settings: `alembic.ini` la deja vacía a propósito.
# `%` se escapa porque ConfigParser lo interpreta como interpolación.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

#: Metadatos de referencia del autogenerado: las 52 tablas del contrato.
target_metadata = Base.metadata


def render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """Renderiza tipos que Alembic no sabe escribir por sí solo.

    `pgvector.sqlalchemy.Vector` no vive en `sqlalchemy` ni en su dialecto de
    PostgreSQL, así que el autogenerado produciría `Vector(512)` sin importarlo.
    Aquí devolvemos la referencia cualificada y registramos el import necesario,
    de modo que la migración generada contenga `import pgvector.sqlalchemy`.

    Devolver `False` delega en el comportamiento por defecto de Alembic.
    """
    if type_ == "type":
        module = type(obj).__module__
        if module.startswith("pgvector"):
            autogen_context.imports.add("import pgvector.sqlalchemy")  # type: ignore[attr-defined]
            dim = getattr(obj, "dim", None)
            return f"pgvector.sqlalchemy.Vector(dim={dim})" if dim else "pgvector.sqlalchemy.Vector()"
    return False


def include_object(
    obj: object,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: object,
) -> bool:
    """Filtra objetos del autogenerado.

    Los índices HNSW y GIN se crean a mano con `op.execute` (contrato §1.5), así que
    cuando se reflejan desde la base de datos no deben provocar un `drop_index`
    espurio en la siguiente migración autogenerada.
    """
    manual_indexes = {
        "ix_document_chunks_embedding_hnsw",
        "ix_document_chunks_search_vector",
        "ix_items_requirement_facts",
    }
    return not (type_ == "index" and name in manual_indexes)


def run_migrations_offline() -> None:
    """Ejecuta las migraciones en modo 'offline': emite SQL sin conectarse."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=False,
        render_item=render_item,
        include_object=include_object,
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Ejecuta las migraciones con una conexión real (psycopg3 síncrono)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=False,
            render_item=render_item,
            include_object=include_object,
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
