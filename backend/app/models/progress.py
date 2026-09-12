"""Modelos del módulo `progress`: lo que **cada usuario** hizo, cuánto tiempo dedicó
y cuánto dominio demostró.

Contrato §3.4. Este archivo nunca describe contenido reutilizable (eso vive en
`app/models/content.py`): aquí solo hay progreso por usuario, evidencias de respuesta,
agregados de dominio y contabilidad de tiempo.

Los tres medidores del sistema se mantienen **separados** (contrato §1.1):

* ⭐ **XP** — se paga desde el ledger `xp_transactions` (módulo `gamification`); aquí
  solo se cachean los importes ya otorgados (`xp_awarded`) para auditoría rápida.
* ⏱ **Tiempo** — `learning_sessions.active_seconds` y `study_activities.active_seconds`.
* 🧠 **Dominio** — se calcula desde `question_attempts` y `assessment_attempts` y se
  materializa en `user_topic_progress`, `user_module_progress` y `user_area_progress`.

El tiempo nunca alimenta XP ni dominio; el dominio sí puede bajar por decaimiento.

Reglas de construcción aplicadas (contrato §1.4):

* Claves foráneas **por texto** (`"users.id"`): prohibido importar otro archivo de
  `app/models/`. `relationship()` solo entre clases de este mismo archivo.
* Los enums se persisten por el **nombre del miembro en MAYÚSCULAS**; por eso todo
  `server_default` de una columna de enum se escribe con `.name`.
* `question_attempts` es **append-only**: solo `created_at` (`CreatedAtMixin`).
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
    ActivityContext,
    AssessmentOutcome,
    AttemptResult,
    AttemptStatus,
    DifficultyLevel,
    EvaluationMethod,
    KnowledgeAreaStatus,
    ModuleStatus,
    ProgressState,
    SessionEndReason,
    StudyActivityType,
)

# Abreviaturas locales para no repetir la receta del contrato en cada columna.
UUIDc = postgresql.UUID(as_uuid=True)


def _enum(enum_class: type) -> sa.Enum:
    """Receta única de columna de enum del contrato §1.4, regla 6.

    Produce un `VARCHAR(48)` sin `CHECK`; SQLAlchemy guarda el **nombre** del miembro.
    """
    return sa.Enum(enum_class, native_enum=False, length=48, validate_strings=True)


# ---------------------------------------------------------------------------
# Tiempo de estudio: sesiones y actividades
# ---------------------------------------------------------------------------


class LearningSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ventana de actividad del usuario: agrupa actividades y acumula tiempo efectivo.

    Se abre con la primera interacción educativa y se cierra a los 10 minutos de
    inactividad (o cuando la app lo informa). Es la fuente de verdad del medidor ⏱:
    nunca alimenta XP ni dominio.
    """

    __tablename__ = "learning_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: Último latido aceptado por el servidor; base del cierre por inactividad.
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    #: Suma de latidos válidos; cada latido aporta como máximo 60 s.
    active_seconds: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    #: Fecha local del usuario al iniciar la sesión (define el día activo).
    local_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    device: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    end_reason: Mapped[SessionEndReason | None] = mapped_column(
        _enum(SessionEndReason), nullable=True
    )

    activities: Mapped[list[StudyActivity]] = relationship(
        back_populates="session", passive_deletes=True
    )

    __table_args__ = (
        sa.Index("ix_learning_sessions_user_id_started_at", "user_id", "started_at"),
        sa.Index("ix_learning_sessions_user_id_local_date", "user_id", "local_date"),
        sa.CheckConstraint("active_seconds >= 0", name="active_seconds_non_negative"),
    )


class StudyActivity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Intento de actividad: la lección, práctica, repaso, desafío o evaluación abierta.

    Es la unidad que se completa, la que valida el tiempo mínimo plausible y la que
    dispara las recompensas. Todas las dimensiones (tema, módulo, ruta, conocimiento)
    se desnormalizan aquí para que la analítica y los topes diarios no necesiten joins.
    """

    __tablename__ = "study_activities"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("learning_sessions.id", ondelete="SET NULL"), nullable=True
    )
    activity_type: Mapped[StudyActivityType] = mapped_column(
        _enum(StudyActivityType), nullable=False
    )
    #: Expira a las 2 h de inactividad (`xp.attempt_ttl_hours`).
    status: Mapped[AttemptStatus] = mapped_column(
        _enum(AttemptStatus),
        nullable=False,
        server_default=AttemptStatus.IN_PROGRESS.name,
    )
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True
    )
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("path_modules.id", ondelete="SET NULL"), nullable=True
    )
    learning_path_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("learning_paths.id", ondelete="SET NULL"), nullable=True
    )
    #: Dimensión de XP y de dominio: todo se contabiliza por conocimiento.
    knowledge_area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("knowledge_areas.id", ondelete="SET NULL"), nullable=True
    )
    #: Reloj **del servidor**: el cliente nunca fija el inicio.
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    #: `completed_at − started_at` medido por el servidor.
    elapsed_seconds: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    #: Tiempo efectivo con tope de 3× la duración estimada de la actividad.
    active_seconds: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    #: Tiempo bruto informado por los latidos, sin topes; solo auditoría antiabuso.
    reported_seconds: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    questions_total: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    questions_correct: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    accuracy_pct: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 2), nullable=True)
    #: Regla antirrepetición A1: 1ª finalización paga 100 %, 2ª 20 %, 3ª en adelante 0 %.
    completion_index: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    #: `false` si es repetición trivial o duró menos del mínimo plausible.
    counts_for_progress: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    #: Espejo del ledger de XP; el ledger sigue siendo la fuente de verdad.
    xp_awarded: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    gold_awarded: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    #: Fecha local del usuario: día activo, racha y topes diarios.
    local_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    #: Clave enviada por el cliente al abrir la actividad; evita duplicar recompensas.
    idempotency_key: Mapped[str] = mapped_column(sa.String(120), nullable=False)

    session: Mapped[LearningSession | None] = relationship(back_populates="activities")
    question_attempts: Mapped[list[QuestionAttempt]] = relationship(
        back_populates="study_activity", passive_deletes=True
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "idempotency_key"),
        sa.Index("ix_study_activities_user_id_local_date", "user_id", "local_date"),
        sa.Index("ix_study_activities_user_id_status", "user_id", "status"),
        sa.Index("ix_study_activities_lesson_id", "lesson_id"),
        sa.CheckConstraint(
            "elapsed_seconds >= 0 AND active_seconds >= 0 AND reported_seconds >= 0",
            name="seconds_non_negative",
        ),
        sa.CheckConstraint(
            "questions_total >= 0 AND questions_correct >= 0 "
            "AND questions_correct <= questions_total",
            name="questions_coherent",
        ),
        sa.CheckConstraint(
            "accuracy_pct IS NULL OR (accuracy_pct >= 0 AND accuracy_pct <= 100)",
            name="accuracy_pct_range",
        ),
        sa.CheckConstraint("completion_index >= 1", name="completion_index_positive"),
        sa.CheckConstraint(
            "xp_awarded >= 0 AND gold_awarded >= 0", name="rewards_non_negative"
        ),
    )


# ---------------------------------------------------------------------------
# Evidencias: respuestas e intentos de evaluación
# ---------------------------------------------------------------------------


class QuestionAttempt(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Evidencia de dominio: una fila por respuesta del usuario. **Append-only**.

    Jamás se hace `UPDATE` ni `DELETE` sobre esta tabla: es el sustrato desde el que se
    recalcula `P_t` (y por tanto todo el dominio). Copia la dificultad y el contexto del
    momento de responder para que un cambio posterior del contenido no reescriba la
    historia.
    """

    __tablename__ = "question_attempts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    #: Tema al que se agrega la evidencia de dominio.
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("knowledge_areas.id", ondelete="SET NULL"), nullable=True
    )
    study_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("study_activities.id", ondelete="SET NULL"), nullable=True
    )
    assessment_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc,
        sa.ForeignKey("assessment_attempts.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: Peso de contexto en el dominio: lección 1.0, repaso 1.0, desafío 1.5, evaluación 2.0.
    context: Mapped[ActivityContext] = mapped_column(_enum(ActivityContext), nullable=False)
    #: Nº de intento sobre la misma pregunta dentro de la actividad.
    attempt_no: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    response: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    result: Mapped[AttemptResult] = mapped_column(_enum(AttemptResult), nullable=False)
    #: Atajo booleano para misiones y logros; no sustituye a `result`.
    is_correct: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    #: Crédito parcial 0–100 (relacionar, ordenar, respuesta abierta).
    partial_score: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")
    )
    #: `c` de la fórmula de dominio: 1.00 correcto, 0.50 parcial, 0.00 incorrecto.
    correctness_weight: Mapped[Decimal] = mapped_column(
        sa.Numeric(3, 2), nullable=False, server_default=sa.text("0")
    )
    #: Copiada de la pregunta al responder (pesos 1.0 / 1.5 / 2.0).
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        _enum(DifficultyLevel), nullable=False
    )
    evaluation_method: Mapped[EvaluationMethod] = mapped_column(
        _enum(EvaluationMethod), nullable=False
    )
    #: Confianza del juez LLM; por debajo de 0.60 se escala a un modelo mayor.
    judge_confidence: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(3, 2), nullable=True
    )
    #: Rúbrica evaluada, `verdict`, `flags` y retroalimentación del juez.
    judge_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    #: Regla antiabuso A4: por debajo de 2 000 ms la respuesta no paga XP.
    response_ms: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    #: Reservado para el multiplicador "sin ayuda".
    hint_used: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    #: Revancha sobre una pregunta fallada (misión D12, logro Revancha).
    is_retry_of_failed: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    #: Alimenta objetivo diario, misiones y logros.
    counts_for_progress: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    #: `false` cuando el resultado quedó en `NEEDS_REVIEW`: no mueve el dominio.
    counts_for_mastery: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    xp_awarded: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    #: Marca del servidor: base del decaimiento y de las ventanas antiabuso.
    answered_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    local_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(sa.String(120), nullable=False)

    study_activity: Mapped[StudyActivity | None] = relationship(
        back_populates="question_attempts"
    )
    assessment_attempt: Mapped[AssessmentAttempt | None] = relationship(
        back_populates="question_attempts"
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "idempotency_key"),
        sa.Index(
            "ix_question_attempts_user_id_topic_id_answered_at",
            "user_id",
            "topic_id",
            "answered_at",
        ),
        sa.Index("ix_question_attempts_question_id", "question_id"),
        sa.Index("ix_question_attempts_user_id_local_date", "user_id", "local_date"),
        sa.CheckConstraint("attempt_no >= 1", name="attempt_no_positive"),
        sa.CheckConstraint(
            "partial_score >= 0 AND partial_score <= 100", name="partial_score_range"
        ),
        sa.CheckConstraint(
            "correctness_weight >= 0 AND correctness_weight <= 1",
            name="correctness_weight_range",
        ),
        sa.CheckConstraint(
            "judge_confidence IS NULL OR (judge_confidence >= 0 AND judge_confidence <= 1)",
            name="judge_confidence_range",
        ),
        sa.CheckConstraint("response_ms >= 0", name="response_ms_non_negative"),
        sa.CheckConstraint("xp_awarded >= 0", name="xp_awarded_non_negative"),
    )


class AssessmentAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Intento de evaluación de módulo: banco muestreado, puntaje y enfriamiento.

    `effective_score` (`E_mod`) es el puntaje bruto penalizado en 0.05 por cada intento
    previo; entra con peso 0.30 en el dominio del módulo. El enfriamiento tras reprobar
    (4 h / 24 h / 48 h) puede anularse completando el repaso recomendado.
    """

    __tablename__ = "assessment_attempts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
    )
    #: Módulo desnormalizado: evita un join en el desbloqueo progresivo.
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("path_modules.id", ondelete="CASCADE"), nullable=False
    )
    learning_path_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("learning_paths.id", ondelete="SET NULL"), nullable=True
    )
    knowledge_area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("knowledge_areas.id", ondelete="SET NULL"), nullable=True
    )
    #: Penaliza `E_mod` en 0.05 por cada intento previo.
    attempt_no: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    status: Mapped[AttemptStatus] = mapped_column(
        _enum(AttemptStatus),
        nullable=False,
        server_default=AttemptStatus.IN_PROGRESS.name,
    )
    #: Preguntas muestreadas; el solapamiento con el intento previo no supera el 30 %.
    question_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    question_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("10")
    )
    correct_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    score: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 2), nullable=True)
    #: `E_mod`: puntaje con penalización por reintento.
    effective_score: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(5, 2), nullable=True
    )
    outcome: Mapped[AssessmentOutcome | None] = mapped_column(
        _enum(AssessmentOutcome), nullable=True
    )
    #: `[{topic_id, correct, total, pct}]` para el desglose por tema.
    per_topic_scores: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    #: Temas por debajo del 60 % en este intento; alimentan el repaso recomendado.
    weak_topic_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    #: Enfriamiento tras reprobar (4 h / 24 h / 48 h).
    cooldown_until: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    #: Enfriamiento anulado por completar el repaso recomendado.
    cooldown_waived_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    xp_awarded: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    gold_awarded: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    local_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(sa.String(120), nullable=False)

    question_attempts: Mapped[list[QuestionAttempt]] = relationship(
        back_populates="assessment_attempt", passive_deletes=True
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "assessment_id", "attempt_no"),
        sa.UniqueConstraint("user_id", "idempotency_key"),
        sa.Index(
            "ix_assessment_attempts_user_id_assessment_id", "user_id", "assessment_id"
        ),
        sa.CheckConstraint("attempt_no >= 1", name="attempt_no_positive"),
        sa.CheckConstraint(
            "question_count >= 0 AND correct_count >= 0 "
            "AND correct_count <= question_count",
            name="counts_coherent",
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 100)", name="score_range"
        ),
        sa.CheckConstraint(
            "effective_score IS NULL OR (effective_score >= 0 AND effective_score <= 100)",
            name="effective_score_range",
        ),
        sa.CheckConstraint(
            "xp_awarded >= 0 AND gold_awarded >= 0", name="rewards_non_negative"
        ),
    )


# ---------------------------------------------------------------------------
# Agregados de progreso y dominio por usuario
# ---------------------------------------------------------------------------


class UserPathProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Avance del usuario en una ruta: contadores, porcentaje y punto de reanudación.

    Sostiene el botón "Continuar" del panel principal. Una fila por (usuario, ruta),
    también para las Rutas del Reino, que comparten contenido entre muchos usuarios.
    """

    __tablename__ = "user_path_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    learning_path_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ProgressState] = mapped_column(
        _enum(ProgressState),
        nullable=False,
        server_default=ProgressState.NOT_STARTED.name,
    )
    modules_total: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    modules_completed: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    lessons_total: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    lessons_completed: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    completion_pct: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")
    )
    #: Dónde está el usuario: alimenta el botón "Continuar".
    current_module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("path_modules.id", ondelete="SET NULL"), nullable=True
    )
    current_lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDc, sa.ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "learning_path_id"),
        sa.Index(
            "ix_user_path_progress_user_id_last_activity_at",
            "user_id",
            "last_activity_at",
        ),
        sa.CheckConstraint(
            "modules_total >= 0 AND modules_completed >= 0 "
            "AND modules_completed <= modules_total",
            name="modules_coherent",
        ),
        sa.CheckConstraint(
            "lessons_total >= 0 AND lessons_completed >= 0 "
            "AND lessons_completed <= lessons_total",
            name="lessons_coherent",
        ),
        sa.CheckConstraint(
            "completion_pct >= 0 AND completion_pct <= 100", name="completion_pct_range"
        ),
    )


class UserModuleProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Avance y dominio del usuario en un módulo (`M_mod`).

    `mastery` = 0.70 × promedio ponderado de los temas + 0.30 × `E_mod`. El módulo se
    considera **dominado** con `M_mod ≥ 80` y la evaluación aprobada; el desbloqueo del
    siguiente módulo se apoya en `status`.
    """

    __tablename__ = "user_module_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("path_modules.id", ondelete="CASCADE"), nullable=False
    )
    #: Ruta desnormalizada: permite listar el avance de una ruta sin join con módulos.
    learning_path_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ModuleStatus] = mapped_column(
        _enum(ModuleStatus), nullable=False, server_default=ModuleStatus.LOCKED.name
    )
    lessons_total: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    lessons_completed: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    #: Promedio ponderado de `M_t` de los temas del módulo.
    mean_topic_mastery: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")
    )
    assessment_best_score: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(5, 2), nullable=True
    )
    #: `E_mod`: mejor puntaje ya penalizado por reintentos.
    assessment_best_effective: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(5, 2), nullable=True
    )
    assessment_attempts: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    assessment_passed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    mastery: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")
    )
    unlocked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    #: Todas las lecciones completadas y la evaluación aprobada.
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    #: `M_mod ≥ 80` con la evaluación aprobada.
    mastered_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "module_id"),
        sa.Index(
            "ix_user_module_progress_user_id_learning_path_id",
            "user_id",
            "learning_path_id",
        ),
        sa.CheckConstraint(
            "lessons_total >= 0 AND lessons_completed >= 0 "
            "AND lessons_completed <= lessons_total",
            name="lessons_coherent",
        ),
        sa.CheckConstraint(
            "mean_topic_mastery >= 0 AND mean_topic_mastery <= 100",
            name="mean_topic_mastery_range",
        ),
        sa.CheckConstraint("mastery >= 0 AND mastery <= 100", name="mastery_range"),
        sa.CheckConstraint(
            "assessment_best_score IS NULL "
            "OR (assessment_best_score >= 0 AND assessment_best_score <= 100)",
            name="best_score_range",
        ),
        sa.CheckConstraint(
            "assessment_best_effective IS NULL "
            "OR (assessment_best_effective >= 0 AND assessment_best_effective <= 100)",
            name="best_effective_range",
        ),
        sa.CheckConstraint("assessment_attempts >= 0", name="attempts_non_negative"),
    )


class UserLessonProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Avance del usuario en una lección; sostiene la regla antirrepetición A1.

    `completion_count` decide el multiplicador de recompensa de la siguiente
    finalización (1.0 / 0.2 / 0.0) y `last_block_position` permite reanudar donde
    se quedó.
    """

    __tablename__ = "user_lesson_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    #: Tema desnormalizado: la cobertura `C_t` se calcula sin recorrer las lecciones.
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("path_modules.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ProgressState] = mapped_column(
        _enum(ProgressState),
        nullable=False,
        server_default=ProgressState.NOT_STARTED.name,
    )
    #: Nº de finalizaciones: multiplicadores 1.0 / 0.2 / 0.0.
    completion_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    #: Posición del bloque donde quedó el usuario (reanudar).
    last_block_position: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    questions_total: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    questions_correct: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    accuracy_pct: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 2), nullable=True)
    active_seconds: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    #: Primera finalización: la única que paga la recompensa completa.
    first_completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    #: El repaso se contabiliza una sola vez por día local y lección.
    last_reviewed_on: Mapped[date | None] = mapped_column(sa.Date, nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("user_id", "lesson_id"),
        sa.Index("ix_user_lesson_progress_user_id_module_id", "user_id", "module_id"),
        sa.CheckConstraint("completion_count >= 0", name="completion_count_non_negative"),
        sa.CheckConstraint(
            "last_block_position >= 0", name="last_block_position_non_negative"
        ),
        sa.CheckConstraint(
            "questions_total >= 0 AND questions_correct >= 0 "
            "AND questions_correct <= questions_total",
            name="questions_coherent",
        ),
        sa.CheckConstraint(
            "accuracy_pct IS NULL OR (accuracy_pct >= 0 AND accuracy_pct <= 100)",
            name="accuracy_pct_range",
        ),
        sa.CheckConstraint("active_seconds >= 0", name="active_seconds_non_negative"),
    )


class UserTopicProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Dominio fino por tema (`P_t`, `C_t`, `M_t`) y detección de debilidad.

    `mastery_raw` es el dominio sin decaimiento; `mastery` es el valor vigente que
    materializa el job diario aplicando la curva de olvido. La debilidad (`is_weak`)
    dispara `WEAKNESS_DETECTED` con idempotencia de 24 h.
    """

    __tablename__ = "user_topic_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    #: Conocimiento desnormalizado: `M_area` se agrega sin recorrer la jerarquía.
    knowledge_area_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("knowledge_areas.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("path_modules.id", ondelete="CASCADE"), nullable=False
    )
    #: `P_t × 100`, con prior bayesiano `m = 3`, `p0 = 0.5` (de ahí el 50.00 inicial).
    practice_score: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False, server_default=sa.text("50.00")
    )
    #: `C_t × 100` = lecciones completadas / lecciones del tema.
    coverage: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")
    )
    #: `P_t × g(C_t) × 100`, sin decaimiento.
    mastery_raw: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")
    )
    #: Dominio vigente, con decaimiento aplicado por el job diario.
    mastery: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")
    )
    evidence_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    #: Repasos exitosos posteriores al primer dominio: alarga la vida media.
    stability_s: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    #: Base temporal del decaimiento.
    last_evidence_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    ever_mastered_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    status: Mapped[KnowledgeAreaStatus] = mapped_column(
        _enum(KnowledgeAreaStatus),
        nullable=False,
        server_default=KnowledgeAreaStatus.NO_EVIDENCE.name,
    )
    #: `P_t < 50` con al menos 5 evidencias.
    is_weak: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    #: Última detección de debilidad (idempotencia de 24 h del evento).
    weak_detected_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    #: Regla que la detectó (`R1`…`R5`).
    weak_rule: Mapped[str | None] = mapped_column(sa.String(8), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("user_id", "topic_id"),
        sa.Index(
            "ix_user_topic_progress_user_id_knowledge_area_id",
            "user_id",
            "knowledge_area_id",
        ),
        sa.Index("ix_user_topic_progress_user_id_is_weak", "user_id", "is_weak"),
        sa.CheckConstraint(
            "practice_score >= 0 AND practice_score <= 100", name="practice_score_range"
        ),
        sa.CheckConstraint("coverage >= 0 AND coverage <= 100", name="coverage_range"),
        sa.CheckConstraint(
            "mastery_raw >= 0 AND mastery_raw <= 100", name="mastery_raw_range"
        ),
        sa.CheckConstraint("mastery >= 0 AND mastery <= 100", name="mastery_range"),
        sa.CheckConstraint(
            "evidence_count >= 0 AND stability_s >= 0", name="counters_non_negative"
        ),
    )


class UserAreaProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Perfil de conocimiento: nivel, XP, dominio y tiempo por conocimiento.

    Es la fila que pinta el territorio del mapa y la ficha "Competente en …". `xp` es un
    saldo **cacheado** desde `xp_transactions` filtrado por conocimiento y se reconcilia
    de noche; nunca se edita a mano.
    """

    __tablename__ = "user_area_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_area_id: Mapped[uuid.UUID] = mapped_column(
        UUIDc, sa.ForeignKey("knowledge_areas.id", ondelete="CASCADE"), nullable=False
    )
    #: Saldo cacheado del ledger filtrado por conocimiento.
    xp: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, server_default=sa.text("0")
    )
    #: Nivel por conocimiento (curva base 50), derivado de `xp`.
    level: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    #: Prefijo del título mostrado ("Competente en", "Novato/a en"…).
    rank_title: Mapped[str] = mapped_column(
        sa.String(48), nullable=False, server_default="Novato/a en"
    )
    #: `M_area × 100`.
    mastery: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")
    )
    study_seconds: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    modules_total: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    modules_mastered: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    topics_mastered: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    paths_completed: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    status: Mapped[KnowledgeAreaStatus] = mapped_column(
        _enum(KnowledgeAreaStatus),
        nullable=False,
        server_default=KnowledgeAreaStatus.NO_EVIDENCE.name,
    )
    #: Declarado dominado: `M_area ≥ 80 %` y al menos una ruta completa.
    mastered_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "knowledge_area_id"),
        sa.Index("ix_user_area_progress_user_id_status", "user_id", "status"),
        sa.CheckConstraint("xp >= 0", name="xp_non_negative"),
        sa.CheckConstraint("level >= 1 AND level <= 99", name="level_range"),
        sa.CheckConstraint("mastery >= 0 AND mastery <= 100", name="mastery_range"),
        sa.CheckConstraint("study_seconds >= 0", name="study_seconds_non_negative"),
        sa.CheckConstraint(
            "modules_total >= 0 AND modules_mastered >= 0 "
            "AND modules_mastered <= modules_total",
            name="modules_coherent",
        ),
        sa.CheckConstraint(
            "topics_mastered >= 0 AND paths_completed >= 0",
            name="counters_non_negative",
        ),
    )


__all__ = [
    "AssessmentAttempt",
    "LearningSession",
    "QuestionAttempt",
    "StudyActivity",
    "UserAreaProgress",
    "UserLessonProgress",
    "UserModuleProgress",
    "UserPathProgress",
    "UserTopicProgress",
]
