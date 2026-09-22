"""Módulos: resolución del contexto de contenido y desbloqueo progresivo.

Contrato §3.2, §3.4 (`user_module_progress`), §6.9 regla A7, §7.5 y §7.7.

Este archivo es el **guardián de acceso** del contenido: antes de abrir una lección,
un repaso o una evaluación se comprueba aquí que

1. el contenido pertenece a una ruta visible para el usuario (si no, `404`, §8.7);
2. el módulo está desbloqueado (si no, `409 MODULE_LOCKED`);
3. el contenido terminó de generarse (si no, `409 CONTENT_NOT_READY`).

El desbloqueo en sí lo decide `app.modules.progress.progreso`: aquí solo se consulta
y se traduce a los errores del catálogo cerrado de §8.1.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import AteneaError, NotFound
from app.models.content import (
    Assessment,
    KnowledgeArea,
    LearningPath,
    Lesson,
    PathModule,
    Topic,
)
from app.models.enums import ContentStatus, ModuleStatus, PathOrigin
from app.models.progress import UserModuleProgress
from app.modules.progress.progreso import ServicioProgreso

#: Estados de contenido que ya se pueden estudiar (§2 `ContentStatus`).
ESTADOS_NAVEGABLES: frozenset[ContentStatus] = frozenset(
    {ContentStatus.READY, ContentStatus.NEEDS_ATTENTION}
)

#: Estados de módulo en los que el usuario puede entrar (§2 `ModuleStatus`).
ESTADOS_ABIERTOS: frozenset[ModuleStatus] = frozenset(
    {
        ModuleStatus.AVAILABLE,
        ModuleStatus.IN_PROGRESS,
        ModuleStatus.COMPLETED,
        ModuleStatus.MASTERED,
    }
)

#: Estados de módulo ya terminado (§7.6 desafío: solo se abre tras completarlo).
ESTADOS_COMPLETADOS: frozenset[ModuleStatus] = frozenset(
    {ModuleStatus.COMPLETED, ModuleStatus.MASTERED}
)


@dataclass(slots=True)
class ContextoContenido:
    """Cadena completa conocimiento → ruta → módulo → tema → lección."""

    lesson: Lesson | None
    topic: Topic | None
    module: PathModule
    path: LearningPath
    knowledge_area_id: uuid.UUID


def _ruta_visible(ruta: LearningPath, usuario_id: uuid.UUID) -> bool:
    """La ruta es del usuario o es una Ruta del Reino publicada (§5.9 D17)."""
    if ruta.user_id == usuario_id:
        return True
    return ruta.user_id is None and (ruta.is_public or ruta.origin == PathOrigin.SEED)


def contexto_de_leccion(
    db: Session, usuario_id: uuid.UUID, lesson_id: uuid.UUID
) -> ContextoContenido:
    """Resuelve la cadena de una lección y comprueba la visibilidad (§8.7)."""
    fila = db.execute(
        sa.select(Lesson, Topic, PathModule, LearningPath)
        .join(Topic, Topic.id == Lesson.topic_id)
        .join(PathModule, PathModule.id == Topic.module_id)
        .join(LearningPath, LearningPath.id == PathModule.learning_path_id)
        .where(Lesson.id == lesson_id)
    ).one_or_none()
    if fila is None:
        raise NotFound()
    leccion, tema, modulo, ruta = fila
    if not _ruta_visible(ruta, usuario_id):
        raise NotFound()
    return ContextoContenido(
        lesson=leccion,
        topic=tema,
        module=modulo,
        path=ruta,
        knowledge_area_id=ruta.knowledge_area_id,
    )


def contexto_de_tema(db: Session, usuario_id: uuid.UUID, topic_id: uuid.UUID) -> ContextoContenido:
    """Resuelve la cadena de un tema (repasos y re-explicaciones, §7.6)."""
    fila = db.execute(
        sa.select(Topic, PathModule, LearningPath)
        .join(PathModule, PathModule.id == Topic.module_id)
        .join(LearningPath, LearningPath.id == PathModule.learning_path_id)
        .where(Topic.id == topic_id)
    ).one_or_none()
    if fila is None:
        raise NotFound()
    tema, modulo, ruta = fila
    if not _ruta_visible(ruta, usuario_id):
        raise NotFound()
    return ContextoContenido(
        lesson=None,
        topic=tema,
        module=modulo,
        path=ruta,
        knowledge_area_id=ruta.knowledge_area_id,
    )


def contexto_de_modulo(
    db: Session, usuario_id: uuid.UUID, module_id: uuid.UUID
) -> ContextoContenido:
    """Resuelve la cadena de un módulo (evaluaciones, §7.7)."""
    fila = db.execute(
        sa.select(PathModule, LearningPath)
        .join(LearningPath, LearningPath.id == PathModule.learning_path_id)
        .where(PathModule.id == module_id)
    ).one_or_none()
    if fila is None:
        raise NotFound()
    modulo, ruta = fila
    if not _ruta_visible(ruta, usuario_id):
        raise NotFound()
    return ContextoContenido(
        lesson=None,
        topic=None,
        module=modulo,
        path=ruta,
        knowledge_area_id=ruta.knowledge_area_id,
    )


def contexto_de_evaluacion(
    db: Session, usuario_id: uuid.UUID, assessment_id: uuid.UUID
) -> tuple[Assessment, ContextoContenido]:
    """Resuelve la evaluación y el módulo al que cierra (§7.7)."""
    evaluacion = db.get(Assessment, assessment_id)
    if evaluacion is None:
        raise NotFound()
    return evaluacion, contexto_de_modulo(db, usuario_id, evaluacion.module_id)


def evaluacion_de_modulo(db: Session, module_id: uuid.UUID) -> Assessment:
    """Evaluación de cierre del módulo (una por módulo, §3.2)."""
    evaluacion = db.execute(
        sa.select(Assessment).where(Assessment.module_id == module_id)
    ).scalar_one_or_none()
    if evaluacion is None:
        raise NotFound()
    return evaluacion


# ---------------------------------------------------------------------------
# Guardas
# ---------------------------------------------------------------------------


def avance_de_modulo(
    db: Session, usuario_id: uuid.UUID, contexto: ContextoContenido
) -> UserModuleProgress:
    """Fila de `user_module_progress`, creándola con el desbloqueo inicial si falta."""
    fila = db.execute(
        sa.select(UserModuleProgress).where(
            UserModuleProgress.user_id == usuario_id,
            UserModuleProgress.module_id == contexto.module.id,
        )
    ).scalar_one_or_none()
    if fila is not None:
        return fila
    ServicioProgreso(db).asegurar_progreso_ruta(usuario_id, contexto.path.id)
    fila = db.execute(
        sa.select(UserModuleProgress).where(
            UserModuleProgress.user_id == usuario_id,
            UserModuleProgress.module_id == contexto.module.id,
        )
    ).scalar_one_or_none()
    if fila is None:  # pragma: no cover - solo si el módulo se borró entre medias
        raise NotFound()
    return fila


def asegurar_desbloqueado(
    db: Session, usuario_id: uuid.UUID, contexto: ContextoContenido
) -> UserModuleProgress:
    """Exige que el módulo esté desbloqueado; si no, `409 MODULE_LOCKED` (§8.1)."""
    fila = avance_de_modulo(db, usuario_id, contexto)
    if fila.status not in ESTADOS_ABIERTOS:
        raise AteneaError(
            code="MODULE_LOCKED",
            details={
                "module_id": str(contexto.module.id),
                "path_id": str(contexto.path.id),
                "status": fila.status.value,
            },
        )
    return fila


def asegurar_modulo_completado(
    db: Session, usuario_id: uuid.UUID, contexto: ContextoContenido
) -> UserModuleProgress:
    """Exige el módulo ya terminado; si no, `409 CHALLENGE_LOCKED` (§7.6 desafío)."""
    fila = asegurar_desbloqueado(db, usuario_id, contexto)
    if fila.status not in ESTADOS_COMPLETADOS:
        raise AteneaError(
            code="CHALLENGE_LOCKED",
            details={
                "module_id": str(contexto.module.id),
                "path_id": str(contexto.path.id),
                "status": fila.status.value,
            },
        )
    return fila


def asegurar_contenido_listo(estado: ContentStatus, *, target_id: uuid.UUID) -> None:
    """Exige contenido generado; si no, `409 CONTENT_NOT_READY` (§8.1)."""
    if estado not in ESTADOS_NAVEGABLES:
        raise AteneaError(
            code="CONTENT_NOT_READY",
            details={"target_id": str(target_id), "content_status": estado.value},
        )


def area_de_ruta(db: Session, path_id: uuid.UUID) -> KnowledgeArea | None:
    """Conocimiento principal de una ruta (dimensión de XP y dominio)."""
    return db.execute(
        sa.select(KnowledgeArea)
        .join(LearningPath, LearningPath.knowledge_area_id == KnowledgeArea.id)
        .where(LearningPath.id == path_id)
    ).scalar_one_or_none()


__all__ = [
    "ESTADOS_ABIERTOS",
    "ESTADOS_NAVEGABLES",
    "ContextoContenido",
    "area_de_ruta",
    "asegurar_contenido_listo",
    "asegurar_desbloqueado",
    "avance_de_modulo",
    "contexto_de_evaluacion",
    "contexto_de_leccion",
    "contexto_de_modulo",
    "contexto_de_tema",
    "evaluacion_de_modulo",
]
