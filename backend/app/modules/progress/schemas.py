"""Esquemas Pydantic v2 de las respuestas del módulo `progress`.

Contrato §7.4, §7.8 y §8.8: los esquemas de salida terminan en `Out`, se serializan
en `snake_case`, los enums viajan por su **valor** y `Numeric(5, 2)` sale como número
con dos decimales. Ningún esquema hereda de un modelo SQLAlchemy.

La forma de `DashboardOut`, `ProfileOut`, `StatsOut` y `UserKnowledgeOut` es
**literalmente** la de §7.8; los campos adicionales no existen.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type, datetime
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    DayStatus,
    GoalType,
    KnowledgeAreaStatus,
    MissionStatus,
    ModuleStatus,
    PathStatus,
    ProgressState,
    StreakChange,
)

T = TypeVar("T")


class SalidaBase(BaseModel):
    """Base de todas las respuestas: acepta objetos con atributos (dataclases y ORM)."""

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Sobre de paginación (§8.2)
# ---------------------------------------------------------------------------


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
# Panel principal (§7.8 · P04)
# ---------------------------------------------------------------------------


class DashboardCharacterOut(SalidaBase):
    """`character` del panel."""

    level: int
    rank_title: str
    xp_total: int
    xp_to_next: int
    progress_pct: float


class DashboardStreakOut(SalidaBase):
    """`streak` del panel: estado visible, sin mutar nada (§6.10)."""

    current: int
    best: int
    status: str
    day_status: DayStatus
    previous_length: int = 0
    last_change: StreakChange | None = None
    started_on: date_type | None = None


class DashboardDailyGoalOut(SalidaBase):
    """`daily_goal` del panel (§6.11)."""

    type: GoalType
    target: int
    progress: int
    met: bool
    bonus_gold: int


class DashboardContinueOut(SalidaBase):
    """`continue_action`: la tarjeta «continuar tu aventura»."""

    type: str
    path_id: uuid.UUID | None = None
    module_id: uuid.UUID | None = None
    lesson_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None
    title: str
    breadcrumb: str
    reward_preview: dict[str, int] = Field(default_factory=dict)


class DashboardKnowledgeOut(SalidaBase):
    """Una tarjeta de `knowledge_summary`: conocimiento con su dominio."""

    knowledge_area_id: uuid.UUID
    slug: str
    name: str
    short_name: str
    icon_key: str | None = None
    accent_color: str | None = None
    level: int
    rank_title: str
    mastery: float
    status: KnowledgeAreaStatus


class DashboardMissionOut(SalidaBase):
    """Una fila de `missions_summary`."""

    user_mission_id: uuid.UUID
    template_code: str
    title: str
    progress: int
    target: int
    status: MissionStatus
    reward_xp: int
    reward_gold: int


class DashboardWeekStatsOut(SalidaBase):
    """`week_stats`: los últimos siete días locales."""

    active_seconds: int
    lessons: int
    achievements: int


class DashboardGenerationBannerOut(SalidaBase):
    """`generation_banner`: hay una ruta preparándose (P06)."""

    path_id: uuid.UUID
    title: str
    status: PathStatus


class DashboardOut(SalidaBase):
    """`GET /api/v1/dashboard` — todo lo que P04 necesita en una sola llamada."""

    greeting_key: str
    character: DashboardCharacterOut
    gold_balance: int
    streak: DashboardStreakOut
    daily_goal: DashboardDailyGoalOut
    continue_action: DashboardContinueOut
    knowledge_summary: list[DashboardKnowledgeOut] = Field(default_factory=list)
    missions_summary: list[DashboardMissionOut] = Field(default_factory=list)
    week_stats: DashboardWeekStatsOut
    generation_banner: DashboardGenerationBannerOut | None = None
    unread_notifications: int = 0


# ---------------------------------------------------------------------------
# Perfil y estadísticas (§7.8 · P17)
# ---------------------------------------------------------------------------


class ProfileCharacterOut(SalidaBase):
    """Personaje tal como lo muestra el perfil."""

    name: str
    archetype: str
    level: int
    rank_title: str
    xp_total: int
    xp_to_next: int
    progress_pct: float
    total_study_seconds: int


class ProfileStatsOut(SalidaBase):
    """`stats` del perfil de videojuego."""

    xp_total: int
    streak_current: int
    study_seconds: int
    areas_mastered: int
    achievements_unlocked: int
    items_owned: int
    topics_mastered: int
    lessons_completed: int
    accuracy_pct: float


class UserKnowledgeOut(SalidaBase):
    """Una fila del perfil de conocimiento (`GET /api/v1/me/knowledge`)."""

    knowledge_area_id: uuid.UUID
    slug: str
    name: str
    short_name: str
    icon_key: str | None = None
    accent_color: str | None = None
    xp: int
    level: int
    rank_title: str
    mastery: float
    study_seconds: int
    modules_total: int
    modules_mastered: int
    topics_mastered: int
    paths_completed: int
    status: KnowledgeAreaStatus
    last_activity_at: datetime | None = None


class DayActivityOut(SalidaBase):
    """Un punto de la serie diaria de actividad."""

    local_date: date_type
    educational_xp: int
    active_seconds: int
    activities: int
    lessons: int
    questions_total: int
    questions_correct: int
    goal_met: bool
    day_status: DayStatus


class ProfileOut(SalidaBase):
    """`GET /api/v1/profile` (P17)."""

    character: ProfileCharacterOut
    avatar_layers: list[dict] = Field(default_factory=list)
    stats: ProfileStatsOut
    knowledge: list[UserKnowledgeOut] = Field(default_factory=list)
    last_7_days: list[DayActivityOut] = Field(default_factory=list)


class StatsTotalsOut(SalidaBase):
    """`totals` de `StatsOut`."""

    educational_xp: int
    active_seconds: int
    activities: int
    lessons: int
    questions_total: int
    questions_correct: int
    active_days: int
    goals_met: int


class StatsOut(SalidaBase):
    """`GET /api/v1/profile/stats` con rango de fechas."""

    daily: list[DayActivityOut] = Field(default_factory=list)
    totals: StatsTotalsOut
    accuracy_pct: float
    lessons: int
    assessments: int


# ---------------------------------------------------------------------------
# Mapa de la ruta (§7.5, lo consume `GET /paths/{path_id}`)
# ---------------------------------------------------------------------------


class LessonNodeOut(SalidaBase):
    """Una lección del mapa."""

    lesson_id: uuid.UUID
    title: str
    position: int
    estimated_seconds: int
    status: ProgressState
    completion_count: int
    accuracy_pct: float | None = None


class TopicNodeOut(SalidaBase):
    """Un tema del mapa, con su dominio."""

    topic_id: uuid.UUID
    title: str
    position: int
    mastery: float
    is_weak: bool
    lecciones: list[LessonNodeOut] = Field(default_factory=list)


class ModuleNodeOut(SalidaBase):
    """Una zona del territorio: un módulo con su bloqueo y su dominio."""

    module_id: uuid.UUID
    title: str
    flavor_name: str | None = None
    position: int
    status: ModuleStatus
    lessons_total: int
    lessons_completed: int
    mastery: float
    assessment_best_score: float | None = None
    assessment_passed: bool
    temas: list[TopicNodeOut] = Field(default_factory=list)


class PathMapOut(SalidaBase):
    """Estado del mapa de una ruta para el usuario (P07)."""

    learning_path_id: uuid.UUID
    title: str
    status: ProgressState
    modules_total: int
    modules_completed: int
    lessons_total: int
    lessons_completed: int
    completion_pct: float
    current_module_id: uuid.UUID | None = None
    current_lesson_id: uuid.UUID | None = None
    modulos: list[ModuleNodeOut] = Field(default_factory=list)


__all__ = [
    "DashboardCharacterOut",
    "DashboardContinueOut",
    "DashboardDailyGoalOut",
    "DashboardGenerationBannerOut",
    "DashboardKnowledgeOut",
    "DashboardMissionOut",
    "DashboardOut",
    "DashboardStreakOut",
    "DashboardWeekStatsOut",
    "DayActivityOut",
    "LessonNodeOut",
    "ModuleNodeOut",
    "Page",
    "PageMeta",
    "PathMapOut",
    "ProfileCharacterOut",
    "ProfileOut",
    "ProfileStatsOut",
    "StatsOut",
    "StatsTotalsOut",
    "TopicNodeOut",
    "UserKnowledgeOut",
]
