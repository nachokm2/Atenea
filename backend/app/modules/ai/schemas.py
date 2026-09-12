"""Esquemas Pydantic v2 de la capa de IA (salidas `Out` que consumen las rutas de §7).

Aquí **no** viven los esquemas de lo que devuelve el modelo (eso es
`esquemas_salida.py`): esto es lo que la API expone al cliente. Reglas de §8.8: los
enums se serializan por su valor, los `Numeric(5,2)` como número con dos decimales y
ninguna respuesta incluye `answer_key` ni el cuerpo de una plantilla de prompt.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AttemptResult, EvaluationMethod


class EsquemaBase(BaseModel):
    """Base de los esquemas de salida de la capa de IA."""

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Procedencia y citas
# ---------------------------------------------------------------------------


class CitationOut(EsquemaBase):
    """Cita de un fragmento del material: sostiene la hoja «Fuente» de la app."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID | None = None
    document_title: str = ""
    page_start: int | None = None
    page_end: int | None = None


class ProvenanceOut(EsquemaBase):
    """Procedencia de una pieza generada (`content_provenance`)."""

    content_type: str
    content_id: uuid.UUID
    block_key: str | None = None
    origin: str
    chunk_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    document_title: str = ""
    page_start: int | None = None
    page_end: int | None = None
    model_id: str | None = None
    processed_at: Any | None = None


# ---------------------------------------------------------------------------
# Generación (Fase A y Fase B)
# ---------------------------------------------------------------------------


class PathDesignOut(EsquemaBase):
    """Resultado de la Fase A: el esquema de la ruta ya persistido."""

    path_id: uuid.UUID
    modules: int = 0
    topics: int = 0
    coverage_notes: list[str] = Field(default_factory=list)
    job_id: uuid.UUID | None = None
    from_cache: bool = False


class ModuleContentOut(EsquemaBase):
    """Resultado de la Fase B para un módulo."""

    module_id: uuid.UUID
    lessons: int = 0
    questions: int = 0
    from_cache: bool = False
    job_id: uuid.UUID | None = None
    notes: list[str] = Field(default_factory=list)


class MaterialReportOut(EsquemaBase):
    """Informe del material que respalda una ruta (detección de material insuficiente)."""

    words: int = 0
    tokens: int = 0
    chunks: int = 0
    min_words: int = 300
    is_enough: bool = False


# ---------------------------------------------------------------------------
# Corrección
# ---------------------------------------------------------------------------


class JudgeVerdictOut(EsquemaBase):
    """Veredicto del juez de respuestas abiertas, tal y como lo ve el cliente."""

    result: AttemptResult
    is_correct: bool
    partial_score: float = 0.0
    confidence: float = 0.0
    evaluation_method: EvaluationMethod
    feedback: str = ""
    missing: list[str] = Field(default_factory=list)
    escalated: bool = False


class SqlEvaluationOut(EsquemaBase):
    """Resultado de un ejercicio de SQL corregido en el sandbox de DuckDB."""

    is_correct: bool
    partial_score: float = 0.0
    message: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    elapsed_ms: int = 0
    error_code: str | None = None


# ---------------------------------------------------------------------------
# Adaptación
# ---------------------------------------------------------------------------


class WeaknessOut(EsquemaBase):
    """Debilidad detectada de forma determinista sobre las evidencias."""

    topic_id: uuid.UUID
    rule: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class AdaptiveDecisionOut(EsquemaBase):
    """Decisión adaptativa: repaso, re-explicación o nada."""

    topic_id: uuid.UUID
    action: str
    rule: str | None = None
    approach: str | None = None
    reason: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)


class ExplanationOut(EsquemaBase):
    """`ExplanationOut` de §7.6: explicación alternativa con citas."""

    approach: str
    body: str
    citations: list[CitationOut] = Field(default_factory=list)
    check_question: str = ""


# ---------------------------------------------------------------------------
# Coste
# ---------------------------------------------------------------------------


class AiUsageOut(EsquemaBase):
    """Contabilidad de tokens y coste de una generación (uso interno y de soporte)."""

    calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: str = "0"


class AiBudgetOut(EsquemaBase):
    """Estado del presupuesto global de IA del día."""

    spent_usd: str = "0"
    budget_usd: str = "0"
    remaining_usd: str = "0"
    exhausted: bool = False


class AiQuotaOut(EsquemaBase):
    """Estado de una cuota diaria de IA del usuario."""

    quota: str
    used: int = 0
    limit: int = 0
    remaining: int = 0
    resets_at: Any | None = None


__all__ = [
    "AdaptiveDecisionOut",
    "AiBudgetOut",
    "AiQuotaOut",
    "AiUsageOut",
    "CitationOut",
    "EsquemaBase",
    "ExplanationOut",
    "JudgeVerdictOut",
    "MaterialReportOut",
    "ModuleContentOut",
    "PathDesignOut",
    "ProvenanceOut",
    "SqlEvaluationOut",
    "WeaknessOut",
]
