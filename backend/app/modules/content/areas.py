"""Conocimientos, territorios y mapa del mundo (§7.4).

Contrato §3.2 (`knowledge_areas`, `territories`), §3.4 (`user_area_progress`,
`user_module_progress`, `user_topic_progress`), §6.7 y §6.8.

**Explicabilidad obligatoria** (§6.7): el detalle de un conocimiento devuelve
`{practice_pct, assessment_pct, modules_mastered, modules_total, weak_topics}` para
que la app pueda decir «63 % porque aprobaste 5 de 8 módulos con 78 % promedio y
tienes 2 temas débiles». Los números salen de las tablas de progreso, nunca de una
estimación del cliente.

Qué conocimientos ve un usuario: la taxonomía canónica (`is_canonical`), los que él
mismo originó (`created_by_user_id`) y cualquiera en el que ya tenga progreso.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models.content import KnowledgeArea, LearningPath, PathModule, Territory, Topic
from app.models.enums import (
    KnowledgeAreaStatus,
    ModuleStatus,
    PathStatus,
    ProgressState,
    TerritoryStatus,
)
from app.models.progress import (
    UserAreaProgress,
    UserModuleProgress,
    UserPathProgress,
    UserTopicProgress,
)
from app.modules.progress import a_float


@dataclass(slots=True)
class TemaDebil:
    """Tema por debajo del umbral de práctica, con su dominio actual."""

    topic_id: uuid.UUID
    title: str
    mastery: float
    practice_score: float
    module_id: uuid.UUID


@dataclass(slots=True)
class FilaArea:
    """Un conocimiento con el progreso del usuario (o sin él)."""

    knowledge_area: KnowledgeArea
    xp: int = 0
    level: int = 1
    rank_title: str = ""
    mastery: float = 0.0
    study_seconds: int = 0
    status: KnowledgeAreaStatus = KnowledgeAreaStatus.NO_EVIDENCE
    paths_completed: int = 0
    modules_total: int = 0
    modules_mastered: int = 0
    topics_mastered: int = 0


@dataclass(slots=True)
class ExplicacionDominio:
    """Desglose que hace comprensible el porcentaje de dominio (§6.7)."""

    practice_pct: float
    assessment_pct: float
    modules_mastered: int
    modules_total: int
    weak_topics: list[TemaDebil] = field(default_factory=list)


@dataclass(slots=True)
class DetalleArea:
    """Detalle de un conocimiento: progreso, explicación y sus módulos."""

    fila: FilaArea
    territory: Territory | None
    explicacion: ExplicacionDominio
    modulos: list[tuple[PathModule, UserModuleProgress | None]] = field(default_factory=list)


@dataclass(slots=True)
class FilaTerritorio:
    """Un territorio del mapa con su estado narrativo (P22)."""

    territory: Territory
    knowledge_area: KnowledgeArea
    status: TerritoryStatus
    mastery: float
    zones_total: int
    zones_unlocked: int
    zones_completed: int


# ---------------------------------------------------------------------------
# Consultas de apoyo
# ---------------------------------------------------------------------------


def _progreso_por_area(db: Session, usuario_id: uuid.UUID) -> dict[uuid.UUID, UserAreaProgress]:
    """Mapa `{knowledge_area_id: UserAreaProgress}` del usuario."""
    filas = db.execute(
        sa.select(UserAreaProgress).where(UserAreaProgress.user_id == usuario_id)
    ).scalars()
    return {fila.knowledge_area_id: fila for fila in filas}


def _fila(area: KnowledgeArea, progreso: UserAreaProgress | None) -> FilaArea:
    """Combina el conocimiento con el progreso del usuario, si lo hay."""
    if progreso is None:
        return FilaArea(knowledge_area=area)
    return FilaArea(
        knowledge_area=area,
        xp=int(progreso.xp),
        level=int(progreso.level),
        rank_title=progreso.rank_title,
        mastery=a_float(progreso.mastery),
        study_seconds=int(progreso.study_seconds),
        status=progreso.status,
        paths_completed=int(progreso.paths_completed),
        modules_total=int(progreso.modules_total),
        modules_mastered=int(progreso.modules_mastered),
        topics_mastered=int(progreso.topics_mastered),
    )


def areas_visibles(db: Session, usuario_id: uuid.UUID) -> list[KnowledgeArea]:
    """Conocimientos que este usuario puede ver: canónicos, propios y con progreso."""
    con_progreso = sa.select(UserAreaProgress.knowledge_area_id).where(
        UserAreaProgress.user_id == usuario_id
    )
    return list(
        db.execute(
            sa.select(KnowledgeArea)
            .where(
                KnowledgeArea.is_active.is_(True),
                sa.or_(
                    KnowledgeArea.is_canonical.is_(True),
                    KnowledgeArea.created_by_user_id == usuario_id,
                    KnowledgeArea.id.in_(con_progreso),
                ),
            )
            .order_by(KnowledgeArea.name, KnowledgeArea.id)
        ).scalars()
    )


def listar_areas(db: Session, usuario_id: uuid.UUID) -> list[FilaArea]:
    """Catálogo de conocimientos con el dominio del usuario (§7.4)."""
    progreso = _progreso_por_area(db, usuario_id)
    return [_fila(area, progreso.get(area.id)) for area in areas_visibles(db, usuario_id)]


def obtener_area(db: Session, usuario_id: uuid.UUID, area_id: uuid.UUID) -> KnowledgeArea:
    """Carga un conocimiento visible para el usuario o lanza `404` (§8.7)."""
    area = db.get(KnowledgeArea, area_id)
    if area is None or not area.is_active:
        raise NotFound()
    if area.is_canonical or area.created_by_user_id == usuario_id:
        return area
    tiene_progreso = db.execute(
        sa.select(sa.literal(1))
        .select_from(UserAreaProgress)
        .where(
            UserAreaProgress.user_id == usuario_id,
            UserAreaProgress.knowledge_area_id == area_id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if tiene_progreso is None:
        raise NotFound()
    return area


def temas_debiles(
    db: Session, usuario_id: uuid.UUID, *, knowledge_area_id: uuid.UUID | None = None,
    module_id: uuid.UUID | None = None, limite: int = 10,
) -> list[TemaDebil]:
    """Temas marcados como débiles (`is_weak`, §6.8), los de menor dominio primero."""
    stmt = (
        sa.select(UserTopicProgress, Topic.title)
        .join(Topic, Topic.id == UserTopicProgress.topic_id)
        .where(UserTopicProgress.user_id == usuario_id, UserTopicProgress.is_weak.is_(True))
        .order_by(UserTopicProgress.mastery, UserTopicProgress.topic_id)
        .limit(limite)
    )
    if knowledge_area_id is not None:
        stmt = stmt.where(UserTopicProgress.knowledge_area_id == knowledge_area_id)
    if module_id is not None:
        stmt = stmt.where(UserTopicProgress.module_id == module_id)
    return [
        TemaDebil(
            topic_id=fila.topic_id,
            title=titulo,
            mastery=a_float(fila.mastery),
            practice_score=a_float(fila.practice_score),
            module_id=fila.module_id,
        )
        for fila, titulo in db.execute(stmt)
    ]


def explicar_dominio(
    db: Session, usuario_id: uuid.UUID, area_id: uuid.UUID
) -> ExplicacionDominio:
    """Desglose `{practice_pct, assessment_pct, modules_mastered, modules_total, weak_topics}`.

    `practice_pct` es el promedio de `mean_topic_mastery` de los módulos del área y
    `assessment_pct` el promedio de `assessment_best_effective` (`E_mod`, §6.6) de los
    módulos con evaluación rendida.
    """
    filas = list(
        db.execute(
            sa.select(UserModuleProgress)
            .join(PathModule, PathModule.id == UserModuleProgress.module_id)
            .join(LearningPath, LearningPath.id == PathModule.learning_path_id)
            .where(
                UserModuleProgress.user_id == usuario_id,
                LearningPath.knowledge_area_id == area_id,
                LearningPath.archived_at.is_(None),
            )
        ).scalars()
    )
    practicas = [a_float(f.mean_topic_mastery) for f in filas]
    evaluaciones = [
        a_float(f.assessment_best_effective) for f in filas if f.assessment_best_effective is not None
    ]
    return ExplicacionDominio(
        practice_pct=round(sum(practicas) / len(practicas), 2) if practicas else 0.0,
        assessment_pct=round(sum(evaluaciones) / len(evaluaciones), 2) if evaluaciones else 0.0,
        modules_mastered=len([f for f in filas if f.mastered_at is not None]),
        modules_total=len(filas),
        weak_topics=temas_debiles(db, usuario_id, knowledge_area_id=area_id),
    )


def detalle_area(db: Session, usuario_id: uuid.UUID, area_id: uuid.UUID) -> DetalleArea:
    """Detalle completo de un conocimiento (§7.4): nivel, XP, dominio explicado y módulos."""
    area = obtener_area(db, usuario_id, area_id)
    progreso = db.execute(
        sa.select(UserAreaProgress).where(
            UserAreaProgress.user_id == usuario_id,
            UserAreaProgress.knowledge_area_id == area_id,
        )
    ).scalar_one_or_none()
    territorio = db.execute(
        sa.select(Territory).where(Territory.knowledge_area_id == area_id)
    ).scalar_one_or_none()

    modulos = list(
        db.execute(
            sa.select(PathModule, UserModuleProgress)
            .join(LearningPath, LearningPath.id == PathModule.learning_path_id)
            .outerjoin(
                UserModuleProgress,
                sa.and_(
                    UserModuleProgress.module_id == PathModule.id,
                    UserModuleProgress.user_id == usuario_id,
                ),
            )
            .where(
                LearningPath.knowledge_area_id == area_id,
                LearningPath.archived_at.is_(None),
                sa.or_(LearningPath.user_id == usuario_id, LearningPath.user_id.is_(None)),
            )
            .order_by(LearningPath.created_at, PathModule.position)
        )
    )
    return DetalleArea(
        fila=_fila(area, progreso),
        territory=territorio,
        explicacion=explicar_dominio(db, usuario_id, area_id),
        modulos=[(modulo, avance) for modulo, avance in modulos],
    )


# ---------------------------------------------------------------------------
# Territorios (mapa del reino, P22)
# ---------------------------------------------------------------------------


def estado_territorio(
    *, mastery: float, zonas_desbloqueadas: int, rutas_completadas: int
) -> TerritoryStatus:
    """Estado visual del territorio (§2 `TerritoryStatus`).

    Con niebla mientras no hay nada desbloqueado; descubierto en cuanto el usuario
    puso un pie en él; completado cuando terminó al menos una ruta del conocimiento.
    """
    if rutas_completadas > 0:
        return TerritoryStatus.COMPLETED
    if zonas_desbloqueadas > 0 or mastery > 0:
        return TerritoryStatus.DISCOVERED
    return TerritoryStatus.FOGGED


def listar_territorios(db: Session, usuario_id: uuid.UUID) -> list[FilaTerritorio]:
    """Mapa simplificado: un territorio por conocimiento, con sus zonas (§7.4)."""
    areas = {area.id: area for area in areas_visibles(db, usuario_id)}
    if not areas:
        return []

    territorios = list(
        db.execute(
            sa.select(Territory).where(Territory.knowledge_area_id.in_(list(areas)))
        ).scalars()
    )
    progreso = _progreso_por_area(db, usuario_id)

    zonas = db.execute(
        sa.select(
            LearningPath.knowledge_area_id,
            sa.func.count(PathModule.id),
            sa.func.count(UserModuleProgress.unlocked_at),
            sa.func.count(UserModuleProgress.completed_at),
        )
        .select_from(PathModule)
        .join(LearningPath, LearningPath.id == PathModule.learning_path_id)
        .outerjoin(
            UserModuleProgress,
            sa.and_(
                UserModuleProgress.module_id == PathModule.id,
                UserModuleProgress.user_id == usuario_id,
            ),
        )
        .where(
            LearningPath.knowledge_area_id.in_(list(areas)),
            LearningPath.archived_at.is_(None),
            sa.or_(LearningPath.user_id == usuario_id, LearningPath.user_id.is_(None)),
        )
        .group_by(LearningPath.knowledge_area_id)
    ).all()
    por_area = {fila[0]: (int(fila[1]), int(fila[2]), int(fila[3])) for fila in zonas}

    rutas_completas = dict(
        db.execute(
            sa.select(LearningPath.knowledge_area_id, sa.func.count(UserPathProgress.id))
            .select_from(UserPathProgress)
            .join(LearningPath, LearningPath.id == UserPathProgress.learning_path_id)
            .where(
                UserPathProgress.user_id == usuario_id,
                UserPathProgress.status == ProgressState.COMPLETED,
            )
            .group_by(LearningPath.knowledge_area_id)
        ).all()
    )

    resultado: list[FilaTerritorio] = []
    for territorio in territorios:
        area = areas[territorio.knowledge_area_id]
        total, desbloqueadas, completadas = por_area.get(area.id, (0, 0, 0))
        avance = progreso.get(area.id)
        dominio = a_float(avance.mastery) if avance else 0.0
        resultado.append(
            FilaTerritorio(
                territory=territorio,
                knowledge_area=area,
                status=estado_territorio(
                    mastery=dominio,
                    zonas_desbloqueadas=desbloqueadas,
                    rutas_completadas=int(rutas_completas.get(area.id, 0)),
                ),
                mastery=dominio,
                zones_total=total,
                zones_unlocked=desbloqueadas,
                zones_completed=completadas,
            )
        )
    resultado.sort(key=lambda f: (f.knowledge_area.name, str(f.territory.id)))
    return resultado


def zonas_desbloqueadas(db: Session, usuario_id: uuid.UUID, area_id: uuid.UUID) -> list[PathModule]:
    """Módulos ya desbloqueados del conocimiento (las zonas visitables del territorio)."""
    return list(
        db.execute(
            sa.select(PathModule)
            .join(LearningPath, LearningPath.id == PathModule.learning_path_id)
            .join(
                UserModuleProgress,
                sa.and_(
                    UserModuleProgress.module_id == PathModule.id,
                    UserModuleProgress.user_id == usuario_id,
                ),
            )
            .where(
                LearningPath.knowledge_area_id == area_id,
                LearningPath.status != PathStatus.ARCHIVED,
                UserModuleProgress.status != ModuleStatus.LOCKED,
            )
            .order_by(PathModule.position)
        ).scalars()
    )


__all__ = [
    "DetalleArea",
    "ExplicacionDominio",
    "FilaArea",
    "FilaTerritorio",
    "TemaDebil",
    "areas_visibles",
    "detalle_area",
    "estado_territorio",
    "explicar_dominio",
    "listar_areas",
    "listar_territorios",
    "obtener_area",
    "temas_debiles",
    "zonas_desbloqueadas",
]
