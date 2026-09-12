"""Avance por lección, módulo y ruta, y desbloqueo progresivo del mapa.

Contrato §3.4 (`user_lesson_progress`, `user_module_progress`, `user_path_progress`),
§6.9 reglas A1 y A7, §7.5 (`GET /paths/{path_id}` usa `estado_mapa_ruta`).

Reglas duras que implementa este archivo:

* **A1 — repetición**: `user_lesson_progress.completion_count` es la fuente del
  `completion_index` que decide el multiplicador de XP (1.ª vez completo, 2.ª al 20 %,
  3.ª y siguientes 0). Aquí solo se **cuenta**; el importe lo paga `gamification`.
* **A7 — finalización verificable**: `MODULE_COMPLETED` exige todas las lecciones
  completas **y** la evaluación aprobada; `PATH_COMPLETED` exige todos los módulos
  completos. Los tres eventos los deriva el servidor, nunca el cliente.
* **Desbloqueo progresivo**: un módulo pasa de `LOCKED` a `AVAILABLE` cuando su
  prerrequisito (explícito en `path_modules.prerequisite_module_id` o implícito por
  `position`) está completado. El primer módulo de la ruta nace `AVAILABLE`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import ensure_utc, utcnow
from app.models.content import LearningPath, Lesson, PathModule, Topic
from app.models.enums import EventType, ModuleStatus, PathStatus, ProgressState
from app.models.gamification import DomainEvent
from app.models.progress import (
    UserLessonProgress,
    UserModuleProgress,
    UserPathProgress,
    UserTopicProgress,
)
from app.modules.progress import a_decimal_2, a_float


@dataclass(slots=True)
class ResultadoLeccion:
    """Lo que produce completar una lección: base del `RewardsReceipt` de §7.10."""

    lesson_id: uuid.UUID
    topic_id: uuid.UUID
    module_id: uuid.UUID
    learning_path_id: uuid.UUID | None
    knowledge_area_id: uuid.UUID | None
    completion_index: int
    is_first_completion: bool
    module_completed: bool
    path_completed: bool
    modulo_desbloqueado_id: uuid.UUID | None = None
    eventos: list[EventType] = field(default_factory=list)


@dataclass(slots=True)
class NodoLeccion:
    """Una lección en el mapa de la ruta."""

    lesson_id: uuid.UUID
    title: str
    position: int
    estimated_seconds: int
    status: ProgressState
    completion_count: int
    accuracy_pct: float | None


@dataclass(slots=True)
class NodoTema:
    """Un tema del mapa, con su dominio y sus lecciones."""

    topic_id: uuid.UUID
    title: str
    position: int
    mastery: float
    is_weak: bool
    lecciones: list[NodoLeccion] = field(default_factory=list)


@dataclass(slots=True)
class NodoModulo:
    """Una zona del territorio: un módulo con su estado de bloqueo y su dominio."""

    module_id: uuid.UUID
    title: str
    flavor_name: str | None
    position: int
    status: ModuleStatus
    lessons_total: int
    lessons_completed: int
    mastery: float
    assessment_best_score: float | None
    assessment_passed: bool
    temas: list[NodoTema] = field(default_factory=list)


@dataclass(slots=True)
class MapaRuta:
    """Estado completo del mapa de una ruta para un usuario (P07)."""

    learning_path_id: uuid.UUID
    title: str
    status: ProgressState
    modules_total: int
    modules_completed: int
    lessons_total: int
    lessons_completed: int
    completion_pct: float
    current_module_id: uuid.UUID | None
    current_lesson_id: uuid.UUID | None
    modulos: list[NodoModulo] = field(default_factory=list)


@dataclass(slots=True)
class EstadoModulo:
    """Resultado de recalcular un módulo."""

    fila: UserModuleProgress
    completado_ahora: bool
    modulo_desbloqueado_id: uuid.UUID | None = None
    eventos: list[EventType] = field(default_factory=list)


@dataclass(slots=True)
class EstadoRuta:
    """Resultado de recalcular una ruta."""

    fila: UserPathProgress
    completada_ahora: bool
    eventos: list[EventType] = field(default_factory=list)


class ServicioProgreso:
    """Casos de uso del avance del usuario por el contenido."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- inicialización ---------------------------------------------------

    def asegurar_progreso_ruta(
        self, user_id: uuid.UUID, learning_path_id: uuid.UUID, *, ahora: datetime | None = None
    ) -> UserPathProgress:
        """Crea (si faltan) las filas de progreso de la ruta y de sus módulos.

        El primer módulo nace `AVAILABLE` y el resto `LOCKED`: es el desbloqueo
        progresivo del mapa. Es idempotente.
        """
        momento = ensure_utc(ahora) if ahora else utcnow()
        ruta = self.db.get(LearningPath, learning_path_id)
        if ruta is None:
            raise LookupError(f"La ruta {learning_path_id} no existe.")

        modulos = list(
            self.db.execute(
                sa.select(PathModule)
                .where(PathModule.learning_path_id == learning_path_id)
                .order_by(PathModule.position)
            ).scalars()
        )
        existentes = {
            fila.module_id: fila
            for fila in self.db.execute(
                sa.select(UserModuleProgress).where(
                    UserModuleProgress.user_id == user_id,
                    UserModuleProgress.learning_path_id == learning_path_id,
                )
            ).scalars()
        }
        for indice, modulo in enumerate(modulos):
            if modulo.id in existentes:
                continue
            desbloqueado = indice == 0 and modulo.prerequisite_module_id is None
            self.db.add(
                UserModuleProgress(
                    user_id=user_id,
                    module_id=modulo.id,
                    learning_path_id=learning_path_id,
                    status=ModuleStatus.AVAILABLE if desbloqueado else ModuleStatus.LOCKED,
                    lessons_total=self._contar_lecciones_modulo(modulo.id),
                    unlocked_at=momento if desbloqueado else None,
                )
            )

        fila = self._fila_ruta(user_id, learning_path_id)
        self.db.flush()
        self.recalcular_ruta(user_id, learning_path_id, ahora=momento, emitir_eventos=False)
        return fila

    # -- lección ----------------------------------------------------------

    def iniciar_leccion(
        self, user_id: uuid.UUID, lesson_id: uuid.UUID, *, ahora: datetime | None = None
    ) -> UserLessonProgress:
        """Marca la lección como en curso y despierta el avance de módulo y ruta."""
        momento = ensure_utc(ahora) if ahora else utcnow()
        leccion, topic, modulo = self._contexto_de_leccion(lesson_id)
        fila = self._fila_leccion(user_id, leccion, topic)
        if fila.status == ProgressState.NOT_STARTED:
            fila.status = ProgressState.IN_PROGRESS

        fila_modulo = self._fila_modulo(user_id, modulo)
        if fila_modulo.started_at is None:
            fila_modulo.started_at = momento
        if fila_modulo.status in (ModuleStatus.LOCKED, ModuleStatus.AVAILABLE):
            fila_modulo.status = ModuleStatus.IN_PROGRESS

        fila_ruta = self._fila_ruta(user_id, modulo.learning_path_id)
        if fila_ruta.started_at is None:
            fila_ruta.started_at = momento
        if fila_ruta.status == ProgressState.NOT_STARTED:
            fila_ruta.status = ProgressState.IN_PROGRESS
        fila_ruta.last_activity_at = momento
        self.db.flush()
        return fila

    def completar_leccion(
        self,
        user_id: uuid.UUID,
        lesson_id: uuid.UUID,
        *,
        questions_total: int = 0,
        questions_correct: int = 0,
        active_seconds: int = 0,
        ahora: datetime | None = None,
        timezone_name: str | None = None,
        emitir_eventos: bool = True,
    ) -> ResultadoLeccion:
        """Registra la finalización de una lección y propaga módulo, ruta y desbloqueos.

        Devuelve el `completion_index` (regla A1) sin calcular ni un punto de XP: el
        importe lo decide `gamification` a partir del evento `LESSON_COMPLETED`.
        """
        momento = ensure_utc(ahora) if ahora else utcnow()
        leccion, topic, modulo = self._contexto_de_leccion(lesson_id)
        area_id = self._area_de_ruta(modulo.learning_path_id)

        fila = self._fila_leccion(user_id, leccion, topic)
        primera = fila.completion_count == 0
        fila.completion_count = int(fila.completion_count) + 1
        fila.status = ProgressState.COMPLETED
        fila.questions_total = int(questions_total)
        fila.questions_correct = int(questions_correct)
        fila.accuracy_pct = (
            a_decimal_2(100.0 * questions_correct / questions_total)
            if questions_total > 0
            else None
        )
        fila.active_seconds = int(fila.active_seconds) + max(0, int(active_seconds))
        if fila.first_completed_at is None:
            fila.first_completed_at = momento
        fila.last_completed_at = momento
        fila.last_block_position = int(leccion.block_count or 0)
        self.db.flush()

        resultado = ResultadoLeccion(
            lesson_id=lesson_id,
            topic_id=topic.id,
            module_id=modulo.id,
            learning_path_id=modulo.learning_path_id,
            knowledge_area_id=area_id,
            completion_index=int(fila.completion_count),
            is_first_completion=primera,
            module_completed=False,
            path_completed=False,
        )

        if emitir_eventos:
            self._emitir(
                EventType.LESSON_COMPLETED,
                user_id,
                {
                    "lesson_id": str(lesson_id),
                    "topic_id": str(topic.id),
                    "module_id": str(modulo.id),
                    "path_id": str(modulo.learning_path_id),
                    "knowledge_area_id": str(area_id) if area_id else None,
                    "questions_total": int(questions_total),
                    "questions_correct": int(questions_correct),
                    "accuracy_pct": a_float(fila.accuracy_pct),
                    "duration_s": int(active_seconds),
                    "completion_index": resultado.completion_index,
                    "is_first_completion": primera,
                    "is_low_content": bool(leccion.is_low_content),
                },
                clave=f"lesson-complete:{user_id}:{lesson_id}:{resultado.completion_index}",
                momento=momento,
                timezone_name=timezone_name,
            )
            resultado.eventos.append(EventType.LESSON_COMPLETED)

        estado_modulo = self.recalcular_modulo(
            user_id, modulo.id, ahora=momento, timezone_name=timezone_name, emitir_eventos=emitir_eventos
        )
        resultado.module_completed = estado_modulo.completado_ahora
        resultado.modulo_desbloqueado_id = estado_modulo.modulo_desbloqueado_id
        resultado.eventos.extend(estado_modulo.eventos)

        estado_ruta = self.recalcular_ruta(
            user_id,
            modulo.learning_path_id,
            ahora=momento,
            timezone_name=timezone_name,
            emitir_eventos=emitir_eventos,
        )
        resultado.path_completed = estado_ruta.completada_ahora
        resultado.eventos.extend(estado_ruta.eventos)
        return resultado

    # -- módulo -----------------------------------------------------------

    def recalcular_modulo(
        self,
        user_id: uuid.UUID,
        module_id: uuid.UUID,
        *,
        ahora: datetime | None = None,
        timezone_name: str | None = None,
        emitir_eventos: bool = True,
    ) -> EstadoModulo:
        """Recuenta lecciones del módulo, aplica A7 y desbloquea el siguiente."""
        momento = ensure_utc(ahora) if ahora else utcnow()
        modulo = self.db.get(PathModule, module_id)
        if modulo is None:
            raise LookupError(f"El módulo {module_id} no existe.")
        fila = self._fila_modulo(user_id, modulo)

        totales = self._contar_lecciones_modulo(module_id)
        completadas = self.db.execute(
            sa.select(sa.func.count(UserLessonProgress.id)).where(
                UserLessonProgress.user_id == user_id,
                UserLessonProgress.module_id == module_id,
                UserLessonProgress.status == ProgressState.COMPLETED,
            )
        ).scalar_one()
        fila.lessons_total = int(totales)
        fila.lessons_completed = int(completadas)

        # A7: módulo completo = todas las lecciones + evaluación aprobada.
        evaluacion_aprobada = fila.assessment_passed_at is not None
        todas = totales > 0 and int(completadas) >= totales
        completado_ahora = False
        if todas and evaluacion_aprobada and fila.completed_at is None:
            fila.completed_at = momento
            completado_ahora = True
        if fila.completed_at is not None and fila.status not in (
            ModuleStatus.COMPLETED,
            ModuleStatus.MASTERED,
        ):
            fila.status = ModuleStatus.COMPLETED
        elif fila.completed_at is None and int(completadas) > 0 and fila.status == ModuleStatus.AVAILABLE:
            fila.status = ModuleStatus.IN_PROGRESS
        self.db.flush()

        estado = EstadoModulo(fila=fila, completado_ahora=completado_ahora)
        if completado_ahora:
            area_id = self._area_de_ruta(modulo.learning_path_id)
            if emitir_eventos:
                self._emitir(
                    EventType.MODULE_COMPLETED,
                    user_id,
                    {
                        "module_id": str(module_id),
                        "module_index": int(modulo.position),
                        "path_id": str(modulo.learning_path_id),
                        "knowledge_area_id": str(area_id) if area_id else None,
                    },
                    clave=f"module-complete:{user_id}:{module_id}:1",
                    momento=momento,
                    timezone_name=timezone_name,
                )
                estado.eventos.append(EventType.MODULE_COMPLETED)
            estado.modulo_desbloqueado_id = self.desbloquear_siguiente_modulo(
                user_id, modulo, ahora=momento
            )
        return estado

    def desbloquear_siguiente_modulo(
        self, user_id: uuid.UUID, modulo: PathModule, *, ahora: datetime | None = None
    ) -> uuid.UUID | None:
        """Pasa el siguiente módulo de `LOCKED` a `AVAILABLE`. Devuelve su id."""
        momento = ensure_utc(ahora) if ahora else utcnow()
        siguiente = self.db.execute(
            sa.select(PathModule)
            .where(
                PathModule.learning_path_id == modulo.learning_path_id,
                sa.or_(
                    PathModule.prerequisite_module_id == modulo.id,
                    sa.and_(
                        PathModule.prerequisite_module_id.is_(None),
                        PathModule.position == modulo.position + 1,
                    ),
                ),
            )
            .order_by(PathModule.position)
            .limit(1)
        ).scalar_one_or_none()
        if siguiente is None:
            return None
        fila = self._fila_modulo(user_id, siguiente)
        if fila.status == ModuleStatus.LOCKED:
            fila.status = ModuleStatus.AVAILABLE
            fila.unlocked_at = momento
            self.db.flush()
            return siguiente.id
        return None

    # -- ruta -------------------------------------------------------------

    def recalcular_ruta(
        self,
        user_id: uuid.UUID,
        learning_path_id: uuid.UUID,
        *,
        ahora: datetime | None = None,
        timezone_name: str | None = None,
        emitir_eventos: bool = True,
    ) -> EstadoRuta:
        """Recalcula totales, porcentaje, «continuar» y la finalización de la ruta (A7)."""
        momento = ensure_utc(ahora) if ahora else utcnow()
        fila = self._fila_ruta(user_id, learning_path_id)

        modulos_total, modulos_completos = self.db.execute(
            sa.select(
                sa.func.count(PathModule.id),
                sa.func.count(UserModuleProgress.completed_at),
            )
            .select_from(PathModule)
            .outerjoin(
                UserModuleProgress,
                sa.and_(
                    UserModuleProgress.module_id == PathModule.id,
                    UserModuleProgress.user_id == user_id,
                ),
            )
            .where(PathModule.learning_path_id == learning_path_id)
        ).one()

        lecciones_total = self.db.execute(
            sa.select(sa.func.count(Lesson.id))
            .select_from(Lesson)
            .join(Topic, Topic.id == Lesson.topic_id)
            .join(PathModule, PathModule.id == Topic.module_id)
            .where(PathModule.learning_path_id == learning_path_id)
        ).scalar_one()

        lecciones_completas = self.db.execute(
            sa.select(sa.func.count(UserLessonProgress.id))
            .select_from(UserLessonProgress)
            .join(PathModule, PathModule.id == UserLessonProgress.module_id)
            .where(
                UserLessonProgress.user_id == user_id,
                UserLessonProgress.status == ProgressState.COMPLETED,
                PathModule.learning_path_id == learning_path_id,
            )
        ).scalar_one()

        fila.modules_total = int(modulos_total)
        fila.modules_completed = int(modulos_completos)
        fila.lessons_total = int(lecciones_total)
        fila.lessons_completed = int(lecciones_completas)
        fila.completion_pct = (
            a_decimal_2(100.0 * int(lecciones_completas) / int(lecciones_total))
            if int(lecciones_total) > 0
            else Decimal("0.00")
        )
        fila.last_activity_at = momento

        siguiente = self._siguiente_paso(user_id, learning_path_id)
        fila.current_module_id = siguiente[0]
        fila.current_lesson_id = siguiente[1]

        completada_ahora = False
        if (
            int(modulos_total) > 0
            and int(modulos_completos) >= int(modulos_total)
            and fila.completed_at is None
        ):
            fila.completed_at = momento
            fila.status = ProgressState.COMPLETED
            completada_ahora = True
        elif fila.status == ProgressState.NOT_STARTED and int(lecciones_completas) > 0:
            fila.status = ProgressState.IN_PROGRESS
        self.db.flush()

        estado = EstadoRuta(fila=fila, completada_ahora=completada_ahora)
        if completada_ahora and emitir_eventos:
            area_id = self._area_de_ruta(learning_path_id)
            dias = 0
            if fila.started_at is not None:
                dias = max(0, (momento - ensure_utc(fila.started_at)).days)
            self._emitir(
                EventType.PATH_COMPLETED,
                user_id,
                {
                    "path_id": str(learning_path_id),
                    "knowledge_area_id": str(area_id) if area_id else None,
                    "modules": int(modulos_total),
                    "days_elapsed": dias,
                },
                clave=f"path-complete:{user_id}:{learning_path_id}:1",
                momento=momento,
                timezone_name=timezone_name,
            )
            estado.eventos.append(EventType.PATH_COMPLETED)
        return estado

    # -- mapa -------------------------------------------------------------

    def estado_mapa_ruta(self, user_id: uuid.UUID, learning_path_id: uuid.UUID) -> MapaRuta:
        """Mapa de la ruta con el estado de bloqueo y de dominio de cada nodo (P07).

        Se resuelve en cuatro consultas: ruta, módulos, temas y lecciones.
        Índices usados: `ix_user_module_progress_user_id_learning_path_id`,
        `ix_user_topic_progress_user_id_knowledge_area_id`,
        `ix_user_lesson_progress_user_id_module_id`.
        """
        ruta = self.db.get(LearningPath, learning_path_id)
        if ruta is None:
            raise LookupError(f"La ruta {learning_path_id} no existe.")
        fila_ruta = self._fila_ruta(user_id, learning_path_id)

        modulos = self.db.execute(
            sa.select(PathModule, UserModuleProgress)
            .outerjoin(
                UserModuleProgress,
                sa.and_(
                    UserModuleProgress.module_id == PathModule.id,
                    UserModuleProgress.user_id == user_id,
                ),
            )
            .where(PathModule.learning_path_id == learning_path_id)
            .order_by(PathModule.position)
        ).all()

        temas = self.db.execute(
            sa.select(Topic, UserTopicProgress)
            .join(PathModule, PathModule.id == Topic.module_id)
            .outerjoin(
                UserTopicProgress,
                sa.and_(
                    UserTopicProgress.topic_id == Topic.id,
                    UserTopicProgress.user_id == user_id,
                ),
            )
            .where(PathModule.learning_path_id == learning_path_id)
            .order_by(Topic.position)
        ).all()

        lecciones = self.db.execute(
            sa.select(Lesson, UserLessonProgress)
            .join(Topic, Topic.id == Lesson.topic_id)
            .join(PathModule, PathModule.id == Topic.module_id)
            .outerjoin(
                UserLessonProgress,
                sa.and_(
                    UserLessonProgress.lesson_id == Lesson.id,
                    UserLessonProgress.user_id == user_id,
                ),
            )
            .where(PathModule.learning_path_id == learning_path_id)
            .order_by(Lesson.position)
        ).all()

        nodos_tema: dict[uuid.UUID, NodoTema] = {}
        for topic, progreso_tema in temas:
            nodos_tema[topic.id] = NodoTema(
                topic_id=topic.id,
                title=topic.title,
                position=int(topic.position),
                mastery=a_float(progreso_tema.mastery) if progreso_tema else 0.0,
                is_weak=bool(progreso_tema.is_weak) if progreso_tema else False,
            )
        for leccion, progreso_leccion in lecciones:
            nodo = nodos_tema.get(leccion.topic_id)
            if nodo is None:
                continue
            nodo.lecciones.append(
                NodoLeccion(
                    lesson_id=leccion.id,
                    title=leccion.title,
                    position=int(leccion.position),
                    estimated_seconds=int(leccion.estimated_seconds or 0),
                    status=progreso_leccion.status if progreso_leccion else ProgressState.NOT_STARTED,
                    completion_count=int(progreso_leccion.completion_count) if progreso_leccion else 0,
                    accuracy_pct=a_float(progreso_leccion.accuracy_pct, 0.0)
                    if progreso_leccion and progreso_leccion.accuracy_pct is not None
                    else None,
                )
            )

        temas_por_modulo: dict[uuid.UUID, list[NodoTema]] = {}
        for topic, _ in temas:
            temas_por_modulo.setdefault(topic.module_id, []).append(nodos_tema[topic.id])

        nodos_modulo: list[NodoModulo] = []
        for modulo, progreso_modulo in modulos:
            nodos_modulo.append(
                NodoModulo(
                    module_id=modulo.id,
                    title=modulo.title,
                    flavor_name=modulo.flavor_name,
                    position=int(modulo.position),
                    status=progreso_modulo.status if progreso_modulo else ModuleStatus.LOCKED,
                    lessons_total=int(progreso_modulo.lessons_total) if progreso_modulo else 0,
                    lessons_completed=int(progreso_modulo.lessons_completed) if progreso_modulo else 0,
                    mastery=a_float(progreso_modulo.mastery) if progreso_modulo else 0.0,
                    assessment_best_score=(
                        a_float(progreso_modulo.assessment_best_score)
                        if progreso_modulo and progreso_modulo.assessment_best_score is not None
                        else None
                    ),
                    assessment_passed=bool(
                        progreso_modulo and progreso_modulo.assessment_passed_at is not None
                    ),
                    temas=sorted(temas_por_modulo.get(modulo.id, []), key=lambda t: t.position),
                )
            )

        return MapaRuta(
            learning_path_id=learning_path_id,
            title=ruta.title,
            status=fila_ruta.status,
            modules_total=int(fila_ruta.modules_total),
            modules_completed=int(fila_ruta.modules_completed),
            lessons_total=int(fila_ruta.lessons_total),
            lessons_completed=int(fila_ruta.lessons_completed),
            completion_pct=a_float(fila_ruta.completion_pct),
            current_module_id=fila_ruta.current_module_id,
            current_lesson_id=fila_ruta.current_lesson_id,
            modulos=nodos_modulo,
        )

    def continuar_aventura(self, user_id: uuid.UUID) -> UserPathProgress | None:
        """Ruta en la que el usuario debe continuar: la de actividad más reciente.

        Índice usado: `ix_user_path_progress_user_id_last_activity_at`.
        """
        return self.db.execute(
            sa.select(UserPathProgress)
            .join(LearningPath, LearningPath.id == UserPathProgress.learning_path_id)
            .where(
                UserPathProgress.user_id == user_id,
                UserPathProgress.status != ProgressState.ARCHIVED,
                LearningPath.status != PathStatus.ARCHIVED,
            )
            .order_by(
                UserPathProgress.last_activity_at.desc().nullslast(),
                UserPathProgress.id,
            )
            .limit(1)
        ).scalar_one_or_none()

    # -- internos ---------------------------------------------------------

    def _siguiente_paso(
        self, user_id: uuid.UUID, learning_path_id: uuid.UUID
    ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        """Primera lección no completada de la ruta, en orden de módulo, tema y lección."""
        fila = self.db.execute(
            sa.select(PathModule.id, Lesson.id)
            .select_from(Lesson)
            .join(Topic, Topic.id == Lesson.topic_id)
            .join(PathModule, PathModule.id == Topic.module_id)
            .outerjoin(
                UserLessonProgress,
                sa.and_(
                    UserLessonProgress.lesson_id == Lesson.id,
                    UserLessonProgress.user_id == user_id,
                ),
            )
            .where(
                PathModule.learning_path_id == learning_path_id,
                sa.or_(
                    UserLessonProgress.id.is_(None),
                    UserLessonProgress.status != ProgressState.COMPLETED,
                ),
            )
            .order_by(PathModule.position, Topic.position, Lesson.position)
            .limit(1)
        ).one_or_none()
        if fila is None:
            return None, None
        return fila[0], fila[1]

    def _contexto_de_leccion(self, lesson_id: uuid.UUID) -> tuple[Lesson, Topic, PathModule]:
        fila = self.db.execute(
            sa.select(Lesson, Topic, PathModule)
            .join(Topic, Topic.id == Lesson.topic_id)
            .join(PathModule, PathModule.id == Topic.module_id)
            .where(Lesson.id == lesson_id)
        ).one_or_none()
        if fila is None:
            raise LookupError(f"La lección {lesson_id} no existe.")
        return fila[0], fila[1], fila[2]

    def _contar_lecciones_modulo(self, module_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                sa.select(sa.func.count(Lesson.id))
                .select_from(Lesson)
                .join(Topic, Topic.id == Lesson.topic_id)
                .where(Topic.module_id == module_id)
            ).scalar_one()
        )

    def _area_de_ruta(self, learning_path_id: uuid.UUID | None) -> uuid.UUID | None:
        if learning_path_id is None:
            return None
        return self.db.execute(
            sa.select(LearningPath.knowledge_area_id).where(LearningPath.id == learning_path_id)
        ).scalar_one_or_none()

    def _fila_leccion(
        self, user_id: uuid.UUID, leccion: Lesson, topic: Topic
    ) -> UserLessonProgress:
        fila = self.db.execute(
            sa.select(UserLessonProgress).where(
                UserLessonProgress.user_id == user_id,
                UserLessonProgress.lesson_id == leccion.id,
            )
        ).scalar_one_or_none()
        if fila is None:
            fila = UserLessonProgress(
                user_id=user_id,
                lesson_id=leccion.id,
                topic_id=topic.id,
                module_id=topic.module_id,
            )
            self.db.add(fila)
            self.db.flush()
        return fila

    def _fila_modulo(self, user_id: uuid.UUID, modulo: PathModule) -> UserModuleProgress:
        fila = self.db.execute(
            sa.select(UserModuleProgress).where(
                UserModuleProgress.user_id == user_id,
                UserModuleProgress.module_id == modulo.id,
            )
        ).scalar_one_or_none()
        if fila is None:
            fila = UserModuleProgress(
                user_id=user_id,
                module_id=modulo.id,
                learning_path_id=modulo.learning_path_id,
                status=ModuleStatus.AVAILABLE if modulo.position <= 1 else ModuleStatus.LOCKED,
            )
            self.db.add(fila)
            self.db.flush()
        return fila

    def _fila_ruta(self, user_id: uuid.UUID, learning_path_id: uuid.UUID) -> UserPathProgress:
        fila = self.db.execute(
            sa.select(UserPathProgress).where(
                UserPathProgress.user_id == user_id,
                UserPathProgress.learning_path_id == learning_path_id,
            )
        ).scalar_one_or_none()
        if fila is None:
            fila = UserPathProgress(user_id=user_id, learning_path_id=learning_path_id)
            self.db.add(fila)
            self.db.flush()
        return fila

    def _emitir(
        self,
        event_type: EventType,
        user_id: uuid.UUID,
        payload: dict,
        *,
        clave: str,
        momento: datetime,
        timezone_name: str | None = None,
    ) -> None:
        """Inserta el evento si la clave es nueva; la cascada nunca duplica (§8.3)."""
        existe = self.db.execute(
            sa.select(sa.literal(1))
            .select_from(DomainEvent)
            .where(DomainEvent.idempotency_key == clave)
            .limit(1)
        ).scalar_one_or_none()
        if existe:
            return
        self.db.add(
            DomainEvent(
                event_type=event_type,
                user_id=user_id,
                occurred_at=momento,
                timezone=timezone_name,
                source_module="progress",
                payload=payload,
                idempotency_key=clave,
            )
        )
        self.db.flush()


__all__ = [
    "EstadoModulo",
    "EstadoRuta",
    "MapaRuta",
    "NodoLeccion",
    "NodoModulo",
    "NodoTema",
    "ResultadoLeccion",
    "ServicioProgreso",
]
