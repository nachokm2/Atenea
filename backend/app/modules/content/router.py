"""Rutas HTTP del módulo `content` (§7.4, §7.5, §7.6 y §7.7).

Este archivo expone `router = APIRouter()` **sin prefijo**: el `/api/v1` y el montaje
los pone el router raíz (`app/api/v1/__init__.py`, que pertenece a otro agente).

| Método | Ruta | Sección |
|---|---|---|
| GET | `/knowledge-areas`, `/knowledge-areas/{id}`, `/territories` | §7.4 |
| GET/POST/PATCH/DELETE | `/paths…` | §7.5 |
| GET/POST | `/lessons…`, `/activities…`, `/reviews…`, `/topics/{id}/explain`, `/content/report` | §7.6 |
| GET/POST | `/modules/{id}/assessment`, `/assessments…`, `/assessment-attempts…` | §7.7 |

`GET /me/knowledge` **no** está aquí: lo sirve el router de `progress` (§7.4).

Tres reglas que se ven en cada handler:

* `Idempotency-Key` obligatoria donde §8.3 la exige, vía `idem.require()`.
* Ninguna respuesta lleva `answer_key`: las preguntas salen por `QuestionOut`.
* Las acciones que otorgan recompensas devuelven el `RewardsReceipt` tal cual lo
  produce el motor de gamificación (§7.10).
"""

from __future__ import annotations

import uuid
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, IdempotencyDep
from app.core.errors import AteneaError, NotFound, ValidationFailed
from app.core.limites import freno
from app.models.content import LearningPath, Lesson, LessonBlock, PathModule, Question, Topic
from app.models.enums import (
    ContentStatus,
    EventType,
    JobType,
    ModuleStatus,
    ProvenanceContentType,
)
from app.models.ingestion import Document, KnowledgeBase
from app.models.progress import UserPathProgress
from app.modules.content import (
    areas as servicio_areas,
    evaluaciones as servicio_evaluaciones,
    lecciones as servicio_lecciones,
    modulos as servicio_modulos,
    rutas as servicio_rutas,
)
from app.modules.content.schemas import (
    ActivityOut,
    AnswerIn,
    AnswerResultOut,
    AreaModuleOut,
    AssessmentAnswerIn,
    AssessmentAnswerOut,
    AssessmentAttemptOut,
    AssessmentBriefOut,
    AssessmentInfoOut,
    AssessmentReviewOut,
    ContentReportIn,
    ExplanationIn,
    ExplanationOut,
    HeartbeatIn,
    HeartbeatOut,
    JobOut,
    KnowledgeAreaDetailOut,
    KnowledgeAreaOut,
    LessonBlockOut,
    LessonNodeOut,
    LessonOut,
    MasteryExplanationOut,
    ModuleNodeOut,
    Page,
    PageMeta,
    PathConfirmIn,
    PathCreatedOut,
    PathCreateIn,
    PathDetailOut,
    PathSummaryOut,
    PathUpdateIn,
    ProvenanceOut,
    QuestionOut,
    ReviewStartIn,
    ReviewSuggestionOut,
    TerritoryBriefOut,
    TerritoryOut,
    TopicNodeOut,
    WeakTopicOut,
)
from app.modules.gamification.eventos import buscar_por_clave, registrar_evento
from app.modules.gamification.recompensas import ReciboRecompensas
from app.modules.gamification.servicio_config import ServicioConfig
from app.modules.progress import a_float
from app.worker import cola

router = APIRouter()

#: Paginación por defecto y máxima (§8.2).
LIMITE_POR_DEFECTO = 20
LIMITE_MAXIMO = 100


def _pagina(items: list, limit: int) -> Page:
    """Envuelve una lista ya resuelta en el sobre de §8.2."""
    return Page(
        items=items[:limit],
        page=PageMeta(
            limit=limit, next_cursor=None, has_more=len(items) > limit, total=len(items)
        ),
    )


# ---------------------------------------------------------------------------
# §7.4 · Conocimientos y mundo
# ---------------------------------------------------------------------------


def _area_out(fila: servicio_areas.FilaArea) -> KnowledgeAreaOut:
    """Traduce una `FilaArea` del servicio al esquema de salida."""
    area = fila.knowledge_area
    return KnowledgeAreaOut(
        knowledge_area_id=area.id,
        slug=area.slug,
        name=area.name,
        short_name=area.short_name,
        category=area.category,
        description=area.description,
        icon_key=area.icon_key,
        accent_color=area.accent_color,
        is_canonical=bool(area.is_canonical),
        xp=fila.xp,
        level=fila.level,
        rank_title=fila.rank_title,
        mastery=fila.mastery,
        study_seconds=fila.study_seconds,
        status=fila.status,
    )


def _tema_debil_out(tema: servicio_areas.TemaDebil) -> WeakTopicOut:
    """Traduce un tema débil al esquema de salida."""
    return WeakTopicOut(
        topic_id=tema.topic_id,
        title=tema.title,
        mastery=tema.mastery,
        practice_score=tema.practice_score,
        module_id=tema.module_id,
    )


@router.get(
    "/knowledge-areas",
    response_model=Page[KnowledgeAreaOut],
    summary="Catálogo de conocimientos con el dominio del usuario",
)
def listar_conocimientos(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=LIMITE_MAXIMO)] = LIMITE_POR_DEFECTO,
) -> Page[KnowledgeAreaOut]:
    """Taxonomía canónica más los conocimientos propios del usuario (§7.4)."""
    filas = servicio_areas.listar_areas(db, user.id)
    return _pagina([_area_out(f) for f in filas], limit)


@router.get(
    "/knowledge-areas/{area_id}",
    response_model=KnowledgeAreaDetailOut,
    summary="Detalle de un conocimiento con su dominio explicado",
)
def obtener_conocimiento(
    area_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> KnowledgeAreaDetailOut:
    """Nivel, XP, dominio **con su explicación**, tiempo, módulos y temas débiles (§6.7)."""
    detalle = servicio_areas.detalle_area(db, user.id, area_id)
    return KnowledgeAreaDetailOut(
        knowledge_area=_area_out(detalle.fila),
        territory=(
            TerritoryBriefOut(
                territory_id=detalle.territory.id,
                name=detalle.territory.name,
                icon_hint=detalle.territory.icon_hint,
                description=detalle.territory.description,
            )
            if detalle.territory is not None
            else None
        ),
        explain=MasteryExplanationOut(
            practice_pct=detalle.explicacion.practice_pct,
            assessment_pct=detalle.explicacion.assessment_pct,
            modules_mastered=detalle.explicacion.modules_mastered,
            modules_total=detalle.explicacion.modules_total,
            weak_topics=[_tema_debil_out(t) for t in detalle.explicacion.weak_topics],
        ),
        modules=[
            AreaModuleOut(
                module_id=modulo.id,
                title=modulo.title,
                flavor_name=modulo.flavor_name,
                position=int(modulo.position),
                learning_path_id=modulo.learning_path_id,
                status=avance.status if avance else ModuleStatus.LOCKED,
                mastery=a_float(avance.mastery) if avance else 0.0,
                lessons_total=int(avance.lessons_total) if avance else 0,
                lessons_completed=int(avance.lessons_completed) if avance else 0,
            )
            for modulo, avance in detalle.modulos
        ],
        weak_topics=[_tema_debil_out(t) for t in detalle.explicacion.weak_topics],
    )


@router.get(
    "/territories", response_model=Page[TerritoryOut], summary="Mapa simplificado del reino"
)
def listar_territorios(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=LIMITE_MAXIMO)] = LIMITE_POR_DEFECTO,
) -> Page[TerritoryOut]:
    """Territorios con estado y zonas desbloqueadas (§7.4 · P22)."""
    filas = servicio_areas.listar_territorios(db, user.id)
    items = [
        TerritoryOut(
            territory_id=fila.territory.id,
            knowledge_area_id=fila.knowledge_area.id,
            name=fila.territory.name,
            knowledge_name=fila.knowledge_area.name,
            icon_hint=fila.territory.icon_hint,
            description=fila.territory.description,
            status=fila.status,
            mastery=fila.mastery,
            zones_total=fila.zones_total,
            zones_unlocked=fila.zones_unlocked,
            zones_completed=fila.zones_completed,
        )
        for fila in filas
    ]
    return _pagina(items, limit)


# ---------------------------------------------------------------------------
# §7.5 · Rutas de aprendizaje
# ---------------------------------------------------------------------------


def _ruta_out(fila: servicio_rutas.FilaRuta) -> PathSummaryOut:
    """Traduce una ruta con su avance al esquema de salida."""
    ruta = fila.path
    avance = fila.progress
    return PathSummaryOut(
        path_id=ruta.id,
        title=ruta.title,
        summary=ruta.summary,
        goal_text=ruta.goal_text,
        knowledge_area_id=ruta.knowledge_area_id,
        knowledge_area_name=fila.knowledge_area.name if fila.knowledge_area else None,
        origin=ruta.origin,
        status=ruta.status,
        source_mode=ruta.source_mode,
        declared_level=ruta.declared_level,
        coverage_policy=ruta.coverage_policy,
        module_count=int(ruta.module_count),
        estimated_minutes=ruta.estimated_minutes,
        is_seed=ruta.user_id is None,
        is_adopted=avance is not None,
        completion_pct=a_float(avance.completion_pct) if avance else 0.0,
        modules_completed=int(avance.modules_completed) if avance else 0,
        lessons_completed=int(avance.lessons_completed) if avance else 0,
        lessons_total=int(avance.lessons_total) if avance else 0,
        current_module_id=avance.current_module_id if avance else None,
        current_lesson_id=avance.current_lesson_id if avance else None,
        archived_at=ruta.archived_at,
        created_at=ruta.created_at,
    )


def _detalle_out(detalle: servicio_rutas.DetalleRuta) -> PathDetailOut:
    """Traduce el mapa de la ruta al esquema de salida (§7.5 · P07)."""
    mapa = detalle.mapa
    return PathDetailOut(
        path=_ruta_out(
            servicio_rutas.FilaRuta(
                path=detalle.path, knowledge_area=detalle.knowledge_area, progress=None
            )
        ),
        status=mapa.status,
        modules_total=mapa.modules_total,
        modules_completed=mapa.modules_completed,
        lessons_total=mapa.lessons_total,
        lessons_completed=mapa.lessons_completed,
        completion_pct=mapa.completion_pct,
        current_module_id=mapa.current_module_id,
        current_lesson_id=mapa.current_lesson_id,
        modules=[
            ModuleNodeOut(
                module_id=modulo.module_id,
                title=modulo.title,
                flavor_name=modulo.flavor_name,
                position=modulo.position,
                status=modulo.status,
                lessons_total=modulo.lessons_total,
                lessons_completed=modulo.lessons_completed,
                mastery=modulo.mastery,
                assessment_best_score=modulo.assessment_best_score,
                assessment_passed=modulo.assessment_passed,
                topics=[
                    TopicNodeOut(
                        topic_id=tema.topic_id,
                        title=tema.title,
                        position=tema.position,
                        mastery=tema.mastery,
                        is_weak=tema.is_weak,
                        lessons=[
                            LessonNodeOut(
                                lesson_id=leccion.lesson_id,
                                title=leccion.title,
                                position=leccion.position,
                                estimated_seconds=leccion.estimated_seconds,
                                status=leccion.status,
                                content_status=leccion.content_status,
                                completion_count=leccion.completion_count,
                                accuracy_pct=leccion.accuracy_pct,
                            )
                            for leccion in tema.lecciones
                        ],
                    )
                    for tema in modulo.temas
                ],
            )
            for modulo in mapa.modulos
        ],
        weak_topic_ids=detalle.weak_topic_ids,
    )


@router.get("/paths", response_model=Page[PathSummaryOut], summary="Mis rutas y Rutas del Reino")
def listar_rutas(
    db: DbSession,
    user: CurrentUser,
    scope: Annotated[str, Query(pattern="^(mine|seed|all)$")] = "all",
    limit: Annotated[int, Query(ge=1, le=LIMITE_MAXIMO)] = LIMITE_POR_DEFECTO,
) -> Page[PathSummaryOut]:
    """Listado de rutas con el avance del usuario (§7.5 · P22)."""
    filas = servicio_rutas.listar_rutas(db, user.id, scope=scope)
    return _pagina([_ruta_out(f) for f in filas], limit)


def _biblioteca_de_documentos(
    db: Session, usuario_id: uuid.UUID, documentos: list[uuid.UUID]
) -> uuid.UUID | None:
    """Biblioteca a la que pertenecen los documentos elegidos para la ruta.

    Comprueba de paso que sean del usuario: pedir una ruta sobre el material de
    otra persona sería leer sus apuntes. Si vienen de bibliotecas distintas se
    rechaza, porque una ruta se alimenta de una sola.
    """
    if not documentos:
        return None
    filas = (
        db.execute(
            sa.select(Document.id, Document.knowledge_base_id)
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(
                Document.id.in_(documentos),
                Document.deleted_at.is_(None),
                KnowledgeBase.user_id == usuario_id,
            )
        )
        .all()
    )
    encontrados = {fila[0] for fila in filas}
    faltan = [str(d) for d in documentos if d not in encontrados]
    if faltan:
        raise NotFound(
            "No encontramos ese material entre tus documentos.",
            details={"document_ids": faltan},
        )
    bibliotecas = {fila[1] for fila in filas}
    if len(bibliotecas) > 1:
        raise ValidationFailed(
            "Elige material de una sola biblioteca para esta ruta.",
            details={"knowledge_base_ids": [str(b) for b in bibliotecas]},
        )
    return bibliotecas.pop()


@router.post(
    "/paths",
    response_model=PathCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crea una ruta y encola su diseño",
    # 5 por minuto (§8.7): cada llamada encarga un diseño a Claude y gasta dinero.
    dependencies=[Depends(freno("5/minute"))],
)
def crear_ruta(
    cuerpo: PathCreateIn,
    db: DbSession,
    user: CurrentUser,
    idem: IdempotencyDep,
    response: Response,
) -> PathCreatedOut:
    """Crea la ruta y **encola su diseño** (§7.5 · P05).

    Encolar aquí no es un detalle: sin este trabajo la ruta se queda en borrador
    para siempre y el usuario ve una pantalla de generación que no avanza. El
    trabajo lo ejecuta el worker, que llama a la Fase A del módulo `ai`.

    El identificador de la ruta hace de clave de idempotencia del trabajo, así
    que pulsar dos veces "crear" no diseña la ruta dos veces ni cobra dos veces.
    """
    # Los documentos elegidos deciden de qué biblioteca se alimenta la ruta. Sin
    # esto, la Fase A busca material en una biblioteca vacía y el diseño falla
    # diciendo que no pudo leer el documento, que es justo lo contrario de lo
    # que pasó: el documento estaba, pero nadie se lo pasó.
    biblioteca_id = cuerpo.knowledge_base_id or _biblioteca_de_documentos(
        db, user.id, cuerpo.document_ids or []
    )

    resultado = servicio_rutas.crear_ruta(
        db,
        user.id,
        idempotency_key=idem.require(),
        goal_text=cuerpo.goal_text,
        declared_level=cuerpo.declared_level,
        source_mode=cuerpo.source_mode,
        knowledge_area_id=cuerpo.knowledge_area_id,
        knowledge_area_hint=cuerpo.knowledge_area_hint,
        knowledge_base_id=biblioteca_id,
        coverage_policy=cuerpo.coverage_policy,
        title=cuerpo.title,
    )
    if not resultado.creada:
        response.status_code = status.HTTP_200_OK

    trabajo = cola.encolar(
        db,
        job_type=JobType.PATH_DESIGN,
        usuario_id=user.id,
        target_type="path",
        target_id=resultado.path.id,
        learning_path_id=resultado.path.id,
        payload={
            "learning_path_id": str(resultado.path.id),
            "goal_text": resultado.path.goal_text or "",
        },
        idempotency_key=f"path-design:{resultado.path.id}",
        progress_label="Diseñando módulos",
    )

    detalle = servicio_rutas.detalle_ruta(db, user.id, resultado.path.id)
    return PathCreatedOut(
        path=_detalle_out(detalle).path,
        job=JobOut(
            id=trabajo.id,
            job_type=trabajo.job_type.value,
            status=trabajo.status.value,
            progress_pct=float(trabajo.progress_pct or 0),
            progress_label=trabajo.progress_label,
            error=trabajo.error_message,
        ),
    )


@router.get("/paths/{path_id}", response_model=PathDetailOut, summary="Mapa de la ruta")
def obtener_ruta(path_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PathDetailOut:
    """Módulos, temas, lecciones y estado de bloqueo por usuario (§7.5 · P07)."""
    return _detalle_out(servicio_rutas.detalle_ruta(db, user.id, path_id))


def _encolar_primer_modulo(
    db: Session, usuario_id: uuid.UUID, path_id: uuid.UUID, detalle: object  # noqa: ARG001 - firma fijada por quien llama
) -> None:
    """Encola la redacción del primer módulo que aún no tenga contenido.

    Es la Fase B de la generación, y es perezosa a propósito: se escribe un
    módulo, no la ruta entera. Escribirla completa costaría de más y el usuario
    abandona la mitad de las rutas que empieza.

    La clave de idempotencia lleva el módulo, así que confirmar dos veces no
    encarga el trabajo dos veces.
    """
    modulo = db.execute(
        sa.select(PathModule)
        .where(
            PathModule.learning_path_id == path_id,
            PathModule.content_status != ContentStatus.READY,
        )
        .order_by(PathModule.position)
        .limit(1)
    ).scalar_one_or_none()
    if modulo is None:
        return

    cola.encolar(
        db,
        job_type=JobType.MODULE_GENERATION,
        usuario_id=usuario_id,
        target_type="module",
        target_id=modulo.id,
        learning_path_id=path_id,
        payload={"module_id": str(modulo.id), "learning_path_id": str(path_id)},
        idempotency_key=f"module-generation:{modulo.id}",
        progress_label="Escribiendo las lecciones",
    )


@router.post(
    "/paths/{path_id}/confirm", response_model=PathDetailOut, summary="Confirma el esquema revisado"
)
def confirmar_ruta(
    path_id: uuid.UUID, cuerpo: PathConfirmIn, db: DbSession, user: CurrentUser
) -> PathDetailOut:
    """Reordena, renombra o elimina temas y encola el módulo 1 (§7.5)."""
    servicio_rutas.confirmar_ruta(
        db,
        user.id,
        path_id,
        cambios=[
            servicio_rutas.CambioEsquema(
                topic_id=cambio.topic_id,
                title=cambio.title,
                position=cambio.position,
                remove=cambio.remove,
            )
            for cambio in cuerpo.topics
        ],
        coverage_policy=cuerpo.coverage_policy,
    )

    detalle = servicio_rutas.detalle_ruta(db, user.id, path_id)
    _encolar_primer_modulo(db, user.id, path_id, detalle)
    return _detalle_out(detalle)


@router.patch("/paths/{path_id}", response_model=PathDetailOut, summary="Renombra o archiva la ruta")
def actualizar_ruta(
    path_id: uuid.UUID, cuerpo: PathUpdateIn, db: DbSession, user: CurrentUser
) -> PathDetailOut:
    """Cambia el título o archiva la ruta del usuario (§7.5)."""
    servicio_rutas.actualizar_ruta(
        db, user.id, path_id, title=cuerpo.title, archived=cuerpo.archived
    )
    return _detalle_out(servicio_rutas.detalle_ruta(db, user.id, path_id))


@router.delete(
    "/paths/{path_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Elimina la ruta"
)
def eliminar_ruta(path_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    """Elimina la ruta del usuario y cancela sus misiones de ruta (§7.5)."""
    servicio_rutas.eliminar_ruta(db, user.id, path_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/paths/{path_id}/adopt", response_model=PathDetailOut, summary="Adopta una Ruta del Reino"
)
def adoptar_ruta(path_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PathDetailOut:
    """Crea el progreso del usuario sin duplicar contenido (§5.9 D17)."""
    return _detalle_out(servicio_rutas.adoptar_ruta(db, user.id, path_id))


# ---------------------------------------------------------------------------
# §7.6 · Lección, actividad y respuestas
# ---------------------------------------------------------------------------


def _pregunta_out(datos: dict) -> QuestionOut:
    """Traduce la vista pública de una pregunta al esquema de salida."""
    return QuestionOut(**datos)


def _procedencia_out(trazas) -> list[ProvenanceOut]:
    """Traduce las trazas de `content_provenance` al esquema de salida."""
    return [
        ProvenanceOut(
            chunk_id=t.chunk_id,
            document_id=t.document_id,
            document_version_id=t.document_version_id,
            origin=t.origin,
            retrieval_rank=t.retrieval_rank,
        )
        for t in trazas
    ]


def _actividad_out(abierta: servicio_lecciones.ActividadAbierta) -> ActivityOut:
    """Traduce una actividad abierta al esquema de salida."""
    actividad = abierta.activity
    return ActivityOut(
        activity_id=actividad.id,
        activity_type=actividad.activity_type.value,
        lesson_id=actividad.lesson_id,
        topic_id=actividad.topic_id,
        module_id=actividad.module_id,
        learning_path_id=actividad.learning_path_id,
        knowledge_area_id=actividad.knowledge_area_id,
        started_at=actividad.started_at,
        expires_at=abierta.expires_at,
        questions=[_pregunta_out(q) for q in abierta.questions],
    )


@router.get("/lessons/{lesson_id}", response_model=LessonOut, summary="Lección completa")
def obtener_leccion(lesson_id: uuid.UUID, db: DbSession, user: CurrentUser) -> LessonOut:
    """Bloques, procedencia y preguntas. **Nunca** incluye `answer_key` (§7.6, §8.7)."""
    contenido = servicio_lecciones.obtener_leccion(db, user.id, lesson_id)
    leccion = contenido.lesson
    return LessonOut(
        lesson_id=leccion.id,
        title=leccion.title,
        summary=leccion.summary,
        position=int(leccion.position),
        estimated_seconds=int(leccion.estimated_seconds),
        content_status=leccion.content_status,
        origin=leccion.origin,
        is_low_content=bool(leccion.is_low_content),
        coverage_report=list(leccion.coverage_report or []),
        topic_id=contenido.topic.id,
        topic_title=contenido.topic.title,
        topic_coverage=contenido.topic.coverage,
        module_id=contenido.module_id,
        learning_path_id=contenido.learning_path_id,
        knowledge_area_id=contenido.knowledge_area_id,
        status=contenido.status,
        completion_count=contenido.completion_count,
        blocks=[
            LessonBlockOut(
                block_id=bloque.id,
                position=int(bloque.position),
                block_type=bloque.block_type,
                body=bloque.body,
                payload=dict(bloque.payload or {}),
                origin=bloque.origin,
                is_flagged=bool(bloque.is_flagged),
            )
            for bloque in contenido.blocks
        ],
        provenance=_procedencia_out(contenido.provenance),
        questions_preview=[_pregunta_out(q) for q in contenido.questions_preview],
    )


@router.post(
    "/lessons/{lesson_id}/start",
    response_model=ActivityOut,
    status_code=status.HTTP_201_CREATED,
    summary="Abre la actividad de la lección",
)
def iniciar_leccion(
    lesson_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    idem: IdempotencyDep,
    response: Response,
) -> ActivityOut:
    """Crea la fila de `study_activities` y entrega las preguntas sin claves (§7.6)."""
    abierta = servicio_lecciones.iniciar_leccion(
        db, ServicioConfig(db), user, lesson_id, idempotency_key=idem.require()
    )
    if not abierta.creada:
        response.status_code = status.HTTP_200_OK
    return _actividad_out(abierta)


@router.post(
    "/activities/{activity_id}/answers",
    response_model=AnswerResultOut,
    summary="Envía una respuesta y recibe la corrección",
    # 20 por minuto (§8.7): responder lleva su tiempo, y una respuesta abierta
    # puede acabar en una llamada al juez.
    dependencies=[Depends(freno("20/minute"))],
)
def responder_actividad(
    activity_id: uuid.UUID,
    cuerpo: AnswerIn,
    db: DbSession,
    user: CurrentUser,
    idem: IdempotencyDep,
) -> AnswerResultOut:
    """Corrige (determinista, sandbox o juez), registra la evidencia y paga XP (§7.6)."""
    resultado = servicio_lecciones.responder(
        db,
        ServicioConfig(db),
        user,
        activity_id,
        question_id=cuerpo.question_id,
        response=cuerpo.response,
        response_ms=cuerpo.response_ms,
        hint_used=cuerpo.hint_used,
        idempotency_key=idem.require(),
    )
    intento = resultado.attempt
    return AnswerResultOut(
        attempt_id=intento.id,
        question_id=intento.question_id,
        result=intento.result,
        is_correct=bool(intento.is_correct),
        partial_score=a_float(intento.partial_score),
        attempt_no=int(intento.attempt_no),
        xp_awarded=resultado.xp_awarded,
        explanation=resultado.veredicto.explanation,
        correct_answer=resultado.veredicto.correct_answer,
        provenance=_procedencia_out(resultado.provenance),
        evaluation_method=intento.evaluation_method,
        judge_confidence=resultado.veredicto.judge_confidence,
        context=intento.context,
    )


@router.post(
    "/activities/{activity_id}/heartbeat",
    response_model=HeartbeatOut,
    summary="Latido de tiempo efectivo",
)
def latido_actividad(
    activity_id: uuid.UUID, cuerpo: HeartbeatIn, db: DbSession, user: CurrentUser
) -> HeartbeatOut:
    """Acredita tiempo de dedicación; el tiempo no da XP ni dominio (§1.1)."""
    resultado = servicio_lecciones.latido(
        db, ServicioConfig(db), user, activity_id, cuerpo.seconds
    )
    return HeartbeatOut(
        active_seconds=resultado.active_seconds,
        credited_seconds=resultado.acreditados,
        discarded=resultado.descartado,
        reason=resultado.motivo,
    )


@router.post(
    "/activities/{activity_id}/complete",
    response_model=ReciboRecompensas,
    summary="Cierra la actividad y entrega las recompensas",
)
def completar_actividad(
    activity_id: uuid.UUID, db: DbSession, user: CurrentUser, idem: IdempotencyDep
) -> ReciboRecompensas:
    """Emite el evento de cierre y devuelve el `RewardsReceipt` (§7.6 · P10, §7.10)."""
    return servicio_lecciones.completar(
        db, ServicioConfig(db), user, activity_id, idempotency_key=idem.require()
    )


@router.post(
    "/activities/{activity_id}/abandon",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Abandona la actividad",
)
def abandonar_actividad(activity_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    """Marca la actividad como abandonada, sin recompensa (§7.6)."""
    servicio_lecciones.abandonar(db, user, activity_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/reviews/recommended",
    response_model=Page[ReviewSuggestionOut],
    summary="Repasos recomendados",
)
def repasos_recomendados(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=LIMITE_MAXIMO)] = LIMITE_POR_DEFECTO,
) -> Page[ReviewSuggestionOut]:
    """Temas en riesgo o débiles con su duración estimada (§7.6)."""
    filas = servicio_lecciones.repasos_recomendados(db, ServicioConfig(db), user.id, limite=limit)
    return _pagina([ReviewSuggestionOut.model_validate(f) for f in filas], limit)


@router.post(
    "/reviews/start",
    response_model=ActivityOut,
    status_code=status.HTTP_201_CREATED,
    summary="Abre un repaso de 4–8 preguntas",
)
def iniciar_repaso(
    cuerpo: ReviewStartIn,
    db: DbSession,
    user: CurrentUser,
    idem: IdempotencyDep,
    response: Response,
) -> ActivityOut:
    """Abre la actividad de repaso sobre un tema (§7.6)."""
    abierta = servicio_lecciones.iniciar_repaso(
        db, ServicioConfig(db), user, cuerpo.topic_id, idempotency_key=idem.require()
    )
    if not abierta.creada:
        response.status_code = status.HTTP_200_OK
    return _actividad_out(abierta)


@router.post(
    "/topics/{topic_id}/explain",
    response_model=ExplanationOut,
    summary="Re-explicación alternativa del tema",
)
def reexplicar_tema(
    topic_id: uuid.UUID, cuerpo: ExplanationIn, db: DbSession, user: CurrentUser
) -> ExplanationOut:
    """Pide al módulo `ai` otra explicación del tema, con citas (§7.6).

    Si la capa de IA no está disponible se responde `503 AI_BUDGET_EXCEEDED`: la
    corrección determinista sigue funcionando, que es la garantía de §8.1.

    El puente importaba `app.modules.ai.reexplicacion`, que no existe: la función
    vive en `adaptativo` y se llama `reexplicar`. El `except` lo convertía en un
    503 educado, así que "explícamelo de otra forma" respondía siempre que el
    servicio no estaba disponible, en un servidor perfectamente sano.
    """
    contexto = servicio_modulos.contexto_de_tema(db, user.id, topic_id)
    servicio_modulos.asegurar_desbloqueado(db, user.id, contexto)
    try:  # pragma: no cover - depende de que el módulo `ai` esté construido
        from app.modules.ai import adaptativo  # noqa: PLC0415 - puente opcional
        from app.modules.ai.proveedor import crear_proveedor  # noqa: PLC0415
    except ImportError as exc:
        raise AteneaError(code="AI_BUDGET_EXCEEDED", details={"topic_id": str(topic_id)}) from exc

    cfg = ServicioConfig(db)
    # `approach` es opcional: cuando no viene, el módulo elige el enfoque que
    # todavía no se ha probado con este aprendiz.
    decision = (
        adaptativo.Decision(topic_id=topic_id, accion="reexplain", approach=cuerpo.approach)
        if cuerpo.approach
        else None
    )
    resultado = adaptativo.reexplicar(
        db,
        cfg,
        crear_proveedor(cfg=cfg),
        topic_id=topic_id,
        usuario_id=user.id,
        decision=decision,
    )
    return ExplanationOut.model_validate(resultado.como_dict())


@router.post(
    "/content/report",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reporta un bloque o una pregunta",
)
def reportar_contenido(
    cuerpo: ContentReportIn, db: DbSession, user: CurrentUser
) -> Response:
    """Marca el contenido como reportado y emite `CONTENT_REPORTED` (§7.6, §4.2).

    Dos guardas que antes no había, y que juntas cerraban un agujero grande.

    La primera es de propiedad: solo se puede reportar contenido al que se tiene
    acceso. Sin ella, cualquier cuenta recién registrada podía enumerar las
    preguntas de una Ruta del Reino, que es la misma para todo el mundo, y
    dejarlas marcadas una a una: el filtro de exclusión es global, así que el
    Reino entero se quedaba sin preguntas.

    La segunda es de umbral. En el material propio, un reporte basta: es del
    aprendiz y nadie más lo ve. En una Ruta compartida hacen falta varios
    reportes de **personas distintas** antes de retirar nada, porque retirarlo
    afecta a todos. Que sean personas distintas lo garantiza la clave de
    idempotencia, que ya no lleva la hora: reportar dos veces lo mismo cuenta una.
    """
    clave = f"content-reported:{user.id}:{cuerpo.content_id}"
    ya_reportado = buscar_por_clave(db, clave) is not None

    if cuerpo.content_type == "question":
        pregunta = db.get(Question, cuerpo.content_id)
        if pregunta is None:
            raise NotFound()
        compartido = _es_contenido_compartido(db, pregunta.topic_id)
        _asegurar_acceso_al_tema(db, user.id, pregunta.topic_id)
        if not ya_reportado:
            pregunta.is_flagged = True
            pregunta.flag_reason = cuerpo.reason
            pregunta.flag_count = int(pregunta.flag_count) + 1
            umbral = settings.content_flag_threshold if compartido else 1
            if int(pregunta.flag_count) >= umbral:
                pregunta.content_status = ContentStatus.FLAGGED
        contenido_tipo = ProvenanceContentType.QUESTION
    else:
        bloque = db.get(LessonBlock, cuerpo.content_id)
        if bloque is None:
            raise NotFound()
        leccion = db.get(Lesson, bloque.lesson_id)
        if leccion is None:
            raise NotFound()
        _asegurar_acceso_al_tema(db, user.id, leccion.topic_id)
        if not ya_reportado:
            bloque.is_flagged = True
            bloque.flag_reason = cuerpo.reason
        contenido_tipo = ProvenanceContentType.LESSON_BLOCK
    db.flush()

    registrar_evento(
        db,
        usuario_id=user.id,
        tipo=EventType.CONTENT_REPORTED,
        payload={
            "content_type": cuerpo.content_type,
            "content_id": str(cuerpo.content_id),
            "reason": cuerpo.reason,
            "comment": cuerpo.comment or "",
            "provenance_type": contenido_tipo.value,
        },
        idempotency_key=clave,
        source_module="content",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _ruta_del_tema(db: Session, topic_id: uuid.UUID | None) -> LearningPath | None:
    """Ruta a la que pertenece un tema, subiendo por su módulo."""
    if topic_id is None:
        return None
    return db.execute(
        sa.select(LearningPath)
        .join(PathModule, PathModule.learning_path_id == LearningPath.id)
        .join(Topic, Topic.module_id == PathModule.id)
        .where(Topic.id == topic_id)
    ).scalar_one_or_none()


def _es_contenido_compartido(db: Session, topic_id: uuid.UUID | None) -> bool:
    """¿El tema vive en una Ruta del Reino, que ven todos los aprendices?

    Una Ruta del Reino no tiene dueño (`user_id` nulo): es la misma fila para
    todo el mundo, así que marcar una de sus preguntas se la quita a todos.
    """
    ruta = _ruta_del_tema(db, topic_id)
    return bool(ruta is not None and ruta.user_id is None)


def _asegurar_acceso_al_tema(db: Session, usuario_id: uuid.UUID, topic_id: uuid.UUID | None) -> None:
    """Exige que el aprendiz pueda ver ese contenido; si no, 404 (§8.7).

    Se responde 404 y no 403 a propósito: decir "no puedes" confirma que existe.
    """
    ruta = _ruta_del_tema(db, topic_id)
    if ruta is None:
        raise NotFound()
    if ruta.user_id == usuario_id:
        return
    if ruta.user_id is None:
        adoptada = db.execute(
            sa.select(UserPathProgress.id).where(
                UserPathProgress.user_id == usuario_id,
                UserPathProgress.learning_path_id == ruta.id,
            )
        ).scalar_one_or_none()
        if adoptada is not None:
            return
    raise NotFound()


# ---------------------------------------------------------------------------
# §7.7 · Evaluación de módulo
# ---------------------------------------------------------------------------


@router.get(
    "/modules/{module_id}/assessment",
    response_model=AssessmentInfoOut,
    summary="Pantalla de entrada de la prueba del módulo",
)
def obtener_info_evaluacion(
    module_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> AssessmentInfoOut:
    """Reglas, recompensa, intentos usados y enfriamiento (§7.7 · P11)."""
    info = servicio_evaluaciones.info_evaluacion(db, ServicioConfig(db), user, module_id)
    return AssessmentInfoOut(
        assessment=AssessmentBriefOut(
            assessment_id=info.assessment.id,
            module_id=info.assessment.module_id,
            title=info.assessment.title,
            question_count=info.question_count,
            pass_score=info.pass_score,
            max_attempts_per_day=info.max_attempts_per_day,
            content_status=info.assessment.content_status,
        ),
        module_title=info.module.flavor_name or info.module.title,
        attempts_used=info.attempts_used,
        attempts_total=info.attempts_total,
        cooldown_until=info.cooldown_until,
        can_start=info.can_start,
        blocked_reason=info.blocked_reason,
        best_score=info.best_score,
        best_effective=info.best_effective,
        passed_at=info.passed_at,
        reward_preview=info.reward_preview,
    )


@router.post(
    "/assessments/{assessment_id}/start",
    response_model=AssessmentAttemptOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crea el intento y muestrea el banco",
)
def iniciar_evaluacion(
    assessment_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    idem: IdempotencyDep,
    response: Response,
) -> AssessmentAttemptOut:
    """Muestreo con solapamiento ≤ 30 % respecto del intento anterior (§7.7)."""
    abierto = servicio_evaluaciones.iniciar_intento(
        db, ServicioConfig(db), user, assessment_id, idempotency_key=idem.require()
    )
    if not abierto.creado:
        response.status_code = status.HTTP_200_OK
    intento = abierto.attempt
    return AssessmentAttemptOut(
        attempt_id=intento.id,
        assessment_id=intento.assessment_id,
        module_id=intento.module_id,
        attempt_no=int(intento.attempt_no),
        question_count=int(intento.question_count),
        started_at=intento.started_at,
        questions=[_pregunta_out(q) for q in abierto.questions],
    )


@router.post(
    "/assessment-attempts/{attempt_id}/answers",
    response_model=AssessmentAnswerOut,
    summary="Registra una respuesta del examen",
)
def responder_evaluacion(
    attempt_id: uuid.UUID,
    cuerpo: AssessmentAnswerIn,
    db: DbSession,
    user: CurrentUser,
    idem: IdempotencyDep,
) -> AssessmentAnswerOut:
    """Feedback mínimo: correcto/incorrecto, sin explicación (§7.7)."""
    resultado = servicio_evaluaciones.registrar_respuesta(
        db,
        ServicioConfig(db),
        user,
        attempt_id,
        question_id=cuerpo.question_id,
        response=cuerpo.response,
        response_ms=cuerpo.response_ms,
        idempotency_key=idem.require(),
    )
    return AssessmentAnswerOut.model_validate(resultado)


@router.post(
    "/assessment-attempts/{attempt_id}/submit",
    response_model=ReciboRecompensas,
    summary="Cierra el intento y calcula puntaje y dominio",
)
def enviar_evaluacion(
    attempt_id: uuid.UUID, db: DbSession, user: CurrentUser, idem: IdempotencyDep
) -> ReciboRecompensas:
    """Devuelve el `RewardsReceipt` con `assessment_result` (§7.7 · P12, §7.10)."""
    return servicio_evaluaciones.enviar_intento(
        db, ServicioConfig(db), user, attempt_id, idempotency_key=idem.require()
    )


@router.get(
    "/assessment-attempts/{attempt_id}",
    response_model=AssessmentReviewOut,
    summary="Revisión del intento con explicación y fuente",
)
def revisar_evaluacion(
    attempt_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> AssessmentReviewOut:
    """Respuestas, explicación y procedencia de cada pregunta (§7.7)."""
    revision = servicio_evaluaciones.revision_intento(db, user, attempt_id)
    intento = revision.attempt
    return AssessmentReviewOut(
        attempt_id=intento.id,
        assessment_id=intento.assessment_id,
        module_id=intento.module_id,
        attempt_no=int(intento.attempt_no),
        status=intento.status.value,
        score_pct=a_float(intento.score) if intento.score is not None else None,
        effective_score_pct=(
            a_float(intento.effective_score) if intento.effective_score is not None else None
        ),
        outcome=intento.outcome,
        correct_count=int(intento.correct_count),
        question_count=int(intento.question_count),
        submitted_at=intento.submitted_at,
        cooldown_until=intento.cooldown_until,
        per_topic=list(intento.per_topic_scores or []),
        items=revision.items,
    )


__all__ = ["router"]
