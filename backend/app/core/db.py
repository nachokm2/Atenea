"""Base declarativa, convención de nombres, mixins comunes y sesión síncrona de Atenea.

Código normativo del contrato §1.5, verificado contra PostgreSQL 16.15 + pgvector 0.8.6
con SQLAlchemy 2.0.36. **Prohibido `async` en esta capa**: psycopg3 síncrono.
Todos los archivos de `app/models/` importan `Base` y los mixins de aquí.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import MetaData, create_engine, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import settings

# Convención de nombres: Alembic genera nombres estables y deterministas.
# Si un nombre autogenerado supera los 63 caracteres hay que pasar `name=` explícito.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa única del proyecto. Alembic autogenera desde `Base.metadata`."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    """Devuelve la columna de clave primaria estándar de Atenea.

    Azúcar sintáctico para que todas las tablas declaren exactamente la misma PK:
    `id: Mapped[uuid.UUID] = uuid_pk()`. Equivale a heredar de `UUIDPrimaryKeyMixin`.
    """
    return mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class UUIDPrimaryKeyMixin:
    """Clave primaria UUID estándar de Atenea."""

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class CreatedAtMixin:
    """Solo fecha de creación: para tablas append-only (ledgers, eventos, evidencias)."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    """Fechas de creación y actualización, en UTC."""

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Motor y sesión (síncronos)
# ---------------------------------------------------------------------------

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Abre una sesión transaccional: confirma al salir bien, revierte ante cualquier error.

    Uso fuera de FastAPI (worker, semillas, scripts)::

        with session_scope() as db:
            db.add(fila)
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una **unidad de trabajo por petición**.

    La petición entera es una sola transacción: si el manejador termina bien se
    confirma, y si lanza una excepción se revierte por completo. Un caso de uso
    puede seguir llamando a `commit()` cuando necesite cerrar la transacción
    antes de tiempo (por ejemplo, para que un trabajo encolado vea los datos);
    el `commit()` final de aquí es entonces inofensivo.

    Este es el contrato que esperan los módulos: ninguno debe quedarse a medias
    por olvidar confirmar, y ninguna respuesta con código de éxito puede dejar
    cambios sin persistir.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "NAMING_CONVENTION",
    "Base",
    "CreatedAtMixin",
    "SessionLocal",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "engine",
    "get_db",
    "session_scope",
    "uuid_pk",
]
