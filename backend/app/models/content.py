"""Modelos del módulo `content`: taxonomía de conocimientos y contenido educativo.

Este archivo implementa el catálogo de tablas del CONTRACT.md §3.2. Todo lo que
vive aquí es **contenido reutilizable**: no guarda ninguna columna de progreso,
XP, oro ni dominio de un usuario concreto. Las «Rutas del Reino»
(`learning_paths.user_id IS NULL`) son estudiadas por muchas personas sin
duplicar una sola fila de contenido; lo que hizo cada usuario vive en
`app/models/progress.py`.

Jerarquía normativa (CONTRACT.md §1.1)::

    Conocimiento (knowledge_areas)   = territorio del mapa
      └── Ruta (learning_paths)
            └── Módulo (path_modules)  = zona, termina en una Evaluación
                  └── Tema (topics)    = unidad de dominio fino
                        └── Lección (lessons)
                              └── Bloques (lesson_blocks) y Preguntas (questions)

Reglas de construcción respetadas en todo el archivo:

- Claves foráneas **siempre por texto** (`ForeignKey("users.id", ...)`). Este
  archivo no importa ningún otro módulo de `app/models/` salvo `enums`; las
  referencias a `users`, `knowledge_bases` y `generation_jobs` las resuelve
  Alembic al construir el esquema completo.
- `relationship()` **solo entre clases de este mismo archivo** (regla
  anti-conflicto del contrato §1.4.8).
- Enums con la receta canónica `sa.Enum(X, native_enum=False, length=48,
  validate_strings=True)`: la columna es un `VARCHAR(48)` y lo que se persiste
  es el **nombre del miembro en MAYÚSCULAS**, por eso todo `server_default` usa
  `Miembro.name` y todo `CheckConstraint` compara contra el nombre.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Final

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    ContentStatus,
    CoverageLevel,
    CoveragePolicy,
    DeclaredLevel,
    DifficultyLevel,
    KnowledgeCategory,
    LessonBlockType,
    PathOrigin,
    PathSourceMode,
    PathStatus,
    ProvenanceOrigin,
    QuestionType,
)

# Catálogo cerrado de motivos de reporte de contenido, compartido por
# `lesson_blocks.flag_reason` y `questions.flag_reason` (CONTRACT.md §3.2).
# El contrato define ambas columnas como `sa.String(32)` sin enum ni CHECK:
# la validación es responsabilidad de los esquemas Pydantic del módulo.
FLAG_REASONS: Final[frozenset[str]] = frozenset(
    {
        "incorrect",
        "ambiguous",
        "not_in_material",
        "poorly_written",
        "too_easy",
        "too_hard",
        "other",
    }
)


class KnowledgeArea(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Conocimiento de nivel superior (SQL, BigQuery…).

    Es la unidad que tiene nivel, XP, dominio y tiempo **propios** para cada
    usuario (esos contadores viven en `user_area_progress`) y la que se dibuja
    en el mapa como territorio. La taxonomía semilla curada por el equipo lleva
    `is_canonical = true`; un área creada al vuelo por un usuario guarda su
    autor en `created_by_user_id`.
    """

    __tablename__ = "knowledge_areas"

    slug: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    """Identificador canónico estable y legible (`sql`, `bigquery`)."""

    name: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    short_name: Mapped[str] = mapped_column(sa.String(18), nullable=False)
    """Nombre corto para las plantillas de ítems derivados ("Grimorio de {short_name}")."""

    category: Mapped[KnowledgeCategory] = mapped_column(
        sa.Enum(KnowledgeCategory, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=KnowledgeCategory.OTHER,
        server_default=KnowledgeCategory.OTHER.name,
    )
    """Categoría del conocimiento; tinta los ítems derivados por plantilla."""

    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    is_canonical: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    """`true` para la taxonomía semilla curada por el equipo."""

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Usuario que originó el área (nulo en la taxonomía canónica)."""

    icon_key: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    accent_color: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    """Color de la categoría en formato `#RRGGBB`."""

    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    """Permite retirar un conocimiento sin borrarlo ni romper el historial."""

    __table_args__ = (
        sa.UniqueConstraint("slug", name="uq_knowledge_areas_slug"),
        sa.Index("ix_knowledge_areas_category", "category"),
        sa.Index("ix_knowledge_areas_created_by_user_id", "created_by_user_id"),
    )

    territory: Mapped[Territory | None] = relationship(
        back_populates="knowledge_area",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    learning_paths: Mapped[list[LearningPath]] = relationship(
        back_populates="knowledge_area",
    )


class Territory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Representación narrativa de un conocimiento en el mapa (1:1 con el área).

    El nombre y el texto de sabor los genera la IA una sola vez y se cachean
    aquí. El **estado** del territorio (con niebla, descubierto, completado) no
    vive en esta tabla: se deriva del progreso del usuario.
    """

    __tablename__ = "territories"

    knowledge_area_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("knowledge_areas.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    """Nombre narrativo ("Castillo de las Consultas")."""

    icon_hint: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    """Pista visual devuelta por la IA (`castle`, `forest`)."""

    concept_keyword: Mapped[str | None] = mapped_column(sa.String(48), nullable=True)
    """Palabra clave que valida que el nombre narrativo sigue hablando del concepto."""

    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    generated_by_job_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("generation_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Trabajo de IA (`TERRITORY_NAMING`) que lo bautizó."""

    __table_args__ = (
        sa.UniqueConstraint("knowledge_area_id", name="uq_territories_knowledge_area_id"),
    )

    knowledge_area: Mapped[KnowledgeArea] = relationship(back_populates="territory")


class LearningPath(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ruta de aprendizaje: secuencia ordenada de módulos para un objetivo concreto.

    Con `user_id` nulo la ruta es una **Ruta del Reino**: catálogo semilla
    compartido y curado por el equipo, estudiado por muchos usuarios sin
    duplicar contenido. `status` describe el ciclo de vida del *contenido*
    (borrador, generando, activa…), nunca el avance de una persona.
    """

    __tablename__ = "learning_paths"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    """Dueño de la ruta. **Nulo = Ruta del Reino** (catálogo compartido)."""

    knowledge_area_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("knowledge_areas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(sa.String(120), nullable=False)

    goal_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    """Objetivo tal como lo escribió el usuario; entra al prompt de la Fase A."""

    summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    declared_level: Mapped[DeclaredLevel] = mapped_column(
        sa.Enum(DeclaredLevel, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=DeclaredLevel.BEGINNER,
        server_default=DeclaredLevel.BEGINNER.name,
    )
    source_mode: Mapped[PathSourceMode] = mapped_column(
        sa.Enum(PathSourceMode, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=PathSourceMode.WITH_SOURCE,
        server_default=PathSourceMode.WITH_SOURCE.name,
    )
    """Respaldo documental: `con_fuente`, `sin_fuente` o `mixta`."""

    origin: Mapped[PathOrigin] = mapped_column(
        sa.Enum(PathOrigin, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=PathOrigin.USER,
        server_default=PathOrigin.USER.name,
    )
    status: Mapped[PathStatus] = mapped_column(
        sa.Enum(PathStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=PathStatus.DRAFT,
        server_default=PathStatus.DRAFT.name,
    )
    language: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, default="es", server_default="es"
    )

    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Corpus de material asociado (tabla del módulo `ingestion`)."""

    coverage_policy: Mapped[CoveragePolicy] = mapped_column(
        sa.Enum(CoveragePolicy, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=CoveragePolicy.MODEL_KNOWLEDGE,
        server_default=CoveragePolicy.MODEL_KNOWLEDGE.name,
    )
    """Qué hacer con los temas sin respaldo suficiente en el material."""

    coverage_notes: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    """Avisos de cobertura devueltos por la Fase A del diseño de ruta."""

    module_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    """Número de módulos (cacheado; se recalcula al confirmar la ruta)."""

    estimated_minutes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    is_public: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    """Visible para todos; solo tiene sentido en rutas semilla."""

    generated_by_job_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("generation_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Trabajo de diseño de ruta (Fase A) que produjo el esquema."""

    confirmed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    """Momento en que el usuario confirmó el esquema propuesto."""

    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        sa.Index("ix_learning_paths_user_id_status", "user_id", "status"),
        sa.Index("ix_learning_paths_knowledge_area_id", "knowledge_area_id"),
        sa.Index("ix_learning_paths_origin_is_public", "origin", "is_public"),
        # Los enums se persisten por el NOMBRE del miembro (§1.4 regla 6):
        # una Ruta del Reino nunca puede tener dueño.
        sa.CheckConstraint(
            "(origin <> 'SEED') OR (user_id IS NULL)",
            name="seed_has_no_owner",
        ),
    )

    knowledge_area: Mapped[KnowledgeArea] = relationship(back_populates="learning_paths")
    modules: Mapped[list[PathModule]] = relationship(
        back_populates="learning_path",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PathModule.position",
    )


class PathModule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Módulo de una ruta: la «zona» del territorio. Siempre cierra con una evaluación.

    Es la unidad de generación perezosa: su contenido (temas, lecciones,
    preguntas y banco de evaluación) se produce cuando el usuario se acerca a
    él, y `content_status` refleja en qué punto de ese proceso está.
    """

    __tablename__ = "path_modules"

    learning_path_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    """Orden 1..n dentro de la ruta."""

    title: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    flavor_name: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    """Nombre narrativo de la zona ("Puente de las Uniones")."""

    summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    difficulty: Mapped[DifficultyLevel] = mapped_column(
        sa.Enum(DifficultyLevel, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=DifficultyLevel.MEDIUM,
        server_default=DifficultyLevel.MEDIUM.name,
    )
    estimated_minutes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    content_status: Mapped[ContentStatus] = mapped_column(
        sa.Enum(ContentStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ContentStatus.PENDING,
        server_default=ContentStatus.PENDING.name,
    )
    """Estado de la generación perezosa del contenido del módulo."""

    prerequisite_module_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("path_modules.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Prerrequisito explícito. El MVP es lineal; se guarda para la fase 3."""

    topic_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    lesson_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    generated_by_job_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("generation_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "learning_path_id", "position", name="uq_path_modules_learning_path_id_position"
        ),
        sa.Index("ix_path_modules_learning_path_id", "learning_path_id"),
        sa.CheckConstraint("position >= 1", name="position_positive"),
    )

    learning_path: Mapped[LearningPath] = relationship(back_populates="modules")
    prerequisite_module: Mapped[PathModule | None] = relationship(
        remote_side="PathModule.id",
        foreign_keys="PathModule.prerequisite_module_id",
    )
    topics: Mapped[list[Topic]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Topic.position",
    )
    assessment: Mapped[Assessment | None] = relationship(
        back_populates="module",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Topic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tema dentro de un módulo: la granularidad del dominio fino y del repaso.

    Cada pregunta pertenece a **exactamente un** tema, y el dominio (`M_t`) se
    calcula por tema. `source_chunk_ids` guarda la asignación gruesa de
    fragmentos hecha en el diseño de ruta; la traza fina vive en
    `content_provenance`.
    """

    __tablename__ = "topics"

    module_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("path_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    title: Mapped[str] = mapped_column(sa.String(140), nullable=False)

    learning_objectives: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    """Lista de objetivos de aprendizaje del tema."""

    coverage: Mapped[CoverageLevel] = mapped_column(
        sa.Enum(CoverageLevel, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=CoverageLevel.FULL,
        server_default=CoverageLevel.FULL.name,
    )
    """Cobertura del material del usuario para este tema."""

    difficulty: Mapped[DifficultyLevel] = mapped_column(
        sa.Enum(DifficultyLevel, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=DifficultyLevel.MEDIUM,
        server_default=DifficultyLevel.MEDIUM.name,
    )
    estimated_minutes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    suggested_question_types: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    """Tipos de pregunta sugeridos por la Fase A para este tema."""

    source_chunk_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    """Fragmentos (`document_chunks.id`) asignados al tema en el diseño."""

    lesson_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    content_status: Mapped[ContentStatus] = mapped_column(
        sa.Enum(ContentStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ContentStatus.PENDING,
        server_default=ContentStatus.PENDING.name,
    )

    __table_args__ = (
        sa.UniqueConstraint("module_id", "position", name="uq_topics_module_id_position"),
        sa.Index("ix_topics_module_id", "module_id"),
    )

    module: Mapped[PathModule] = relationship(back_populates="topics")
    lessons: Mapped[list[Lesson]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Lesson.position",
    )
    questions: Mapped[list[Question]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="Question.topic_id",
    )


class Lesson(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Lección de 5–15 minutos: unidad mínima que otorga "lección completada".

    `estimated_seconds` es la base del tiempo mínimo plausible que usa la regla
    anti-abuso al validar una lección completada. `is_low_content` marca las
    lecciones con material insuficiente, que pagan la mitad de XP y oro.
    """

    __tablename__ = "lessons"

    topic_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    title: Mapped[str] = mapped_column(sa.String(140), nullable=False)
    summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    estimated_seconds: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=540, server_default=sa.text("540")
    )
    """Duración estimada (9 min por defecto); base del tiempo mínimo plausible."""

    content_status: Mapped[ContentStatus] = mapped_column(
        sa.Enum(ContentStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ContentStatus.PENDING,
        server_default=ContentStatus.PENDING.name,
    )
    origin: Mapped[ProvenanceOrigin] = mapped_column(
        sa.Enum(ProvenanceOrigin, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ProvenanceOrigin.SOURCE,
        server_default=ProvenanceOrigin.SOURCE.name,
    )
    """Si se apoya en el material del usuario o en el conocimiento del modelo."""

    is_low_content: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    """Material insuficiente: paga 50 % de XP y oro (regla anti-abuso A8)."""

    coverage_report: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    """`[{objective, status}]`: cobertura conseguida por objetivo."""

    block_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    question_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    content_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1")
    )
    """Sube con cada regeneración; el progreso anterior del usuario se conserva."""

    generated_by_job_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("generation_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        sa.UniqueConstraint("topic_id", "position", name="uq_lessons_topic_id_position"),
        sa.Index("ix_lessons_topic_id", "topic_id"),
    )

    topic: Mapped[Topic] = relationship(back_populates="lessons")
    blocks: Mapped[list[LessonBlock]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LessonBlock.position",
    )
    inline_questions: Mapped[list[Question]] = relationship(
        back_populates="lesson",
        foreign_keys="Question.lesson_id",
    )
    """Preguntas intercaladas en esta lección (la FK es `SET NULL`, no borra)."""


class LessonBlock(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Bloque ordenado dentro de una lección (explicación, ejemplo, diagrama…).

    `body` admite Markdown restringido (sin HTML ni URLs) y `payload` lleva los
    extras propios del tipo: `{language}` en código, `{mermaid}` en diagrama y
    `{question_id}` en una pregunta intercalada.
    """

    __tablename__ = "lesson_blocks"

    lesson_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    block_type: Mapped[LessonBlockType] = mapped_column(
        sa.Enum(LessonBlockType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    body: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    origin: Mapped[ProvenanceOrigin] = mapped_column(
        sa.Enum(ProvenanceOrigin, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ProvenanceOrigin.SOURCE,
        server_default=ProvenanceOrigin.SOURCE.name,
    )
    is_flagged: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    """Reportado por el usuario o por la evaluación automática de calidad."""

    flag_reason: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    """Motivo del reporte; valores admitidos en `FLAG_REASONS`."""

    __table_args__ = (
        sa.UniqueConstraint(
            "lesson_id", "position", name="uq_lesson_blocks_lesson_id_position"
        ),
        sa.Index("ix_lesson_blocks_lesson_id", "lesson_id"),
    )

    lesson: Mapped[Lesson] = relationship(back_populates="blocks")


class Question(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Pregunta o ejercicio del pool de un tema.

    Es reutilizable: la misma fila sirve en la lección, en la práctica, en el
    repaso y en la evaluación del módulo. `answer_key` **jamás** se serializa al
    cliente; la corrección siempre ocurre en el servidor. Con
    `content_status = FLAGGED` la pregunta queda fuera del pool y del banco de
    evaluación.
    """

    __tablename__ = "questions"

    topic_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    """Tema al que está etiquetada la pregunta (exactamente uno)."""

    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("lessons.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Lección donde aparece intercalada, si aplica."""

    question_type: Mapped[QuestionType] = mapped_column(
        sa.Enum(QuestionType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        sa.Enum(DifficultyLevel, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=DifficultyLevel.EASY,
        server_default=DifficultyLevel.EASY.name,
    )
    """Peso de dominio 1.0 / 1.5 / 2.0 según sea EASY / MEDIUM / HARD."""

    stem: Mapped[str] = mapped_column(sa.Text, nullable=False)
    """Enunciado de la pregunta."""

    body: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    """Cuerpo según el tipo: opciones, huecos, parejas, rúbrica, `schema_sql`/`seed_data`."""

    answer_key: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    """Clave de corrección. **Nunca se serializa al cliente.**"""

    explanation: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    learning_objective: Mapped[str | None] = mapped_column(sa.String(240), nullable=True)

    estimated_seconds: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=45, server_default=sa.text("45")
    )
    origin: Mapped[ProvenanceOrigin] = mapped_column(
        sa.Enum(ProvenanceOrigin, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ProvenanceOrigin.SOURCE,
        server_default=ProvenanceOrigin.SOURCE.name,
    )
    is_remedial: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    """Generada como ejercicio dirigido tras detectar una debilidad."""

    content_status: Mapped[ContentStatus] = mapped_column(
        sa.Enum(ContentStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ContentStatus.READY,
        server_default=ContentStatus.READY.name,
    )
    is_flagged: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    flag_reason: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    """Motivo del reporte; mismo catálogo que `lesson_blocks.flag_reason`."""

    flag_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    """Reportes acumulados; al superar el umbral se retira la pregunta."""

    content_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1")
    )
    generated_by_job_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("generation_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        sa.Index("ix_questions_topic_id_question_type", "topic_id", "question_type"),
        sa.Index("ix_questions_lesson_id", "lesson_id"),
        sa.Index("ix_questions_content_status", "content_status"),
    )

    topic: Mapped[Topic] = relationship(
        back_populates="questions", foreign_keys=[topic_id]
    )
    lesson: Mapped[Lesson | None] = relationship(
        back_populates="inline_questions", foreign_keys=[lesson_id]
    )
    assessment_entries: Mapped[list[AssessmentQuestion]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Assessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Evaluación de cierre de módulo ("Prueba del Castillo"). Una por módulo.

    Define el contrato del examen (cuántas preguntas se muestran, umbral de
    aprobación, tope diario de intentos) y su banco vive en
    `assessment_questions`. Los intentos de cada usuario se guardan en
    `assessment_attempts`, del módulo `progress`.
    """

    __tablename__ = "assessments"

    module_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("path_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        sa.String(140),
        nullable=False,
        default="Prueba del módulo",
        server_default="Prueba del módulo",
    )
    """Nombre narrativo. Nunca usa la palabra "Desafío" (reservada a otra mecánica)."""

    question_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=10, server_default=sa.text("10")
    )
    """Preguntas que se presentan en cada intento."""

    pass_score: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2),
        nullable=False,
        default=Decimal("70.00"),
        server_default=sa.text("70.00"),
    )
    """Umbral de aprobación en porcentaje (escala 0.00–100.00)."""

    bank_size: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=25, server_default=sa.text("25")
    )
    """Tamaño objetivo del banco de preguntas (2,5× `question_count`)."""

    max_attempts_per_day: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=2, server_default=sa.text("2")
    )
    content_status: Mapped[ContentStatus] = mapped_column(
        sa.Enum(ContentStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ContentStatus.PENDING,
        server_default=ContentStatus.PENDING.name,
    )
    """Estado de generación del banco de preguntas."""

    __table_args__ = (sa.UniqueConstraint("module_id", name="uq_assessments_module_id"),)

    module: Mapped[PathModule] = relationship(back_populates="assessment")
    bank_entries: Mapped[list[AssessmentQuestion]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentQuestion.position",
    )


class AssessmentQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Entrada del banco de preguntas de una evaluación (N:M con `questions`).

    Permite retirar una pregunta reportada del examen (`is_active = false`) sin
    borrarla del pool del tema ni perder el historial de intentos.
    """

    __tablename__ = "assessment_questions"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    """Orden sugerido dentro del banco (el intento puede barajar)."""

    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    """`false` si la pregunta fue reportada y queda fuera del examen."""

    __table_args__ = (
        sa.UniqueConstraint(
            "assessment_id",
            "question_id",
            name="uq_assessment_questions_assessment_id_question_id",
        ),
        sa.Index("ix_assessment_questions_assessment_id", "assessment_id"),
    )

    assessment: Mapped[Assessment] = relationship(back_populates="bank_entries")
    question: Mapped[Question] = relationship(back_populates="assessment_entries")


__all__ = [
    "FLAG_REASONS",
    "Assessment",
    "AssessmentQuestion",
    "KnowledgeArea",
    "LearningPath",
    "Lesson",
    "LessonBlock",
    "PathModule",
    "Question",
    "Territory",
    "Topic",
]
