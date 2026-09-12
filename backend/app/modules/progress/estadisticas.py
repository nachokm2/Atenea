"""Perfil y estadísticas del usuario (P17) y las series que dibuja el cliente.

Contrato §7.8: `GET /api/v1/profile` y `GET /api/v1/profile/stats`.

Fuentes de verdad, sin recalcular nada que ya sea de otro módulo:

* **Días** — `streak_days`, el agregado diario que mantiene `gamification`. Es la
  única tabla que ya tiene, por fecha local, XP educativo, segundos efectivos,
  unidades de actividad, lecciones y aciertos. Aquí solo se **lee**.
* **Tiempo** — `study_activities.active_seconds` y `user_area_progress.study_seconds`.
* **Precisión** — `question_attempts`, contando solo lo que cuenta para dominio.
* **Dominio y conocimientos** — `user_area_progress` + `knowledge_areas`.

Todas las series se devuelven ya rellenas (los días sin actividad viajan en cero),
para que el cliente dibuje sus gráficos sin inventar huecos.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import user_local_date, utcnow
from app.models.content import KnowledgeArea
from app.models.economy import UserItem
from app.models.enums import AttemptStatus, DayStatus, KnowledgeAreaStatus, ProgressState
from app.models.gamification import StreakDay, UserAchievement
from app.models.identity import Character
from app.models.progress import (
    AssessmentAttempt,
    QuestionAttempt,
    StudyActivity,
    UserAreaProgress,
    UserLessonProgress,
    UserTopicProgress,
)
from app.modules.progress import a_float

DIAS_DE_LA_SEMANA = 7


@dataclass(slots=True)
class DiaDeActividad:
    """Un punto de la serie diaria: lo que el cliente dibuja en su gráfico."""

    local_date: date_type
    educational_xp: int
    active_seconds: int
    activities: int
    lessons: int
    questions_total: int
    questions_correct: int
    goal_met: bool
    day_status: DayStatus


@dataclass(slots=True)
class ConocimientoDelUsuario:
    """Una fila del perfil de conocimiento (§7.4 `GET /me/knowledge`)."""

    knowledge_area_id: uuid.UUID
    slug: str
    name: str
    short_name: str
    icon_key: str | None
    accent_color: str | None
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
    last_activity_at: datetime | None


@dataclass(slots=True)
class EstadisticasPerfil:
    """Bloque `stats` de `ProfileOut` (§7.8)."""

    xp_total: int
    streak_current: int
    study_seconds: int
    areas_mastered: int
    achievements_unlocked: int
    items_owned: int
    topics_mastered: int
    lessons_completed: int
    accuracy_pct: float


@dataclass(slots=True)
class TotalesRango:
    """Bloque `totals` de `StatsOut` (§7.8)."""

    educational_xp: int
    active_seconds: int
    activities: int
    lessons: int
    questions_total: int
    questions_correct: int
    active_days: int
    goals_met: int


@dataclass(slots=True)
class EstadisticasRango:
    """Respuesta completa de `GET /api/v1/profile/stats`."""

    desde: date_type
    hasta: date_type
    daily: list[DiaDeActividad] = field(default_factory=list)
    totals: TotalesRango = field(
        default_factory=lambda: TotalesRango(0, 0, 0, 0, 0, 0, 0, 0)
    )
    accuracy_pct: float = 0.0
    lessons: int = 0
    assessments: int = 0


class ServicioEstadisticas:
    """Perfil, series diarias y agregados del cliente."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- series diarias ---------------------------------------------------

    def serie_diaria(
        self, user_id: uuid.UUID, desde: date_type, hasta: date_type
    ) -> list[DiaDeActividad]:
        """Serie de actividad por fecha local, con los huecos rellenos en cero.

        Índice usado: `uq_streak_days_user_id_local_date`.
        """
        filas = {
            fila.local_date: fila
            for fila in self.db.execute(
                sa.select(StreakDay)
                .where(
                    StreakDay.user_id == user_id,
                    StreakDay.local_date >= desde,
                    StreakDay.local_date <= hasta,
                )
                .order_by(StreakDay.local_date)
            ).scalars()
        }
        serie: list[DiaDeActividad] = []
        dia = desde
        while dia <= hasta:
            fila = filas.get(dia)
            serie.append(
                DiaDeActividad(
                    local_date=dia,
                    educational_xp=int(fila.educational_xp) if fila else 0,
                    active_seconds=int(fila.effective_seconds) if fila else 0,
                    activities=int(fila.activities_completed) if fila else 0,
                    lessons=int(fila.lessons_completed) if fila else 0,
                    questions_total=int(fila.questions_total) if fila else 0,
                    questions_correct=int(fila.questions_correct) if fila else 0,
                    goal_met=bool(fila.goal_met_at) if fila else False,
                    day_status=fila.day_status if fila else DayStatus.INACTIVE,
                )
            )
            dia += timedelta(days=1)
        return serie

    def ultimos_dias(
        self, user_id: uuid.UUID, timezone_name: str, dias: int = DIAS_DE_LA_SEMANA
    ) -> list[DiaDeActividad]:
        """Los últimos N días locales del usuario (P17 muestra 7)."""
        hoy = user_local_date(utcnow(), timezone_name)
        return self.serie_diaria(user_id, hoy - timedelta(days=dias - 1), hoy)

    def resumen_semana(self, user_id: uuid.UUID, timezone_name: str) -> dict[str, int]:
        """`week_stats` del panel: tiempo, lecciones y logros de los últimos 7 días.

        Se resuelve con **una** consulta agregada sobre `streak_days` más otra sobre
        `user_achievements`.
        """
        hoy = user_local_date(utcnow(), timezone_name)
        desde = hoy - timedelta(days=DIAS_DE_LA_SEMANA - 1)
        segundos, lecciones, xp = self.db.execute(
            sa.select(
                sa.func.coalesce(sa.func.sum(StreakDay.effective_seconds), 0),
                sa.func.coalesce(sa.func.sum(StreakDay.lessons_completed), 0),
                sa.func.coalesce(sa.func.sum(StreakDay.educational_xp), 0),
            ).where(
                StreakDay.user_id == user_id,
                StreakDay.local_date >= desde,
                StreakDay.local_date <= hoy,
            )
        ).one()
        limite = utcnow() - timedelta(days=DIAS_DE_LA_SEMANA)
        logros = self.db.execute(
            sa.select(sa.func.count(UserAchievement.id)).where(
                UserAchievement.user_id == user_id,
                UserAchievement.last_unlocked_at.is_not(None),
                UserAchievement.last_unlocked_at >= limite,
            )
        ).scalar_one()
        return {
            "active_seconds": int(segundos),
            "lessons": int(lecciones),
            "achievements": int(logros),
            "educational_xp": int(xp),
        }

    # -- perfil -----------------------------------------------------------

    def estadisticas_perfil(
        self, user_id: uuid.UUID, *, streak_current: int = 0
    ) -> EstadisticasPerfil:
        """Bloque `stats` del perfil de videojuego (P17)."""
        xp_total, study_seconds = self.db.execute(
            sa.select(
                sa.func.coalesce(Character.xp_total, 0),
                sa.func.coalesce(Character.total_study_seconds, 0),
            ).where(Character.user_id == user_id)
        ).one_or_none() or (0, 0)

        areas_dominadas, temas_dominados = self.db.execute(
            sa.select(
                sa.func.count(UserAreaProgress.id).filter(
                    UserAreaProgress.status == KnowledgeAreaStatus.MASTERED
                ),
                sa.func.coalesce(sa.func.sum(UserAreaProgress.topics_mastered), 0),
            ).where(UserAreaProgress.user_id == user_id)
        ).one()

        logros = self.db.execute(
            sa.select(sa.func.count(UserAchievement.id)).where(
                UserAchievement.user_id == user_id,
                UserAchievement.first_unlocked_at.is_not(None),
            )
        ).scalar_one()

        objetos = self.db.execute(
            sa.select(sa.func.count(UserItem.id)).where(
                UserItem.user_id == user_id, UserItem.revoked_at.is_(None)
            )
        ).scalar_one()

        lecciones = self.db.execute(
            sa.select(sa.func.count(UserLessonProgress.id)).where(
                UserLessonProgress.user_id == user_id,
                UserLessonProgress.status == ProgressState.COMPLETED,
            )
        ).scalar_one()

        return EstadisticasPerfil(
            xp_total=int(xp_total or 0),
            streak_current=int(streak_current),
            study_seconds=int(study_seconds or 0),
            areas_mastered=int(areas_dominadas or 0),
            achievements_unlocked=int(logros),
            items_owned=int(objetos),
            topics_mastered=int(temas_dominados or 0),
            lessons_completed=int(lecciones),
            accuracy_pct=self.precision_global(user_id),
        )

    def conocimientos(self, user_id: uuid.UUID) -> list[ConocimientoDelUsuario]:
        """Perfil de conocimiento del usuario (`GET /api/v1/me/knowledge`).

        Índice usado: `ix_user_area_progress_user_id_status`.
        """
        filas = self.db.execute(
            sa.select(UserAreaProgress, KnowledgeArea)
            .join(KnowledgeArea, KnowledgeArea.id == UserAreaProgress.knowledge_area_id)
            .where(UserAreaProgress.user_id == user_id)
            .order_by(UserAreaProgress.mastery.desc(), KnowledgeArea.name)
        ).all()
        return [
            ConocimientoDelUsuario(
                knowledge_area_id=progreso.knowledge_area_id,
                slug=area.slug,
                name=area.name,
                short_name=area.short_name,
                icon_key=area.icon_key,
                accent_color=area.accent_color,
                xp=int(progreso.xp),
                level=int(progreso.level),
                rank_title=progreso.rank_title,
                mastery=a_float(progreso.mastery),
                study_seconds=int(progreso.study_seconds),
                modules_total=int(progreso.modules_total),
                modules_mastered=int(progreso.modules_mastered),
                topics_mastered=int(progreso.topics_mastered),
                paths_completed=int(progreso.paths_completed),
                status=progreso.status,
                last_activity_at=progreso.last_activity_at,
            )
            for progreso, area in filas
        ]

    # -- precisión y rangos ------------------------------------------------

    def precision_global(
        self,
        user_id: uuid.UUID,
        desde: date_type | None = None,
        hasta: date_type | None = None,
    ) -> float:
        """Precisión (%) sobre las respuestas que cuentan para dominio.

        Índice usado: `ix_question_attempts_user_id_local_date`.
        """
        stmt = sa.select(
            sa.func.count(QuestionAttempt.id),
            sa.func.count(QuestionAttempt.id).filter(QuestionAttempt.is_correct.is_(True)),
        ).where(
            QuestionAttempt.user_id == user_id,
            QuestionAttempt.counts_for_mastery.is_(True),
        )
        if desde is not None:
            stmt = stmt.where(QuestionAttempt.local_date >= desde)
        if hasta is not None:
            stmt = stmt.where(QuestionAttempt.local_date <= hasta)
        total, correctas = self.db.execute(stmt).one()
        if not total:
            return 0.0
        return round(100.0 * int(correctas) / int(total), 2)

    def estadisticas(
        self, user_id: uuid.UUID, desde: date_type, hasta: date_type
    ) -> EstadisticasRango:
        """`StatsOut`: serie diaria, totales, precisión, lecciones y evaluaciones."""
        serie = self.serie_diaria(user_id, desde, hasta)
        totales = TotalesRango(
            educational_xp=sum(d.educational_xp for d in serie),
            active_seconds=sum(d.active_seconds for d in serie),
            activities=sum(d.activities for d in serie),
            lessons=sum(d.lessons for d in serie),
            questions_total=sum(d.questions_total for d in serie),
            questions_correct=sum(d.questions_correct for d in serie),
            active_days=sum(1 for d in serie if d.day_status != DayStatus.INACTIVE),
            goals_met=sum(1 for d in serie if d.goal_met),
        )
        evaluaciones = self.db.execute(
            sa.select(sa.func.count(AssessmentAttempt.id)).where(
                AssessmentAttempt.user_id == user_id,
                AssessmentAttempt.status == AttemptStatus.SUBMITTED,
                AssessmentAttempt.local_date >= desde,
                AssessmentAttempt.local_date <= hasta,
            )
        ).scalar_one()
        return EstadisticasRango(
            desde=desde,
            hasta=hasta,
            daily=serie,
            totals=totales,
            accuracy_pct=self.precision_global(user_id, desde, hasta),
            lessons=totales.lessons,
            assessments=int(evaluaciones),
        )

    # -- apoyo -------------------------------------------------------------

    def horas_por_area(self, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Segundos de estudio por conocimiento, derivados de `study_activities`."""
        stmt = (
            sa.select(
                StudyActivity.knowledge_area_id,
                sa.func.coalesce(sa.func.sum(StudyActivity.active_seconds), 0),
            )
            .where(
                StudyActivity.user_id == user_id,
                StudyActivity.knowledge_area_id.is_not(None),
            )
            .group_by(StudyActivity.knowledge_area_id)
        )
        return {aid: int(total) for aid, total in self.db.execute(stmt)}

    def temas_debiles(self, user_id: uuid.UUID, limite: int = 10) -> list[UserTopicProgress]:
        """Temas marcados como débiles (`is_weak`), para repaso recomendado.

        Índice usado: `ix_user_topic_progress_user_id_is_weak`.
        """
        return list(
            self.db.execute(
                sa.select(UserTopicProgress)
                .where(
                    UserTopicProgress.user_id == user_id,
                    UserTopicProgress.is_weak.is_(True),
                )
                .order_by(UserTopicProgress.practice_score, UserTopicProgress.id)
                .limit(limite)
            ).scalars()
        )


__all__ = [
    "ConocimientoDelUsuario",
    "DiaDeActividad",
    "EstadisticasPerfil",
    "EstadisticasRango",
    "ServicioEstadisticas",
    "TotalesRango",
]
