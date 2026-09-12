"""Modelos de los módulos `ingestion` y `ai` de Atenea (CONTRACT.md §3.3).

Aquí vive todo el material documental del usuario y su rastro de procesamiento:

* `knowledge_bases` → corpus de material; una ruta de aprendizaje apunta a uno.
* `documents` → identidad lógica de un material ("Manual SQL.pdf").
* `document_versions` → versión inmutable de ese material (hash, binario, estadísticas).
* `document_chunks` → fragmento indexado con embedding y vector de búsqueda léxica.
* `generation_jobs` → cola y bitácora de todo trabajo de IA o de ingesta, con su coste.
* `prompt_templates` → versión de prompt registrada; toda generación referencia una.
* `content_provenance` → trazabilidad fina de cada pieza generada.

El módulo `ai` **no posee tablas propias**: escribe en `generation_jobs`,
`prompt_templates` y `content_provenance`, definidas en este archivo.

Reglas del contrato respetadas aquí:

* Claves foráneas **siempre por texto** (`ForeignKey("users.id", ...)`); este archivo
  nunca importa otro archivo de `app/models/` salvo `enums`.
* `relationship()` solo entre clases de este mismo archivo.
* `document_chunks` y `content_provenance` son **append-only**: solo `created_at`.
* Los índices HNSW (pgvector) y GIN (FTS) se crean a mano en la migración de Alembic
  con `op.execute(...)`, no con `sa.Index`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import func
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    ChunkType,
    DocumentStatus,
    DocumentType,
    JobMode,
    JobStatus,
    JobType,
    ProvenanceContentType,
    ProvenanceOrigin,
)

# Dimensión del espacio vectorial de los embeddings. Es el literal 512 —el mismo
# valor que `settings.embeddings_dim`— porque el DDL de una columna `vector(n)` se
# fija en la migración y no puede depender de una variable de entorno: cambiarlo
# obliga a una migración y a reindexar todos los fragmentos. Modelo: `voyage-3-lite`.
EMBEDDING_DIM = 512


class KnowledgeBase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Corpus de material de un usuario ("Material de SQL").

    Es la unidad de aislamiento del RAG: toda recuperación híbrida filtra por
    `knowledge_base_id` y por `user_id`. Una `learning_paths.knowledge_base_id`
    apunta aquí, de modo que la ruta solo ve el material que el usuario le dio.
    """

    __tablename__ = "knowledge_bases"

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # Contadores cacheados: se recalculan desde `documents` / `document_versions`.
    document_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    # Tokens del corpus completo; el tope por ruta (150 000) se valida en el servicio.
    total_tokens: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    # Biblioteca a la que van los materiales cuando el usuario no elige ninguna.
    is_default: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )

    documents: Mapped[list[Document]] = relationship(
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        sa.Index("ix_knowledge_bases_user_id", "user_id"),
        sa.CheckConstraint("document_count >= 0", name="document_count_non_negative"),
        sa.CheckConstraint("total_tokens >= 0", name="total_tokens_non_negative"),
    )


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Identidad lógica de un material subido, independiente de sus versiones.

    El usuario ve un solo "Manual SQL.pdf" aunque lo haya vuelto a subir tres veces:
    el contenido real vive en `document_versions`, y aquí queda el estado agregado.
    El borrado es lógico (`deleted_at`) con purga física diferida (`purge_after`).
    """

    __tablename__ = "documents"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Desnormalizado a propósito: **toda** consulta de material filtra por el dueño.
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        sa.Enum(DocumentType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    original_filename: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    # Estado agregado: resume el de la versión vigente de cara a la app.
    status: Mapped[DocumentStatus] = mapped_column(
        sa.Enum(DocumentStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=DocumentStatus.UPLOADED,
        server_default=DocumentStatus.UPLOADED.name,
    )
    version_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    # Borrado lógico inmediato: desaparece de la app pero el binario sigue disponible.
    deleted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    # Purga física diferida (30 días) que ejecuta el worker de mantenimiento.
    purge_after: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents")
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        sa.Index("ix_documents_user_id_status", "user_id", "status"),
        sa.Index("ix_documents_knowledge_base_id", "knowledge_base_id"),
        sa.CheckConstraint("version_count >= 0", name="version_count_non_negative"),
    )


class DocumentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Versión inmutable de un documento: binario, hash y estadísticas de ingesta.

    Es la unidad que el worker procesa (extraer → trocear → embeber) y la que citan
    los fragmentos y la trazabilidad. `content_hash` deduplica subidas idénticas y
    `is_current` marca la única versión vigente por documento (índice parcial único
    `uq_document_versions_current`, creado a mano en la migración).
    """

    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1")
    )
    # SHA-256 hexadecimal del binario: dos subidas iguales no se reprocesan.
    content_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    # Clave en el bucket de Railway o ruta local en desarrollo.
    storage_key: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    byte_size: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    page_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    # Mínimo 300 palabras para poder diseñar una ruta con respaldo documental.
    word_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    token_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    language: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        sa.Enum(DocumentStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=DocumentStatus.UPLOADED,
        server_default=DocumentStatus.UPLOADED.name,
    )
    # Solo una versión vigente por documento (lo garantiza el índice parcial único).
    is_current: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    document: Mapped[Document] = relationship(back_populates="versions")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        sa.UniqueConstraint("document_id", "version_number"),
        sa.UniqueConstraint("document_id", "content_hash"),
        sa.Index("ix_document_versions_document_id", "document_id"),
        sa.CheckConstraint("version_number >= 1", name="version_number_positive"),
        sa.CheckConstraint("byte_size >= 0", name="byte_size_non_negative"),
        sa.CheckConstraint("chunk_count >= 0", name="chunk_count_non_negative"),
    )


class DocumentChunk(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Fragmento indexado del material: texto, trazabilidad, embedding y FTS.

    Tabla **append-only** (solo `created_at`): reprocesar una versión borra sus
    fragmentos y los vuelve a insertar, nunca los actualiza. Es el sustrato de la
    recuperación híbrida (§6.12): coseno sobre `embedding` + `tsvector` español sobre
    `search_vector`, fusionados con RRF (k = 60).
    """

    __tablename__ = "document_chunks"

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Desnormalizados para poder filtrar la recuperación sin joins.
    document_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Aislamiento obligatorio: ninguna consulta de RAG puede omitir este filtro.
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    chunk_type: Mapped[ChunkType] = mapped_column(
        sa.Enum(ChunkType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ChunkType.PROSE,
        server_default=ChunkType.PROSE.name,
    )
    # Ruta de encabezados, p. ej. ["Capítulo 5. JOINs", "LEFT JOIN"].
    # Se antepone al texto antes de calcular el embedding.
    heading_path: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # Objetivo 450 tokens, máximo 800, mínimo 80 (se valida en el troceador).
    token_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    # Páginas y offsets: permiten mostrar "generado a partir de la página 42".
    page_start: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    char_start: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    # SHA-256 del texto normalizado: deduplica fragmentos repetidos.
    content_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    # Embedding `voyage-3-lite` de 512 dimensiones, distancia coseno.
    # Nulo mientras el fragmento espera su lote de embeddings.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
    # Modelo y dimensión efectiva: permiten reindexar por lotes al cambiar de modelo.
    embedding_model: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    # Columna generada y persistida por PostgreSQL: no se escribe desde Python.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        sa.Computed("to_tsvector('spanish', coalesce(text, ''))", persisted=True),
        nullable=True,
    )

    document_version: Mapped[DocumentVersion] = relationship(back_populates="chunks")

    __table_args__ = (
        sa.UniqueConstraint("document_version_id", "chunk_index"),
        sa.Index("ix_document_chunks_knowledge_base_id", "knowledge_base_id"),
        sa.Index("ix_document_chunks_user_id", "user_id"),
        sa.Index("ix_document_chunks_document_id", "document_id"),
        sa.CheckConstraint("chunk_index >= 0", name="chunk_index_non_negative"),
        sa.CheckConstraint("token_count >= 0", name="token_count_non_negative"),
        # Los índices HNSW y GIN se crean con op.execute(...) en la migración:
        #   CREATE INDEX ix_document_chunks_embedding_hnsw
        #     ON document_chunks USING hnsw (embedding vector_cosine_ops)
        #     WITH (m = 16, ef_construction = 128);
        #   CREATE INDEX ix_document_chunks_search_vector
        #     ON document_chunks USING gin (search_vector);
    )


class GenerationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Trabajo de IA o de ingesta: es a la vez cola de trabajo, bitácora y contador de coste.

    El worker toma filas en estado `PENDING` ordenadas por (`queue`, `priority`).
    `steps` guarda los pasos ya completados, de modo que un reintento reanuda en vez
    de repetir; `idempotency_key` impide encolar dos veces el mismo trabajo, y
    `progress_pct` / `progress_label` alimentan la pantalla de generación de la app.
    """

    __tablename__ = "generation_jobs"

    # Nulo en trabajos de sistema (mantenimiento, reindexado, semillas).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    job_type: Mapped[JobType] = mapped_column(
        sa.Enum(JobType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        sa.Enum(JobStatus, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=JobStatus.PENDING,
        server_default=JobStatus.PENDING.name,
    )
    # BATCH cuesta la mitad ante el proveedor, a cambio de latencia.
    mode: Mapped[JobMode] = mapped_column(
        sa.Enum(JobMode, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=JobMode.SYNC,
        server_default=JobMode.SYNC.name,
    )
    # Cola lógica: "ingest", "generate" u "housekeeping".
    queue: Mapped[str] = mapped_column(
        sa.String(24), nullable=False, default="generate", server_default="generate"
    )
    # Menor número = se atiende antes.
    priority: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=100, server_default=sa.text("100")
    )
    # Referencia polimórfica suelta (sin FK): "path", "module", "topic", "lesson",
    # "question", "assessment", "document", "answer".
    target_type: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True
    )
    # Ruta afectada: la app consulta por aquí el progreso de generación.
    learning_path_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("learning_paths.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("document_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    prompt_template_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("prompt_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, default="anthropic", server_default="anthropic"
    )
    # Modelo exacto devuelto por la API, no el alias pedido.
    model_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    # Lecturas de caché de prompt: se facturan aparte y mucho más barato.
    cached_input_tokens: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    output_tokens: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    # Costo en USD con 6 decimales; alimenta el presupuesto y AI_BUDGET_THRESHOLD.
    cost_usd: Mapped[Decimal] = mapped_column(
        sa.Numeric(10, 6),
        nullable=False,
        default=Decimal("0"),
        server_default=sa.text("0"),
    )
    attempt_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    max_attempts: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=3, server_default=sa.text("3")
    )
    # Pasos ya completados: hace el trabajo reanudable e idempotente.
    steps: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    # Progreso 0.00–100.00 mostrado en la pantalla de generación.
    progress_pct: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2),
        nullable=False,
        default=Decimal("0"),
        server_default=sa.text("0"),
    )
    progress_label: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    result: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    prompt_template: Mapped[PromptTemplate | None] = relationship(
        back_populates="jobs"
    )

    __table_args__ = (
        sa.UniqueConstraint("idempotency_key"),
        sa.Index("ix_generation_jobs_status_queue_priority", "status", "queue", "priority"),
        sa.Index("ix_generation_jobs_user_id_created_at", "user_id", "created_at"),
        sa.Index("ix_generation_jobs_learning_path_id", "learning_path_id"),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        sa.CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        sa.CheckConstraint("cost_usd >= 0", name="cost_usd_non_negative"),
        sa.CheckConstraint(
            "progress_pct >= 0 AND progress_pct <= 100", name="progress_pct_range"
        ),
    )


class PromptTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Versión registrada de un prompt del sistema.

    Los prompts no viven en el código: se siembran aquí en el despliegue y cada
    generación guarda cuál usó (`generation_jobs.prompt_template_id` y
    `content_provenance.prompt_template_id`). Así se puede auditar y reproducir
    exactamente qué instrucciones produjeron una lección o una pregunta.
    """

    __tablename__ = "prompt_templates"

    # Reutiliza JobType: la tarea que cubre el prompt es el tipo de trabajo.
    task_type: Mapped[JobType] = mapped_column(
        sa.Enum(JobType, native_enum=False, length=48, validate_strings=True),
        nullable=False,
    )
    # Versión semántica libre: "v3", "2026-09-10.1".
    version: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    # SHA-256 del cuerpo: detecta ediciones no versionadas.
    content_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    body: Mapped[str] = mapped_column(sa.Text, nullable=False)
    default_model: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    # Esfuerzo de razonamiento sugerido: "low", "medium", "high".
    effort: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    # Esquema JSON que se pasa como `output_config.format` al proveedor.
    output_schema: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # Solo una plantilla activa por `task_type` (regla aplicada en el servicio de IA).
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )

    jobs: Mapped[list[GenerationJob]] = relationship(back_populates="prompt_template")

    __table_args__ = (sa.UniqueConstraint("task_type", "version"),)


class ContentProvenance(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Trazabilidad fina de cada pieza de contenido generada por la IA.

    Responde a "¿de dónde salió esto?": qué fragmento del material, qué versión de
    documento, qué modelo, qué plantilla de prompt y qué trabajo la produjeron.
    Sustenta la etiqueta que ve el usuario ("generado a partir de tu material,
    página 42") y la distinción `SOURCE` frente a `MODEL_KNOWLEDGE`.

    Tabla **append-only** (solo `created_at`): una pieza regenerada añade filas nuevas.
    Se referencia el contenido de forma polimórfica (`content_type` + `content_id`),
    sin clave foránea, porque apunta a tablas de `content` que este archivo no importa.
    """

    __tablename__ = "content_provenance"

    content_type: Mapped[ProvenanceContentType] = mapped_column(
        sa.Enum(
            ProvenanceContentType, native_enum=False, length=48, validate_strings=True
        ),
        nullable=False,
    )
    # Id del elemento generado (lección, bloque, pregunta…). Sin FK: es polimórfico.
    content_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False
    )
    # Sub-elemento dentro del contenido: posición del bloque, clave de la pregunta…
    block_key: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    # Nulos si el fragmento fue purgado o si el origen es MODEL_KNOWLEDGE.
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("document_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Posición que ocupó el fragmento en la recuperación híbrida (1 = el mejor).
    retrieval_rank: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    origin: Mapped[ProvenanceOrigin] = mapped_column(
        sa.Enum(ProvenanceOrigin, native_enum=False, length=48, validate_strings=True),
        nullable=False,
        default=ProvenanceOrigin.SOURCE,
        server_default=ProvenanceOrigin.SOURCE.name,
    )
    generation_job_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("generation_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    prompt_template_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("prompt_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    # Fecha de procesamiento que se muestra al usuario junto a la cita.
    processed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.Index(
            "ix_content_provenance_content_type_content_id",
            "content_type",
            "content_id",
        ),
        sa.Index("ix_content_provenance_chunk_id", "chunk_id"),
        sa.Index("ix_content_provenance_document_id", "document_id"),
        sa.CheckConstraint("retrieval_rank >= 1", name="retrieval_rank_positive"),
    )


__all__ = [
    "EMBEDDING_DIM",
    "ContentProvenance",
    "Document",
    "DocumentChunk",
    "DocumentVersion",
    "GenerationJob",
    "KnowledgeBase",
    "PromptTemplate",
]
