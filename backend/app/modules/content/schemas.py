"""Esquemas Pydantic v2 del módulo `content` (§7.4–§7.7, §8.2, §8.8).

Reglas aplicadas:

* Un esquema de salida nunca hereda de un modelo SQLAlchemy: se construye con
  `ConfigDict(from_attributes=True)` (§8.8).
* Los enums se serializan por su **valor** (`"multiple_choice"`, `"in_progress"`).
* **No existe ningún esquema que contenga `answer_key`.** Es una garantía
  estructural: aunque alguien pase un modelo completo, Pydantic no tiene dónde
  ponerlo (§8.7).
* Los `Numeric(5,2)` viajan como número con dos decimales.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ActivityContext,
    AssessmentOutcome,
    AttemptResult,
    ContentStatus,
    CoverageLevel,
    CoveragePolicy,
    DeclaredLevel,
    DifficultyLevel,
    EvaluationMethod,
    KnowledgeAreaStatus,
    KnowledgeCategory,
    LessonBlockType,
    ModuleStatus,
    PathOrigin,
    PathSourceMode,
    PathStatus,
    ProgressState,
    ProvenanceOrigin,
    QuestionType,
    TerritoryStatus,
)

T = TypeVar("T")


class EsquemaBase(BaseModel):
    """Base común de **salida**: construible desde atributos del dominio."""

    model_config = ConfigDict(from_attributes=True)


class EntradaBase(BaseModel):
    """Base de las **entradas**: rechaza campos no declarados.

    Sin esto, un nombre de campo equivocado no da error: Pydantic descarta la
    clave y la petición sigue como si nada. Fue justo lo que pasó con quitar un
    tema al confirmar una Ruta: el cliente mandaba `removed`, el esquema declara
    `remove`, y borrar un tema no hacía absolutamente nada en silencio.

    `identity` ya tenía esta guarda desde el principio; `content` no, y por eso
    el fallo se coló aquí y no allí.
    """

    model_config = ConfigDict(extra="forbid")


class PageMeta(BaseModel):
    """Metadatos de una página por cursor opaco (§8.2)."""

    limit: int
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None


class Page[T](BaseModel):
    """Sobre `{"items": [...], "page": {...}}` del contrato (§8.2)."""

    items: list[T]
    page: PageMeta


# ---------------------------------------------------------------------------
# §7.4 · Conocimientos y mundo
# ---------------------------------------------------------------------------


class WeakTopicOut(EsquemaBase):
    """Tema débil que explica parte del dominio (§6.7, §6.8)."""

    topic_id: uuid.UUID
    title: str
    mastery: float
    practice_score: float
    module_id: uuid.UUID


class KnowledgeAreaOut(EsquemaBase):
    """Conocimiento con el progreso del usuario (§7.4)."""

    knowledge_area_id: uuid.UUID
    slug: str
    name: str
    short_name: str
    category: KnowledgeCategory
    description: str | None = None
    icon_key: str | None = None
    accent_color: str | None = None
    is_canonical: bool = False
    xp: int = 0
    level: int = 1
    rank_title: str = ""
    mastery: float = 0.0
    study_seconds: int = 0
    status: KnowledgeAreaStatus = KnowledgeAreaStatus.NO_EVIDENCE


class MasteryExplanationOut(EsquemaBase):
    """Explicación obligatoria del porcentaje de dominio (§6.7)."""

    practice_pct: float
    assessment_pct: float
    modules_mastered: int
    modules_total: int
    weak_topics: list[WeakTopicOut] = Field(default_factory=list)


class AreaModuleOut(EsquemaBase):
    """Un módulo del conocimiento con el estado del usuario."""

    module_id: uuid.UUID
    title: str
    flavor_name: str | None = None
    position: int
    learning_path_id: uuid.UUID
    status: ModuleStatus = ModuleStatus.LOCKED
    mastery: float = 0.0
    lessons_total: int = 0
    lessons_completed: int = 0


class TerritoryBriefOut(EsquemaBase):
    """Territorio narrativo asociado al conocimiento."""

    territory_id: uuid.UUID
    name: str
    icon_hint: str | None = None
    description: str | None = None


class KnowledgeAreaDetailOut(EsquemaBase):
    """Detalle del conocimiento (§7.4)."""

    knowledge_area: KnowledgeAreaOut
    territory: TerritoryBriefOut | None = None
    explain: MasteryExplanationOut
    modules: list[AreaModuleOut] = Field(default_factory=list)
    weak_topics: list[WeakTopicOut] = Field(default_factory=list)


class TerritoryOut(EsquemaBase):
    """Territorio del mapa simplificado (§7.4 · P22)."""

    territory_id: uuid.UUID
    knowledge_area_id: uuid.UUID
    name: str
    knowledge_name: str
    icon_hint: str | None = None
    description: str | None = None
    status: TerritoryStatus
    mastery: float = 0.0
    zones_total: int = 0
    zones_unlocked: int = 0
    zones_completed: int = 0


# ---------------------------------------------------------------------------
# §7.5 · Rutas de aprendizaje
# ---------------------------------------------------------------------------


class PathSummaryOut(EsquemaBase):
    """Ruta en el listado (§7.5)."""

    path_id: uuid.UUID
    title: str
    summary: str | None = None
    goal_text: str | None = None
    knowledge_area_id: uuid.UUID
    knowledge_area_name: str | None = None
    origin: PathOrigin
    status: PathStatus
    source_mode: PathSourceMode
    declared_level: DeclaredLevel
    coverage_policy: CoveragePolicy
    module_count: int = 0
    estimated_minutes: int | None = None
    is_seed: bool = False
    is_adopted: bool = False
    completion_pct: float = 0.0
    modules_completed: int = 0
    lessons_completed: int = 0
    lessons_total: int = 0
    current_module_id: uuid.UUID | None = None
    current_lesson_id: uuid.UUID | None = None
    archived_at: datetime | None = None
    created_at: datetime | None = None


class PathCreateIn(EntradaBase):
    """Cuerpo de `POST /paths` (§7.5 · P05)."""

    goal_text: str = Field(min_length=1, max_length=2000)
    declared_level: DeclaredLevel = DeclaredLevel.BEGINNER
    source_mode: PathSourceMode = PathSourceMode.WITHOUT_SOURCE
    document_ids: list[uuid.UUID] = Field(default_factory=list)
    knowledge_area_id: uuid.UUID | None = None
    knowledge_area_hint: str | None = Field(default=None, max_length=80)
    knowledge_base_id: uuid.UUID | None = None
    coverage_policy: CoveragePolicy = CoveragePolicy.MODEL_KNOWLEDGE
    title: str | None = Field(default=None, max_length=120)


class PathUpdateIn(EntradaBase):
    """Cuerpo de `PATCH /paths/{id}`: renombrar o archivar (§7.5)."""

    title: str | None = Field(default=None, max_length=120)
    archived: bool | None = None


class TopicChangeIn(EntradaBase):
    """Una edición del esquema revisado en `POST /paths/{id}/confirm`."""

    topic_id: uuid.UUID
    title: str | None = Field(default=None, max_length=140)
    position: int | None = Field(default=None, ge=1)
    remove: bool = False


class PathConfirmIn(EntradaBase):
    """Cuerpo de `POST /paths/{id}/confirm` (§7.5)."""

    topics: list[TopicChangeIn] = Field(default_factory=list)
    coverage_policy: CoveragePolicy | None = None


class LessonNodeOut(EsquemaBase):
    """Lección dentro del mapa de la ruta.

    `content_status` viaja porque el cliente lo necesita para decidir si el nodo
    se puede abrir (P07 pinta «en construcción» y no navega mientras no esté
    `ready`). Faltaba, el cliente lo leía igual, y al no encontrarlo caía a
    `pending`: ninguna lección de ninguna ruta era abrible desde el mapa.
    """

    lesson_id: uuid.UUID
    title: str
    position: int
    estimated_seconds: int
    status: ProgressState
    content_status: ContentStatus
    completion_count: int = 0
    accuracy_pct: float | None = None


class TopicNodeOut(EsquemaBase):
    """Tema dentro del mapa de la ruta."""

    topic_id: uuid.UUID
    title: str
    position: int
    mastery: float = 0.0
    is_weak: bool = False
    # Con qué respalda este tema el material del aprendiz. Sin esto el cliente
    # lo lee nulo, cae a `full` y la etiqueta «Saber del Reino» no se pinta
    # nunca: el mapa afirma en silencio que los documentos cubren cada tema,
    # incluidos los que la Fase A marcó como sin respaldo suficiente.
    coverage: CoverageLevel = CoverageLevel.FULL
    lessons: list[LessonNodeOut] = Field(default_factory=list)


class ModuleAssessmentOut(EsquemaBase):
    """El desafío del módulo, tal y como lo pinta el mapa de la ruta (§7.5).

    Repite la ficha de `AssessmentBriefOut` —y no la hereda a propósito: esa
    vive en §7.7 y se sirve por módulo; esta viaja dentro de cada nodo de un
    mapa entero y tiene que poder cambiar sin arrastrar la pantalla de
    entrada— y le suma lo que depende del usuario: intentos gastados hoy,
    mejor puntaje, si ya aprobó y si puede empezar ahora.

    `can_start` responde solo a las reglas del desafío —enfriamiento y tope
    diario (§5.5, §8.6)—, **no** a si el módulo está desbloqueado: eso ya lo
    dice `status` del nodo, y mezclarlo dejaría el mapa sin poder distinguir
    «bloqueado» de «hoy ya no te quedan intentos».
    """

    assessment_id: uuid.UUID
    module_id: uuid.UUID
    title: str
    question_count: int
    pass_score: float
    max_attempts_per_day: int
    content_status: ContentStatus
    attempts_used: int = 0
    best_score: float | None = None
    passed: bool = False
    can_start: bool = False
    cooldown_until: datetime | None = None


class ModuleNodeOut(EsquemaBase):
    """Zona del territorio: un módulo con su bloqueo y su dominio."""

    module_id: uuid.UUID
    title: str
    flavor_name: str | None = None
    position: int
    status: ModuleStatus
    lessons_total: int = 0
    lessons_completed: int = 0
    mastery: float = 0.0
    # Sin esto el cliente no puede abrir el módulo: lo lee, no lo encuentra,
    # cae a `pending` y lo pinta «En construcción» aunque esté listo.
    content_status: ContentStatus = ContentStatus.READY
    summary: str | None = None
    estimated_minutes: int | None = None
    assessment_best_score: float | None = None
    assessment_passed: bool = False
    # El nodo del desafío. `None` cuando el módulo todavía no tiene evaluación
    # creada, que es lo que el mapa dibuja como «sin prueba».
    assessment: ModuleAssessmentOut | None = None
    topics: list[TopicNodeOut] = Field(default_factory=list)


class PathDetailOut(EsquemaBase):
    """Mapa de la ruta (§7.5 · P07)."""

    path: PathSummaryOut
    status: ProgressState
    modules_total: int = 0
    modules_completed: int = 0
    lessons_total: int = 0
    lessons_completed: int = 0
    completion_pct: float = 0.0
    current_module_id: uuid.UUID | None = None
    current_lesson_id: uuid.UUID | None = None
    # Los temas del objetivo que el material no cubre, tal y como los dejó la
    # Fase A. La pantalla de generación los lista debajo de la tarjeta que pide
    # decidir la política de cobertura: sin ellos, al aprendiz se le pide que
    # decida sobre unos temas que nadie le nombra.
    coverage_notes: list[str] = Field(default_factory=list)
    modules: list[ModuleNodeOut] = Field(default_factory=list)
    weak_topic_ids: list[uuid.UUID] = Field(default_factory=list)


class JobOut(EsquemaBase):
    """Trabajo de generación encolado (lo sirve `ingestion`, §7.5)."""

    id: uuid.UUID
    job_type: str
    status: str
    progress_pct: float = 0.0
    progress_label: str | None = None
    error: str | None = None


class PathCreatedOut(EsquemaBase):
    """Respuesta de `POST /paths` (§7.5)."""

    path: PathSummaryOut
    job: JobOut | None = None


# ---------------------------------------------------------------------------
# §7.6 · Lección, actividad y respuestas
# ---------------------------------------------------------------------------


class LessonBlockOut(EsquemaBase):
    """Bloque de una lección (§3.2)."""

    block_id: uuid.UUID
    position: int
    block_type: LessonBlockType
    body: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    origin: ProvenanceOrigin
    is_flagged: bool = False


class ProvenanceOut(EsquemaBase):
    """Traza de procedencia de un contenido (§3.3)."""

    chunk_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    document_version_id: uuid.UUID | None = None
    origin: ProvenanceOrigin
    retrieval_rank: int | None = None


class QuestionOut(EsquemaBase):
    """Pregunta tal como la ve el cliente. **Sin `answer_key` ni `explanation`.**"""

    question_id: uuid.UUID
    question_type: QuestionType
    difficulty: DifficultyLevel
    stem: str
    body: dict[str, Any] = Field(default_factory=dict)
    learning_objective: str | None = None
    estimated_seconds: int = 45
    topic_id: uuid.UUID
    position: int | None = None


class LessonOut(EsquemaBase):
    """Respuesta de `GET /lessons/{id}` (§7.6)."""

    lesson_id: uuid.UUID
    title: str
    summary: str | None = None
    position: int
    estimated_seconds: int
    content_status: ContentStatus
    origin: ProvenanceOrigin
    is_low_content: bool = False
    coverage_report: list[Any] = Field(default_factory=list)
    topic_id: uuid.UUID
    topic_title: str
    topic_coverage: CoverageLevel
    module_id: uuid.UUID
    learning_path_id: uuid.UUID
    knowledge_area_id: uuid.UUID
    status: ProgressState
    completion_count: int = 0
    blocks: list[LessonBlockOut] = Field(default_factory=list)
    provenance: list[ProvenanceOut] = Field(default_factory=list)
    questions_preview: list[QuestionOut] = Field(default_factory=list)


class ActivityOut(EsquemaBase):
    """Respuesta de `POST /lessons/{id}/start` y `POST /reviews/start` (§7.6)."""

    activity_id: uuid.UUID
    activity_type: str
    lesson_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None
    module_id: uuid.UUID | None = None
    learning_path_id: uuid.UUID | None = None
    knowledge_area_id: uuid.UUID | None = None
    started_at: datetime
    expires_at: datetime
    questions: list[QuestionOut] = Field(default_factory=list)


class AnswerIn(EntradaBase):
    """Cuerpo de `POST /activities/{id}/answers` (§7.6).

    El cliente informa **qué respondió**, nunca cuánto vale: ni XP, ni puntaje, ni
    corrección (§1.4 regla 11).
    """

    question_id: uuid.UUID
    response: dict[str, Any] = Field(default_factory=dict)
    response_ms: int = Field(default=0, ge=0, le=3_600_000)
    hint_used: bool = False


class AnswerResultOut(EsquemaBase):
    """Respuesta de `POST /activities/{id}/answers` (§7.6)."""

    attempt_id: uuid.UUID
    question_id: uuid.UUID
    result: AttemptResult
    is_correct: bool
    partial_score: float
    attempt_no: int
    xp_awarded: int = 0
    explanation: str | None = None
    correct_answer: Any | None = None
    provenance: list[ProvenanceOut] = Field(default_factory=list)
    evaluation_method: EvaluationMethod
    judge_confidence: float | None = None
    context: ActivityContext


class HeartbeatIn(EntradaBase):
    """Cuerpo de `POST /activities/{id}/heartbeat` (§7.6, ≤ 60 s)."""

    seconds: int = Field(ge=0, le=60)


class HeartbeatOut(EsquemaBase):
    """Tiempo efectivo acumulado tras el latido."""

    active_seconds: int
    credited_seconds: int = 0
    discarded: bool = False
    reason: str | None = None


class ReviewStartIn(EntradaBase):
    """Cuerpo de `POST /reviews/start` (§7.6)."""

    topic_id: uuid.UUID


class ReviewSuggestionOut(EsquemaBase):
    """Repaso recomendado (§7.6)."""

    topic_id: uuid.UUID
    title: str
    module_id: uuid.UUID
    knowledge_area_id: uuid.UUID
    mastery: float
    status: KnowledgeAreaStatus
    is_weak: bool
    question_count: int
    estimated_seconds: int


class ExplanationIn(EntradaBase):
    """Cuerpo de `POST /topics/{id}/explain` (§7.6)."""

    approach: str | None = Field(default=None, max_length=32)


class CitationOut(EsquemaBase):
    """Cita de la re-explicación."""

    chunk_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    quote: str | None = None


class ExplanationOut(EsquemaBase):
    """Respuesta de `POST /topics/{id}/explain` (§7.6)."""

    approach: str
    body: str
    citations: list[CitationOut] = Field(default_factory=list)


class ContentReportIn(EntradaBase):
    """Cuerpo de `POST /content/report` (§7.6)."""

    content_type: str = Field(pattern="^(block|question)$")
    content_id: uuid.UUID
    reason: str = Field(
        pattern="^(incorrect|ambiguous|not_in_material|poorly_written|too_easy|too_hard|other)$"
    )
    comment: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# §7.7 · Evaluación de módulo
# ---------------------------------------------------------------------------


class AssessmentBriefOut(EsquemaBase):
    """Ficha de la evaluación (§3.2)."""

    assessment_id: uuid.UUID
    module_id: uuid.UUID
    title: str
    question_count: int
    pass_score: float
    max_attempts_per_day: int
    content_status: ContentStatus


class AssessmentInfoOut(EsquemaBase):
    """Pantalla de entrada de la prueba (§7.7 · P11)."""

    assessment: AssessmentBriefOut
    module_title: str
    attempts_used: int
    attempts_total: int
    cooldown_until: datetime | None = None
    can_start: bool
    blocked_reason: str | None = None
    best_score: float | None = None
    best_effective: float | None = None
    passed_at: datetime | None = None
    reward_preview: dict[str, int] = Field(default_factory=dict)
    # Los temas del módulo, ordenados. Alimenta «Qué entra» en P11: sin esto,
    # `info.temas` llegaba siempre vacía y esa sección de la pantalla no se
    # pintaba nunca.
    topic_titles: list[str] = Field(default_factory=list)


class AssessmentAttemptOut(EsquemaBase):
    """Respuesta de `POST /assessments/{id}/start` (§7.7)."""

    attempt_id: uuid.UUID
    assessment_id: uuid.UUID
    module_id: uuid.UUID
    attempt_no: int
    question_count: int
    started_at: datetime
    questions: list[QuestionOut] = Field(default_factory=list)


class AssessmentAnswerIn(EntradaBase):
    """Cuerpo de `POST /assessment-attempts/{id}/answers` (§7.7)."""

    question_id: uuid.UUID
    response: dict[str, Any] = Field(default_factory=dict)
    response_ms: int = Field(default=0, ge=0, le=3_600_000)


class AssessmentAnswerOut(EsquemaBase):
    """Feedback mínimo: sin explicación mientras el examen está en curso (§7.7)."""

    recorded: bool
    index: int
    total: int
    is_correct: bool


class AssessmentReviewItemOut(EsquemaBase):
    """Una pregunta en la revisión posterior, ya con explicación y fuente."""

    question_id: uuid.UUID
    question_type: QuestionType
    difficulty: DifficultyLevel
    stem: str
    body: dict[str, Any] = Field(default_factory=dict)
    position: int | None = None
    topic_id: uuid.UUID
    explanation: str | None = None
    response: dict[str, Any] | None = None
    result: AttemptResult
    is_correct: bool
    partial_score: float = 0.0
    evaluation_method: EvaluationMethod | None = None
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class AssessmentReviewOut(EsquemaBase):
    """Respuesta de `GET /assessment-attempts/{id}` (§7.7)."""

    attempt_id: uuid.UUID
    assessment_id: uuid.UUID
    module_id: uuid.UUID
    attempt_no: int
    status: str
    score_pct: float | None = None
    effective_score_pct: float | None = None
    outcome: AssessmentOutcome | None = None
    correct_count: int = 0
    question_count: int = 0
    submitted_at: datetime | None = None
    cooldown_until: datetime | None = None
    per_topic: list[dict[str, Any]] = Field(default_factory=list)
    items: list[AssessmentReviewItemOut] = Field(default_factory=list)


__all__ = [
    "ActivityOut",
    "AnswerIn",
    "AnswerResultOut",
    "AreaModuleOut",
    "AssessmentAnswerIn",
    "AssessmentAnswerOut",
    "AssessmentAttemptOut",
    "AssessmentBriefOut",
    "AssessmentInfoOut",
    "AssessmentReviewItemOut",
    "AssessmentReviewOut",
    "CitationOut",
    "ContentReportIn",
    "EsquemaBase",
    "ExplanationIn",
    "ExplanationOut",
    "HeartbeatIn",
    "HeartbeatOut",
    "JobOut",
    "KnowledgeAreaDetailOut",
    "KnowledgeAreaOut",
    "LessonBlockOut",
    "LessonNodeOut",
    "LessonOut",
    "MasteryExplanationOut",
    "ModuleAssessmentOut",
    "ModuleNodeOut",
    "Page",
    "PageMeta",
    "PathConfirmIn",
    "PathCreateIn",
    "PathCreatedOut",
    "PathDetailOut",
    "PathSummaryOut",
    "PathUpdateIn",
    "ProvenanceOut",
    "QuestionOut",
    "ReviewStartIn",
    "ReviewSuggestionOut",
    "TerritoryBriefOut",
    "TerritoryOut",
    "TopicChangeIn",
    "TopicNodeOut",
    "WeakTopicOut",
]
