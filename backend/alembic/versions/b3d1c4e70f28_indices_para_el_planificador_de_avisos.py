"""Índices para el planificador de avisos.

El barrido que decide a quién le toca un recordatorio filtra `streaks` por
`last_active_date`, y esa columna no tenía índice: la tabla solo traía su clave
primaria y la unicidad por usuario, así que el filtro era un recorrido completo
cada cuarto de hora sobre una fila por usuario con personaje.

El otro índice es para los topes diarios. Antes de crear cualquier aviso se
cuenta cuántos lleva ya el usuario en su fecha local, y el único índice que había
(`user_id`, `status`) no sirve para esa consulta.

Revision ID: b3d1c4e70f28
Revises: a27579acfecf
"""

from __future__ import annotations

from alembic import op

revision = "b3d1c4e70f28"
down_revision = "a27579acfecf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_streaks_last_active_date", "streaks", ["last_active_date"])
    op.create_index(
        "ix_notifications_user_id_local_date", "notifications", ["user_id", "local_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_id_local_date", table_name="notifications")
    op.drop_index("ix_streaks_last_active_date", table_name="streaks")
