"""Esquemas Pydantic v2 del módulo `ingestion` (§7.5, §8.2, §8.8).

Reglas aplicadas, idénticas a las del resto del backend:

- Un esquema de salida **jamás** hereda de un modelo SQLAlchemy: se construye con
  `model_config = ConfigDict(from_attributes=True)` desde el modelo o desde las
  dataclases del servicio.
- Los enums se serializan por su **valor** (`"pdf"`, `"ready"`, `"document_ingestion"`),
  no por el nombre en MAYÚSCULAS con el que viajan a la base (§1.4.6).
- Nada de lo que se expone identifica a otro usuario ni revela rutas del almacén:
  `document_versions.storage_key` **no** sale nunca al cliente.
- Paginación por cursor opaco: el sobre `page` es el de §8.2.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ChunkType, DocumentStatus, DocumentType, JobStatus, JobType


class EsquemaBase(BaseModel):
    """Base común: permite construir desde atributos de objetos del dominio."""

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Paginación (§8.2)
# ---------------------------------------------------------------------------


class PageOut(EsquemaBase):
    """Sobre de paginación por cursor opaco."""

    limit: int
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None


# ---------------------------------------------------------------------------
# Trabajos (`generation_jobs`)
# ---------------------------------------------------------------------------


class JobOut(EsquemaBase):
    """`JobOut` de §7.5: lo que la app consulta cada 2–3 s mientras espera.

    `error` es el mensaje de `generation_jobs.error_message`; nunca lleva traza ni SQL
    (§8.1), porque el worker solo guarda ahí el mensaje del catálogo de errores.
    """

    id: uuid.UUID
    job_type: JobType
    status: JobStatus
    queue: str
    progress_pct: float = 0.0
    progress_label: str | None = None
    error: str | None = None
    attempt_count: int = 0
    max_attempts: int = 3
    learning_path_id: uuid.UUID | None = None
    document_version_id: uuid.UUID | None = None
    created_at: dt.datetime | None = None
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None

    @field_validator("progress_pct", mode="before")
    @classmethod
    def _a_float(cls, valor: Any) -> float:
        """`Numeric(5, 2)` llega como `Decimal`; el contrato lo serializa como número."""
        return float(valor or 0)


# ---------------------------------------------------------------------------
# Documentos (`documents` + su versión vigente)
# ---------------------------------------------------------------------------


class DocumentVersionOut(EsquemaBase):
    """Versión vigente de un documento: estadísticas de procesamiento visibles.

    Deliberadamente **sin** `storage_key`: la clave del almacén es interna (§8.7).
    """

    id: uuid.UUID
    version_number: int
    status: DocumentStatus
    byte_size: int = 0
    page_count: int | None = None
    word_count: int | None = None
    token_count: int | None = None
    chunk_count: int = 0
    language: str | None = None
    error_message: str | None = None
    processed_at: dt.datetime | None = None
    created_at: dt.datetime | None = None


class DocumentOut(EsquemaBase):
    """`DocumentOut` de §7.5: ficha de material con su estado de procesamiento."""

    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    title: str
    document_type: DocumentType
    original_filename: str | None = None
    status: DocumentStatus
    version_count: int = 0
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None
    current_version: DocumentVersionOut | None = None


class DocumentCreatedOut(EsquemaBase):
    """Respuesta de `POST /documents` y `POST /documents/paste`: documento + trabajo.

    `duplicate` avisa a la app de que ese binario ya estaba subido (mismo
    `content_hash`) y no se volvió a procesar; `retry` de que la `Idempotency-Key` se
    repitió y la respuesta es la misma de antes (§8.3).
    """

    document: DocumentOut
    job: JobOut | None = None
    duplicate: bool = False
    retry: bool = False


class PageDocumentsOut(EsquemaBase):
    """`Page<DocumentOut>` de §7.5."""

    items: list[DocumentOut] = Field(default_factory=list)
    page: PageOut


# ---------------------------------------------------------------------------
# Entradas
# ---------------------------------------------------------------------------


class PasteTextIn(BaseModel):
    """Cuerpo de `POST /documents/paste`: `{title, text}`."""

    title: str = Field(min_length=1, max_length=255, description="Título visible del material.")
    text: str = Field(min_length=1, description="Texto pegado por la persona.")
    knowledge_base_id: uuid.UUID | None = Field(
        default=None, description="Biblioteca destino; por defecto la del usuario."
    )

    @field_validator("title")
    @classmethod
    def _titulo_no_vacio(cls, valor: str) -> str:
        """Un título de solo espacios no sirve para encontrar el material después."""
        limpio = valor.strip()
        if not limpio:
            raise ValueError("El título no puede estar vacío.")
        return limpio


# ---------------------------------------------------------------------------
# Fragmentos (`document_chunks`)
# ---------------------------------------------------------------------------


class ChunkOut(EsquemaBase):
    """`ChunkOut` de §7.5: fragmento original para la hoja «Fuente» de la app.

    Lleva el documento, las páginas y el texto; **no** lleva el embedding (512 números
    que la app no usa y que multiplicarían por diez el tamaño de la respuesta).
    """

    id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    document_title: str | None = None
    chunk_index: int
    chunk_type: ChunkType
    heading_path: list[str] = Field(default_factory=list)
    text: str
    token_count: int = 0
    page_start: int | None = None
    page_end: int | None = None
    language: str | None = None
    created_at: dt.datetime | None = None


# ---------------------------------------------------------------------------
# Estado de generación de una ruta (§7.5)
# ---------------------------------------------------------------------------


class GenerationStatusOut(EsquemaBase):
    """`GenerationStatusOut` `{status, stage, progress_pct, first_module_ready, eta_seconds, jobs[]}`."""

    status: JobStatus
    stage: str | None = None
    progress_pct: float = 0.0
    first_module_ready: bool = False
    eta_seconds: int | None = None
    jobs: list[JobOut] = Field(default_factory=list)


__all__ = [
    "ChunkOut",
    "DocumentCreatedOut",
    "DocumentOut",
    "DocumentVersionOut",
    "EsquemaBase",
    "GenerationStatusOut",
    "JobOut",
    "PageDocumentsOut",
    "PageOut",
    "PasteTextIn",
]
