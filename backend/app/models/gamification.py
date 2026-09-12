"""Modelos del módulo `gamification` de Atenea (CONTRACT.md §3.5).

Aquí vive todo lo que convierte el aprendizaje demostrado en progresión de juego:

- `domain_events`: bitácora única de eventos de dominio; es el bus del MVP.
- `xp_transactions`: ledger append-only de XP (única fuente de verdad de la ⭐).
- `level_definitions`: las dos curvas de nivel materializadas (global y por conocimiento).
- `streaks` y `streak_days`: racha y calendario por fecha local del usuario.
- `daily_goals`: objetivo diario vigente, cambio pendiente y recomendación adaptativa.
- `mission_templates` y `user_missions`: catálogo determinista de misiones e instancias.
- `achievements` y `user_achievements`: catálogo de logros y progreso por usuario.
- `reward_rules`: regla declarativa evento → recompensa (sustituye constantes en código).
- `game_configs`: configuración versionada de todo valor de juego.
- `notifications`: notificaciones in-app y push, con programación y antifatiga.

Reglas del contrato respetadas en este archivo:

- Ninguna importación de otros archivos de `app/models/` salvo `enums`; las claves
  foráneas apuntan a las tablas de otros módulos **por texto** (§1.4 regla 8).
- `relationship()` solo entre clases declaradas aquí mismo.
- Los enums se persisten como `VARCHAR(48)` sin `CHECK` y guardan el **nombre** del
  miembro en MAYÚSCULAS: por eso cada `server_default` usa `Enum.MIEMBRO.name` (§1.4 regla 6).
- Las tablas append-only (`domain_events`, `xp_transactions`) llevan solo `created_at`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AchievementCategory,
    AchievementTier,
    AchievementVisibility,
    DayStatus,
    EventStatus,
    EventType,
    GoalType,
    GoldSource,
    LevelScope,
    MissionScope,
    MissionStatus,
    MissionTier,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    StreakChange,
    XPSource,
)

# ---------------------------------------------------------------------------
# Bus de eventos de dominio
# ---------------------------------------------------------------------------


class DomainEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Bitácora única de eventos de dominio: el bus del MVP (CONTRACT.md §4).

    Los productores de cualquier módulo insertan una fila; el motor de gamificación
    la consume en la misma transacción (mecánicas rápidas: XP, oro, racha, objetivo)
    o en el worker (logros y desbloqueos). Es append-only en su contenido de negocio:
    los únicos campos mutables son `processing_status`, `processed_at` y
    `error_message`, por eso la tabla no lleva `updated_at`.
    """

    __tablename__ = "domain_events"

    event_type: Mapped[EventType] = mapped_column(
        sa.Enum(EventType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        # Nulo en eventos de sistema (p. ej. AI_BUDGET_THRESHOLD).
    )
    occurred_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        # Momento del hecho: se acepta la marca del cliente si difiere <= 10 min.
    )
    received_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    local_date: Mapped[date | None] = mapped_column(
        sa.Date,
        nullable=True,
        # La calcula el servidor al ingerir y viaja con el evento: todos los
        # consumidores comparten la misma fecha local (§4.1).
    )
    timezone: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    version: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("1"),
        # Versión del contrato del payload, no de la fila.
    )
    source_module: Mapped[str] = mapped_column(
        sa.String(24),
        nullable=False,
        # identity, content, ingestion, ai, progress, gamification, economy, client.
    )
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        nullable=True,
        # Agrupa la cascada de eventos de una misma acción del usuario.
    )
    causation_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("domain_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    processing_status: Mapped[EventStatus] = mapped_column(
        sa.Enum(EventStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        server_default=EventStatus.PENDING.name,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(
        sa.String(120),
        nullable=False,
        # Única global: reprocesar el mismo hecho no duplica efectos.
    )

    # Autorreferencia permitida: ambas puntas son esta misma clase (§1.4 regla 8).
    caused_by: Mapped[DomainEvent | None] = relationship(
        "DomainEvent",
        remote_side="DomainEvent.id",
        back_populates="caused_events",
        lazy="raise",
    )
    caused_events: Mapped[list[DomainEvent]] = relationship(
        "DomainEvent",
        back_populates="caused_by",
        lazy="raise",
    )

    __table_args__ = (
        sa.UniqueConstraint("idempotency_key"),
        sa.Index("ix_domain_events_user_id_occurred_at", "user_id", "occurred_at"),
        sa.Index("ix_domain_events_event_type_occurred_at", "event_type", "occurred_at"),
        sa.Index(
            "ix_domain_events_processing_status_occurred_at",
            "processing_status",
            "occurred_at",
        ),
    )


# ---------------------------------------------------------------------------
# XP: ledger y curvas de nivel
# ---------------------------------------------------------------------------


class XPTransaction(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Ledger append-only de XP: la única fuente de verdad de la ⭐ (CONTRACT.md §6.2).

    Prohibido `UPDATE` y `DELETE`. Los saldos cacheados (`characters.xp_total`,
    `user_area_progress.xp`) se recalculan desde aquí y se reconcilian de noche.
    Una misma transacción alimenta a la vez el XP global y el XP del conocimiento.
    """

    __tablename__ = "xp_transactions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("domain_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[EventType] = mapped_column(
        sa.Enum(EventType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        # Desnormalizado para que la analítica no tenga que unirse a domain_events.
    )
    source: Mapped[XPSource] = mapped_column(
        sa.Enum(XPSource, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        nullable=True,
        # Id de la lección, misión, logro… Sin FK: apunta a tablas distintas según `source`.
    )
    knowledge_area_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("knowledge_areas.id", ondelete="SET NULL"),
        nullable=True,
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_educational: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.true(),
        # true = cuenta para el objetivo diario y el día activo; false = bonificación.
    )
    base_amount: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 3),
        nullable=False,
        server_default=sa.text("1.000"),
        # Producto de todos los multiplicadores aplicados (repetición, topes…).
    )
    amount: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    reason_code: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        # first_completion, repeat_20, repeat_0, question_first_try, question_second_try,
        # question_cap_reached, time_too_short, answer_too_fast, daily_softcap_50,
        # daily_softcap_10, low_content_50, admin_adjustment.
    )
    config_version: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        # Versión de `game_configs` vigente al calcular: hace auditable el importe.
    )
    balance_after: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    local_date: Mapped[date] = mapped_column(
        sa.Date,
        nullable=False,
        # Fecha local del usuario: base de los topes diarios blandos.
    )
    idempotency_key: Mapped[str] = mapped_column(sa.String(120), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint("user_id", "idempotency_key"),
        sa.Index("ix_xp_transactions_user_id_created_at", "user_id", "created_at"),
        sa.Index(
            "ix_xp_transactions_user_id_knowledge_area_id", "user_id", "knowledge_area_id"
        ),
        sa.Index("ix_xp_transactions_user_id_local_date", "user_id", "local_date"),
        sa.CheckConstraint(
            "amount >= 0 OR source = 'ADJUSTMENT'",
            name="amount_sign",
            # El XP nunca baja salvo por un ajuste administrativo explícito.
        ),
    )


class LevelDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tabla materializada de las dos curvas de nivel (CONTRACT.md §6.1).

    `GLOBAL` (base 80) es la progresión del personaje; `KNOWLEDGE_AREA` (base 50)
    es el nivel dentro de un conocimiento. Se siembra al arrancar desde `game_configs`
    para que la conversión XP → nivel sea una consulta y no un cálculo en código.
    """

    __tablename__ = "level_definitions"

    scope: Mapped[LevelScope] = mapped_column(
        sa.Enum(LevelScope, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    level: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    xp_required: Mapped[int] = mapped_column(
        sa.BigInteger,
        nullable=False,
        # XP acumulado (no incremental) necesario para alcanzar este nivel.
    )
    xp_delta: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # XP entre este nivel y el anterior; útil para la barra de progreso.
    )
    rank_title: Mapped[str] = mapped_column(sa.String(48), nullable=False)
    is_rank_start: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.false(),
        # true en 1, 5, 10, 15, 20, 25, 30, 35, 40, 45 y 50: dispara RANK_UP.
    )
    unlocks: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        # {"shop_rarities": ["uncommon"], "gold_bonus": 100}
    )

    __table_args__ = (sa.UniqueConstraint("scope", "level"),)


# ---------------------------------------------------------------------------
# Racha, calendario y objetivo diario
# ---------------------------------------------------------------------------


class Streak(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Estado materializado de la racha del usuario (CONTRACT.md §6.10).

    Es una caché: siempre se puede recomputar íntegramente desde `streak_days`.
    Una fila por usuario.
    """

    __tablename__ = "streaks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    current_length: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    best_length: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # Mejor racha histórica: nunca disminuye.
    )
    last_active_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    started_on: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    total_active_days: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # Días activos de por vida (alimenta el logro Peregrino/a).
    )
    grace_used_for_month: Mapped[str | None] = mapped_column(
        sa.String(7),
        nullable=True,
        # Mes en formato "2026-09" en el que ya se consumió el día de gracia.
    )
    travel_skip_used_on: Mapped[date | None] = mapped_column(
        sa.Date,
        nullable=True,
        # Último ajuste por viaje: como máximo uno cada 30 días.
    )
    last_change: Mapped[StreakChange | None] = mapped_column(
        sa.Enum(StreakChange, native_enum=False, length=48, validate_strings=True),
        nullable=True,
    )
    last_milestone_reached: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # Último hito de racha ya recompensado: evita repetir el premio.
    )
    broken_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    previous_length: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # Longitud de la racha anterior: "Última racha: 21 días".
    )

    __table_args__ = (sa.UniqueConstraint("user_id"),)


class StreakDay(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Agregado por usuario y fecha local (CONTRACT.md §6.10 y §6.11).

    Fuente de verdad del calendario, del concepto de "día activo" y del objetivo
    diario. Todo consumidor usa la `local_date` que viaja en el evento, nunca la
    fecha del servidor.
    """

    __tablename__ = "streak_days"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    local_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    educational_xp: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # Piso de día activo: 30 XP educativo.
    )
    bonus_xp: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # No cuenta para el día activo ni para el objetivo diario.
    )
    effective_seconds: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    activity_units: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # Lección 1, 5 preguntas 1, repaso 1, desafío 1, evaluación 2.
    )
    lessons_completed: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    questions_total: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    questions_correct: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    activities_completed: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    goal_type_snapshot: Mapped[GoalType | None] = mapped_column(
        sa.Enum(GoalType, native_enum=False, length=48, validate_strings=True),
        nullable=True,
        # Objetivo vigente al empezar el día: histórico auditable aunque luego cambie.
    )
    goal_target_snapshot: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    goal_progress: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # Avance expresado en la unidad de `goal_type_snapshot`.
    )
    goal_met_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        # Idempotente: el objetivo se cumple una sola vez al día.
    )
    day_status: Mapped[DayStatus] = mapped_column(
        sa.Enum(DayStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        server_default=DayStatus.INACTIVE.name,
    )
    first_activity_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        # Dispara el bono +20 XP del día y alimenta la "hora habitual de estudio".
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    xp_softcap_applied: Mapped[str | None] = mapped_column(
        sa.String(24),
        nullable=True,
        # none, daily_softcap_50, daily_softcap_10.
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "local_date"),
        # La consulta del calendario recorre las fechas de la más reciente hacia atrás.
        sa.Index(
            "ix_streak_days_user_id_local_date", "user_id", sa.text("local_date DESC")
        ),
    )


class DailyGoal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Objetivo diario del usuario (CONTRACT.md §6.11). Una fila por usuario.

    Guarda el objetivo vigente, el cambio programado (las bajadas rigen al día
    siguiente para que no se pueda "ganar" el día rebajando la meta) y la
    recomendación adaptativa calculada por el sistema.
    """

    __tablename__ = "daily_goals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    goal_type: Mapped[GoalType] = mapped_column(
        sa.Enum(GoalType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        server_default=GoalType.MINUTES.name,
    )
    target: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("20")
    )
    effective_from: Mapped[date] = mapped_column(sa.Date, nullable=False)
    pending_type: Mapped[GoalType | None] = mapped_column(
        sa.Enum(GoalType, native_enum=False, length=48, validate_strings=True),
        nullable=True,
    )
    pending_target: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    pending_from: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    recommendation: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        # {direction, suggested_type, suggested_target, computed_on}
    )
    recommendation_shown_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    recommendation_rejected_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        # Tras un rechazo no se vuelve a sugerir en 28 días.
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id"),
        sa.CheckConstraint("target > 0", name="target_positive"),
    )


# ---------------------------------------------------------------------------
# Misiones
# ---------------------------------------------------------------------------


class MissionTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Catálogo de plantillas de misión parametrizadas (CONTRACT.md §5.7).

    Sin IA: el selector diario es determinista y ponderado. Las plantillas se
    instancian en `user_missions` congelando `version` y los parámetros resueltos.
    """

    __tablename__ = "mission_templates"

    code: Mapped[str] = mapped_column(
        sa.String(24),
        nullable=False,
        # D01…D13 (diarias), S01…S04 (especiales), W01…W06 (semanales).
    )
    scope: Mapped[MissionScope] = mapped_column(
        sa.Enum(MissionScope, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    title_template: Mapped[str] = mapped_column(
        sa.String(160),
        nullable=False,
        # Plantilla interpolable: "Completa {n} lecciones".
    )
    narrative_key: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    metric: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        # {type, event, where, field} — `type` es un valor de MissionMetricType.
    )
    params: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        # {"n": {"easy": 1, "medium": 2, "hard": 3}}
    )
    target_scope: Mapped[str] = mapped_column(
        sa.String(24),
        nullable=False,
        server_default="any",
        # any, knowledge_area, path.
    )
    eligibility: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
        # Predicados: has_weak_topic, has_available_assessment, has_unstarted_topic,
        # has_failed_questions_gte, active_areas_gte, streak_gte, has_available_challenge.
    )
    exclude_if_goal_type: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
        # Evita asignar una misión que duplique el objetivo diario vigente.
    )
    reward_profile: Mapped[str] = mapped_column(
        sa.String(24),
        nullable=False,
        server_default="daily_default",
        # daily_default, weekly_default, path_special.
    )
    rewards: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        # Recompensa explícita cuando no se usa un perfil.
    )
    weight: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("1"),
        # Peso en la selección ponderada del día.
    )
    version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.true(),
        # Las semanales se siembran con false en el MVP.
    )

    instances: Mapped[list[UserMission]] = relationship(
        "UserMission", back_populates="template", lazy="raise"
    )

    __table_args__ = (sa.UniqueConstraint("code"),)


class UserMission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Instancia de una misión asignada a un usuario (CONTRACT.md §5.7).

    Las diarias se asignan por `assigned_for` (fecha local) y expiran a medianoche
    local; las de ruta (`especial`) se instancian al crear la ruta y no expiran.
    El progreso se aplica evento a evento y `last_event_id` lo hace idempotente.
    """

    __tablename__ = "user_missions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("mission_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    template_code: Mapped[str] = mapped_column(
        sa.String(24),
        nullable=False,
        # Desnormalizado: la analítica no necesita unirse a mission_templates.
    )
    template_version: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("1"),
        # Versión congelada al asignar: cambiar la plantilla no altera lo ya repartido.
    )
    scope: Mapped[MissionScope] = mapped_column(
        sa.Enum(MissionScope, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    tier: Mapped[MissionTier | None] = mapped_column(
        sa.Enum(MissionTier, native_enum=False, length=48, validate_strings=True),
        nullable=True,
    )
    params: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        # Parámetros ya resueltos para el tier elegido.
    )
    title: Mapped[str] = mapped_column(
        sa.String(200),
        nullable=False,
        # Título ya interpolado, listo para mostrar.
    )
    target: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    progress: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # Se actualiza siempre como LEAST(target, progress + delta).
    )
    status: Mapped[MissionStatus] = mapped_column(
        sa.Enum(MissionStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        server_default=MissionStatus.ACTIVE.name,
    )
    learning_path_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=True,
        # Presente solo en las misiones de ruta.
    )
    knowledge_area_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("knowledge_areas.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_for: Mapped[date | None] = mapped_column(
        sa.Date,
        nullable=True,
        # Fecha local de asignación: solo las diarias la usan.
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        # Medianoche local; nulo en misiones de ruta.
    )
    reward_xp: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # XP de bonificación: no cuenta para el objetivo diario.
    )
    reward_gold: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    reward_item_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("items.id", ondelete="SET NULL"),
        nullable=True,
        # Solo en misiones especiales.
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        # El reclamo es automático si la misión expira ya completada.
    )
    last_event_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("domain_events.id", ondelete="SET NULL"),
        nullable=True,
        # Idempotencia del progreso: un evento reprocesado no vuelve a sumar.
    )

    template: Mapped[MissionTemplate] = relationship(
        "MissionTemplate", back_populates="instances", lazy="raise"
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "template_id", "assigned_for"),
        sa.Index(
            "ix_user_missions_user_id_status_expires_at",
            "user_id",
            "status",
            "expires_at",
        ),
        sa.Index("ix_user_missions_learning_path_id", "learning_path_id"),
    )


# ---------------------------------------------------------------------------
# Logros
# ---------------------------------------------------------------------------


class Achievement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Catálogo de logros con reglas declarativas y niveles (CONTRACT.md §5.7).

    La regla se evalúa contra los eventos de dominio; los niveles (bronce, plata,
    oro o `single`) llevan objetivos crecientes y su propia recompensa.
    """

    __tablename__ = "achievements"

    code: Mapped[str] = mapped_column(
        sa.String(48),
        nullable=False,
        # ACH_ORACLE, ACH_FLAME_KEEPER…
    )
    name: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
        # Descripción visible o, si el logro es oculto, la pista.
    )
    category: Mapped[AchievementCategory] = mapped_column(
        sa.Enum(AchievementCategory, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    visibility: Mapped[AchievementVisibility] = mapped_column(
        sa.Enum(AchievementVisibility, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        server_default=AchievementVisibility.VISIBLE.name,
    )
    rule: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        # {type, event, where, success_when, reset_when, stat, op, on_events}
    )
    tiers: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
        # [{tier, target, reward:{xp, gold, title_id}}] con objetivos crecientes.
    )
    icon_key: Mapped[str | None] = mapped_column(sa.String(48), nullable=True)
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("100")
    )
    version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.true(),
        # Permite retirar un logro sin borrar el progreso de nadie.
    )

    user_progress: Mapped[list[UserAchievement]] = relationship(
        "UserAchievement", back_populates="achievement", lazy="raise"
    )

    __table_args__ = (sa.UniqueConstraint("code"),)


class UserAchievement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Progreso y niveles desbloqueados de un logro para un usuario.

    Una única fila por par usuario-logro: acumula el estado de la regla
    (contador, racha consecutiva, valores distintos) y la lista de niveles ya
    conseguidos con su recompensa.
    """

    __tablename__ = "user_achievements"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    achievement_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("achievements.id", ondelete="CASCADE"),
        nullable=False,
    )
    counter: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # Estado de las reglas counter / sum / stat_threshold.
    )
    current_consecutive: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # Racha en curso de la regla `consecutive`.
    )
    max_consecutive: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    distinct_values: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
        # Valores ya vistos para la regla `distinct_count`.
    )
    highest_tier: Mapped[AchievementTier | None] = mapped_column(
        sa.Enum(AchievementTier, native_enum=False, length=48, validate_strings=True),
        nullable=True,
    )
    unlocked_tiers: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
        # [{tier, unlocked_at, reward_xp, reward_gold, title_id, reward_granted}]
    )
    progress_pct: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2),
        nullable=False,
        server_default=sa.text("0"),
        # Avance hacia el próximo nivel: "casi lo tienes" a partir del 80 %.
    )
    first_unlocked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_unlocked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_event_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("domain_events.id", ondelete="SET NULL"),
        nullable=True,
        # Idempotencia: un evento reprocesado no vuelve a avanzar el logro.
    )

    achievement: Mapped[Achievement] = relationship(
        "Achievement", back_populates="user_progress", lazy="raise"
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "achievement_id"),
        sa.Index("ix_user_achievements_user_id_highest_tier", "user_id", "highest_tier"),
    )


# ---------------------------------------------------------------------------
# Reglas de recompensa y configuración de juego
# ---------------------------------------------------------------------------


class RewardRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Regla declarativa evento → recompensa (CONTRACT.md §3.5).

    Sustituye a cualquier constante de XP u oro en el código: el motor consulta
    esta tabla y, si la regla declara `xp_config_key` o `gold_config_key`, el
    importe se lee de `game_configs` en lugar de la columna literal.
    """

    __tablename__ = "reward_rules"

    code: Mapped[str] = mapped_column(
        sa.String(48),
        nullable=False,
        # lesson_completed_base, assessment_bonus_90…
    )
    event_type: Mapped[EventType] = mapped_column(
        sa.Enum(EventType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    condition: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        # {"passed": true, "score_pct_gte": 90}
    )
    xp_amount: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
        # Ignorado si hay `xp_config_key`.
    )
    xp_config_key: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    xp_source: Mapped[XPSource | None] = mapped_column(
        sa.Enum(XPSource, native_enum=False, length=48, validate_strings=True),
        nullable=True,
    )
    is_educational: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    gold_amount: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    gold_config_key: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    gold_source: Mapped[GoldSource | None] = mapped_column(
        sa.Enum(GoldSource, native_enum=False, length=48, validate_strings=True),
        nullable=True,
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("items.id", ondelete="SET NULL"),
        nullable=True,
    )
    first_time_only: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.true(),
        # Regla A1: la recompensa plena solo la primera vez.
    )
    respects_daily_cap: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    respects_repeat_multiplier: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.true(),
        # Multiplicadores de repetición 1.0 / 0.2 / 0.0.
    )
    priority: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("100"),
        # Orden de evaluación entre reglas del mismo evento.
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    valid_from: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        # Nulo = vigente.
    )

    __table_args__ = (
        sa.UniqueConstraint("code"),
        sa.Index("ix_reward_rules_event_type_is_active", "event_type", "is_active"),
    )


class GameConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Configuración versionada de todo valor de juego (CONTRACT.md §5).

    Ningún número de balance se escribe en el código. El valor vigente es la fila
    con `valid_from <= now() < coalesce(valid_to, 'infinity')` y mayor `version`;
    el backend la cachea en memoria con TTL de 60 s.
    """

    __tablename__ = "game_configs"

    key: Mapped[str] = mapped_column(
        sa.String(80),
        nullable=False,
        # Clave con espacio de nombres: "xp.lesson_completed".
    )
    version: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("1"),
        # Versión incremental por clave.
    )
    config_version: Mapped[int] = mapped_column(
        sa.BigInteger,
        nullable=False,
        # Contador global monótono: nextval('game_config_version_seq'), secuencia
        # creada en la migración inicial. Se copia a cada transacción de XP y oro.
    )
    value: Mapped[dict | list | str | int | float | bool] = mapped_column(
        JSONB,
        nullable=False,
        # Escalar, lista o mapa, según `value_type`.
    )
    value_type: Mapped[str] = mapped_column(
        sa.String(12),
        nullable=False,
        # int, decimal, bool, string, list, map.
    )
    valid_from: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        # Nulo = vigente.
    )
    is_public: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.false(),
        # true = se expone en GET /api/v1/config/public.
    )
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        sa.UniqueConstraint("key", "version"),
        sa.Index("ix_game_configs_key_valid_from", "key", "valid_from"),
    )


# ---------------------------------------------------------------------------
# Notificaciones
# ---------------------------------------------------------------------------


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Notificación in-app o push, con programación y antifatiga.

    El programador respeta las horas de silencio del usuario y los topes por día;
    `idempotency_key` impide que un reintento genere duplicados. Los textos son en
    español, con tono de recuperación y sin culpabilizar.
    """

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        sa.Enum(NotificationType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        sa.Enum(NotificationChannel, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        server_default=NotificationChannel.IN_APP.name,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        sa.Enum(NotificationStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        server_default=NotificationStatus.PENDING.name,
    )
    title: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    body: Mapped[str] = mapped_column(sa.String(400), nullable=False)
    deep_link: Mapped[str | None] = mapped_column(
        sa.String(160),
        nullable=True,
        # home, streak, missions, route/{id}.
    )
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        # Envío programado: respeta las horas de silencio.
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    local_date: Mapped[date | None] = mapped_column(
        sa.Date,
        nullable=True,
        # Fecha local: base de los topes de notificaciones por día.
    )
    idempotency_key: Mapped[str] = mapped_column(sa.String(120), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint("idempotency_key"),
        sa.Index("ix_notifications_user_id_status", "user_id", "status"),
        sa.Index("ix_notifications_scheduled_for", "scheduled_for"),
    )


__all__ = [
    "Achievement",
    "DailyGoal",
    "DomainEvent",
    "GameConfig",
    "LevelDefinition",
    "MissionTemplate",
    "Notification",
    "RewardRule",
    "Streak",
    "StreakDay",
    "UserAchievement",
    "UserMission",
    "XPTransaction",
]
