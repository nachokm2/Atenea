"""Lección, actividad de estudio, respuestas, latidos y cierre (§7.6).

Contrato §3.2, §3.4 (`study_activities`, `question_attempts`), §4.2 (`LESSON_STARTED`,
`QUESTION_ANSWERED`, `LESSON_COMPLETED`, `REVIEW_COMPLETED`), §6.9 (A1–A8) y §7.10.

Este es el ciclo caliente del producto:

```
GET  /lessons/{id}                  → contenido, nunca `answer_key`
POST /lessons/{id}/start            → abre `study_activities` y entrega las preguntas
POST /activities/{id}/answers       → corrige, registra evidencia y emite QUESTION_ANSWERED
POST /activities/{id}/heartbeat     → tiempo efectivo (no da XP ni dominio)
POST /activities/{id}/complete      → emite LESSON_COMPLETED y devuelve el RewardsReceipt
```

Reglas duras que este archivo hace cumplir:

* **A2** — una respuesta solo cuenta dentro de una actividad abierta y no vencida
  (`xp.attempt_ttl_hours`), y sobre una pregunta que pertenece a esa actividad; si no,
  `409 ATTEMPT_NOT_OPEN`. Una pregunta ya acertada en el intento da `409 ALREADY_ANSWERED`;
  una fallada sí admite revancha y sube `attempt_no` (que es lo que pesa `mastery.weight.retake`).
* **A6** — idempotencia real: `question_attempts` y `study_activities` llevan
  `UNIQUE (user_id, idempotency_key)`, y el recibo lo reconstruye el motor a partir
  de `domain_events.idempotency_key`. Repetir la petición no otorga nada nuevo.
* **A7** — `LESSON_COMPLETED` solo se emite si **todas** las preguntas del intento
  tienen respuesta registrada (una omisión también es una respuesta: `SKIPPED`).
* **Ningún importe se calcula aquí.** XP, oro, nivel, racha, misiones y logros los
  produce `registrar_evento`; este archivo solo transporta hechos verificados.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import AteneaError, NotFound
from app.core.time import ensure_utc, user_local_date, utcnow
from app.models.content import Lesson, LessonBlock, Question, Topic
from app.models.enums import (
    ActivityContext,
    AttemptResult,
    AttemptStatus,
    ContentStatus,
    EventType,
    KnowledgeAreaStatus,
    ProgressState,
    StudyActivityType,
)
from app.models.ingestion import ContentProvenance
from app.models.progress import (
    QuestionAttempt,
    StudyActivity,
    UserLessonProgress,
    UserTopicProgress,
)
from app.modules.content import correccion, modulos, preguntas
from app.modules.gamification.eventos import buscar_por_clave, reconstruir_recibo, registrar_evento
from app.modules.gamification.recompensas import ReciboRecompensas
from app.modules.gamification.servicio_config import ServicioConfig
from app.modules.progress import a_float
from app.modules.progress.dominio import ServicioDominio
from app.modules.progress.progreso import ServicioProgreso
from app.modules.progress.sesiones import ServicioSesiones

#: Contexto de `question_attempts` según el tipo de actividad (§3.4, peso de §6.4).
CONTEXTO_POR_ACTIVIDAD: dict[StudyActivityType, ActivityContext] = {
    StudyActivityType.LESSON: ActivityContext.LESSON,
    StudyActivityType.PRACTICE: ActivityContext.PRACTICE,
    StudyActivityType.REVIEW: ActivityContext.REVIEW,
    StudyActivityType.CHALLENGE: ActivityContext.CHALLENGE,
    StudyActivityType.ASSESSMENT: ActivityContext.ASSESSMENT,
}

#: Evento de cierre según el tipo de actividad (§4.2 · Aprendizaje).
EVENTO_DE_CIERRE: dict[StudyActivityType, EventType] = {
    StudyActivityType.LESSON: EventType.LESSON_COMPLETED,
    StudyActivityType.PRACTICE: EventType.LESSON_COMPLETED,
    StudyActivityType.REVIEW: EventType.REVIEW_COMPLETED,
    StudyActivityType.CHALLENGE: EventType.CHALLENGE_COMPLETED,
}


@dataclass(slots=True)
class ContenidoLeccion:
    """Lo que devuelve `GET /lessons/{id}`: bloques, procedencia y preguntas sin clave."""

    lesson: Lesson
    topic: Topic
    blocks: list[LessonBlock]
    provenance: list[ContentProvenance]
    questions_preview: list[dict[str, Any]]
    module_id: uuid.UUID
    learning_path_id: uuid.UUID
    knowledge_area_id: uuid.UUID
    status: ProgressState
    completion_count: int


@dataclass(slots=True)
class ActividadAbierta:
    """Actividad recién abierta con sus preguntas públicas (§7.6 `ActivityOut`)."""

    activity: StudyActivity
    questions: list[dict[str, Any]]
    expires_at: datetime
    creada: bool = True


@dataclass(slots=True)
class ResultadoRespuesta:
    """Lo que devuelve `POST /activities/{id}/answers` (§7.6 `AnswerResultOut`)."""

    attempt: QuestionAttempt
    veredicto: correccion.ResultadoCorreccion
    xp_awarded: int
    receipt: ReciboRecompensas
    provenance: list[ContentProvenance] = field(default_factory=list)


@dataclass(slots=True)
class SugerenciaRepaso:
    """Un repaso recomendado (§7.6 `ReviewSuggestionOut`)."""

    topic_id: uuid.UUID
    title: str
    module_id: uuid.UUID
    knowledge_area_id: uuid.UUID
    mastery: float
    status: KnowledgeAreaStatus
    is_weak: bool
    question_count: int
    estimated_seconds: int


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------


def _ttl(cfg: ServicioConfig) -> timedelta:
    """Vida de una actividad abierta (`xp.attempt_ttl_hours`, §6.9 A2)."""
    return timedelta(hours=cfg.obtener_int("xp.attempt_ttl_hours"))


def _actividad_del_usuario(db: Session, usuario_id: uuid.UUID, activity_id: uuid.UUID) -> StudyActivity:
    """Carga una actividad propia; las ajenas responden `404` (§8.7)."""
    actividad = db.get(StudyActivity, activity_id)
    if actividad is None or actividad.user_id != usuario_id:
        raise NotFound()
    return actividad


def _asegurar_abierta(
    db: Session, cfg: ServicioConfig, actividad: StudyActivity, *, momento: datetime
) -> None:
    """Exige actividad en curso y dentro del TTL; si no, `409 ATTEMPT_NOT_OPEN` (A2)."""
    if actividad.status != AttemptStatus.IN_PROGRESS:
        raise AteneaError(code="ATTEMPT_NOT_OPEN", details={"status": actividad.status.value})
    if momento - ensure_utc(actividad.started_at) > _ttl(cfg):
        actividad.status = AttemptStatus.EXPIRED
        db.flush()
        raise AteneaError(code="ATTEMPT_NOT_OPEN", details={"status": AttemptStatus.EXPIRED.value})


def procedencia(
    db: Session, *, content_type, content_ids: list[uuid.UUID]
) -> list[ContentProvenance]:
    """Trazas de `content_provenance` de un conjunto de contenidos (§3.3)."""
    if not content_ids:
        return []
    return list(
        db.execute(
            sa.select(ContentProvenance)
            .where(
                ContentProvenance.content_type == content_type,
                ContentProvenance.content_id.in_(content_ids),
            )
            .order_by(ContentProvenance.retrieval_rank.nullslast(), ContentProvenance.id)
        ).scalars()
    )


def fusionar_recibos(principal: ReciboRecompensas, extra: ReciboRecompensas) -> ReciboRecompensas:
    """Funde el recibo de un evento derivado dentro del recibo principal (§7.10).

    Completar una lección puede cerrar el módulo y la ruta en la misma petición: el
    cliente debe recibir **un** recibo con todo, no tres. Los importes se suman y los
    estados posteriores (`total_after`, `balance_after`) se quedan con el último.
    """
    if extra.xp is not None and extra.xp.amount:
        if principal.xp is None:
            principal.xp = extra.xp
        else:
            principal.xp.amount += extra.xp.amount
            principal.xp.base_amount += extra.xp.base_amount
            principal.xp.activity_xp += extra.xp.activity_xp
            principal.xp.question_xp += extra.xp.question_xp
            principal.xp.total_after = max(principal.xp.total_after, extra.xp.total_after)
    if extra.gold is not None and extra.gold.amount:
        if principal.gold is None:
            principal.gold = extra.gold
        else:
            principal.gold.amount += extra.gold.amount
            if extra.gold.balance_after is not None:
                principal.gold.balance_after = extra.gold.balance_after
    if extra.level is not None and extra.level.leveled_up:
        principal.level = extra.level
    if principal.knowledge is None:
        principal.knowledge = extra.knowledge
    if principal.streak is None:
        principal.streak = extra.streak
    if principal.daily_goal is None:
        principal.daily_goal = extra.daily_goal

    vistos_mision = {m.user_mission_id for m in principal.missions}
    principal.missions.extend(m for m in extra.missions if m.user_mission_id not in vistos_mision)
    vistos_logro = {(logro.code, logro.tier) for logro in principal.achievements}
    principal.achievements.extend(
        logro for logro in extra.achievements if (logro.code, logro.tier) not in vistos_logro
    )
    vistos_item = {i.item_code for i in principal.items}
    principal.items.extend(i for i in extra.items if i.item_code not in vistos_item)
    vistos_unlock = {(u.type, str(u.id)) for u in principal.unlocks}
    principal.unlocks.extend(
        u for u in extra.unlocks if (u.type, str(u.id)) not in vistos_unlock
    )
    vistos_delta = {(d.scope, str(d.id)) for d in principal.mastery_deltas}
    principal.mastery_deltas.extend(
        d for d in extra.mastery_deltas if (d.scope, str(d.id)) not in vistos_delta
    )
    principal.pending_sync = principal.pending_sync or extra.pending_sync
    return principal.finalizar()


# ---------------------------------------------------------------------------
# GET /lessons/{id}
# ---------------------------------------------------------------------------


def obtener_leccion(db: Session, usuario_id: uuid.UUID, lesson_id: uuid.UUID) -> ContenidoLeccion:
    """Lección completa con bloques y procedencia. **Nunca** incluye `answer_key` (§7.6)."""
    contexto = modulos.contexto_de_leccion(db, usuario_id, lesson_id)
    modulos.asegurar_desbloqueado(db, usuario_id, contexto)
    leccion = contexto.lesson
    modulos.asegurar_contenido_listo(leccion.content_status, target_id=leccion.id)

    bloques = list(
        db.execute(
            sa.select(LessonBlock)
            .where(LessonBlock.lesson_id == leccion.id)
            .order_by(LessonBlock.position)
        ).scalars()
    )
    pool = preguntas.preguntas_de_leccion(db, leccion.id)
    avance = db.execute(
        sa.select(UserLessonProgress).where(
            UserLessonProgress.user_id == usuario_id,
            UserLessonProgress.lesson_id == leccion.id,
        )
    ).scalar_one_or_none()

    from app.models.enums import ProvenanceContentType  # noqa: PLC0415 - solo aquí

    return ContenidoLeccion(
        lesson=leccion,
        topic=contexto.topic,
        blocks=bloques,
        provenance=procedencia(
            db,
            content_type=ProvenanceContentType.LESSON,
            content_ids=[leccion.id],
        ),
        questions_preview=[
            preguntas.vista_publica(q, position=i) for i, q in enumerate(pool, start=1)
        ],
        module_id=contexto.module.id,
        learning_path_id=contexto.path.id,
        knowledge_area_id=contexto.knowledge_area_id,
        status=avance.status if avance else ProgressState.NOT_STARTED,
        completion_count=int(avance.completion_count) if avance else 0,
    )


# ---------------------------------------------------------------------------
# POST /lessons/{id}/start  ·  POST /reviews/start
# ---------------------------------------------------------------------------


def _actividad_por_clave(
    db: Session,
    cfg: ServicioConfig,
    usuario_id: uuid.UUID,
    idempotency_key: str,
    *,
    momento: datetime,
) -> StudyActivity | None:
    """Actividad **reutilizable** con esa `Idempotency-Key` (§8.3, única por usuario).

    La idempotencia protege del doble toque y del reintento de red: si la misma
    clave llega dos veces mientras la actividad sigue viva, se devuelve la misma
    y no se abre otra. Lo que no puede hacer es resucitar un cadáver.

    La app deriva la clave de la lección, así que es la misma de por vida. Cuando
    se devolvía la actividad existente sin mirar su estado, abandonar una lección
    y volver al día siguiente entregaba la actividad caducada: el aprendiz veía
    las preguntas, respondía, y el servidor contestaba `409 ATTEMPT_NOT_OPEN`.
    Desde ese momento la lección quedaba muerta, porque cada intento devolvía el
    mismo cadáver. Con el repaso era peor: repetir un tema es justo su razón de
    ser, y el segundo repaso devolvía siempre el primero.

    Una actividad que ya no sirve se aparta: se le retira la clave (que pasa a
    llevar su propio identificador) para que la unicidad siga valiendo y la
    siguiente apertura empiece de cero.
    """
    actividad = db.execute(
        sa.select(StudyActivity).where(
            StudyActivity.user_id == usuario_id,
            StudyActivity.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()
    if actividad is None:
        return None

    viva = actividad.status == AttemptStatus.IN_PROGRESS and (
        momento - ensure_utc(actividad.started_at) <= _ttl(cfg)
    )
    if viva:
        return actividad

    if actividad.status == AttemptStatus.IN_PROGRESS:
        actividad.status = AttemptStatus.EXPIRED
    actividad.idempotency_key = _clave_retirada(idempotency_key, actividad.id)
    db.flush()
    return None


def _clave_retirada(clave: str, actividad_id: uuid.UUID) -> str:
    """Clave apartada de una actividad agotada, dentro de los 120 caracteres."""
    sufijo = f"#{actividad_id}"
    return f"{clave[: 120 - len(sufijo)]}{sufijo}"


def _preguntas_de_actividad(
    db: Session, cfg: ServicioConfig, actividad: StudyActivity
) -> list[Question]:
    """Preguntas presentadas en la actividad, en el orden en que se sirvieron.

    `study_activities` no guarda la lista (§3.4 no tiene esa columna), así que el
    conjunto se **reconstruye**: la lección entrega sus preguntas intercaladas y el
    repaso repite el muestreo con la misma semilla determinista (la propia
    `idempotency_key` de la actividad), de modo que siempre salen las mismas.
    """
    if actividad.activity_type == StudyActivityType.LESSON and actividad.lesson_id:
        return preguntas.preguntas_de_leccion(db, actividad.lesson_id)
    if actividad.activity_type == StudyActivityType.REVIEW and actividad.topic_id:
        return preguntas.muestrear_repaso(
            db,
            cfg,
            actividad.topic_id,
            semilla=f"{actividad.user_id}:{actividad.topic_id}:{actividad.idempotency_key}",
        )
    if actividad.topic_id:
        return preguntas.preguntas_de_tema(db, actividad.topic_id)
    return []


def iniciar_leccion(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    lesson_id: uuid.UUID,
    *,
    idempotency_key: str,
    device: str | None = None,
    momento: datetime | None = None,
) -> ActividadAbierta:
    """Abre la actividad de una lección y entrega las preguntas **sin claves** (§7.6)."""
    instante = ensure_utc(momento) if momento else utcnow()
    existente = _actividad_por_clave(db, cfg, usuario.id, idempotency_key, momento=instante)
    if existente is not None:
        pool = _preguntas_de_actividad(db, cfg, existente)
        return ActividadAbierta(
            activity=existente,
            questions=[preguntas.vista_publica(q, position=i) for i, q in enumerate(pool, start=1)],
            expires_at=ensure_utc(existente.started_at) + _ttl(cfg),
            creada=False,
        )

    contexto = modulos.contexto_de_leccion(db, usuario.id, lesson_id)
    modulos.asegurar_desbloqueado(db, usuario.id, contexto)
    modulos.asegurar_contenido_listo(contexto.lesson.content_status, target_id=lesson_id)

    sesiones = ServicioSesiones(db)
    sesion = sesiones.abrir_sesion(usuario.id, usuario.timezone, device=device, ahora=instante)

    actividad = StudyActivity(
        user_id=usuario.id,
        session_id=sesion.id,
        activity_type=StudyActivityType.LESSON,
        status=AttemptStatus.IN_PROGRESS,
        lesson_id=lesson_id,
        topic_id=contexto.topic.id,
        module_id=contexto.module.id,
        learning_path_id=contexto.path.id,
        knowledge_area_id=contexto.knowledge_area_id,
        started_at=instante,
        local_date=user_local_date(instante, usuario.timezone),
        idempotency_key=idempotency_key,
    )
    db.add(actividad)
    db.flush()

    progreso = ServicioProgreso(db)
    avance_previo = db.execute(
        sa.select(sa.func.count(UserLessonProgress.id)).where(
            UserLessonProgress.user_id == usuario.id,
            UserLessonProgress.topic_id == contexto.topic.id,
        )
    ).scalar_one()
    progreso.iniciar_leccion(usuario.id, lesson_id, ahora=instante)

    pool = preguntas.preguntas_de_leccion(db, lesson_id)
    actividad.questions_total = len(pool)
    db.flush()

    if not avance_previo:
        registrar_evento(
            db,
            usuario_id=usuario.id,
            tipo=EventType.TOPIC_STARTED,
            payload={
                "topic_id": str(contexto.topic.id),
                "module_id": str(contexto.module.id),
                "path_id": str(contexto.path.id),
                "knowledge_area_id": str(contexto.knowledge_area_id),
            },
            idempotency_key=f"topic-started:{usuario.id}:{contexto.topic.id}:1",
            occurred_at=instante,
            timezone=usuario.timezone,
            cfg=cfg,
        )
    registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=EventType.LESSON_STARTED,
        payload={
            "lesson_id": str(lesson_id),
            "study_activity_id": str(actividad.id),
            "topic_id": str(contexto.topic.id),
        },
        idempotency_key=f"lesson-started:{usuario.id}:{actividad.id}:1",
        occurred_at=instante,
        timezone=usuario.timezone,
        cfg=cfg,
    )

    return ActividadAbierta(
        activity=actividad,
        questions=[preguntas.vista_publica(q, position=i) for i, q in enumerate(pool, start=1)],
        expires_at=instante + _ttl(cfg),
    )


def iniciar_repaso(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    topic_id: uuid.UUID,
    *,
    idempotency_key: str,
    device: str | None = None,
    momento: datetime | None = None,
) -> ActividadAbierta:
    """Abre un repaso de 4–8 preguntas sobre un tema (§7.6, `mastery.review.questions`)."""
    instante = ensure_utc(momento) if momento else utcnow()
    existente = _actividad_por_clave(db, cfg, usuario.id, idempotency_key, momento=instante)
    if existente is not None:
        pool = _preguntas_de_actividad(db, cfg, existente)
        return ActividadAbierta(
            activity=existente,
            questions=[preguntas.vista_publica(q, position=i) for i, q in enumerate(pool, start=1)],
            expires_at=ensure_utc(existente.started_at) + _ttl(cfg),
            creada=False,
        )

    contexto = modulos.contexto_de_tema(db, usuario.id, topic_id)
    modulos.asegurar_desbloqueado(db, usuario.id, contexto)

    seleccion = preguntas.muestrear_repaso(
        db, cfg, topic_id, semilla=f"{usuario.id}:{topic_id}:{idempotency_key}"
    )
    if not seleccion:
        raise AteneaError(
            code="CONTENT_NOT_READY",
            details={"topic_id": str(topic_id), "reason": "empty_question_pool"},
        )

    sesiones = ServicioSesiones(db)
    sesion = sesiones.abrir_sesion(usuario.id, usuario.timezone, device=device, ahora=instante)
    actividad = StudyActivity(
        user_id=usuario.id,
        session_id=sesion.id,
        activity_type=StudyActivityType.REVIEW,
        status=AttemptStatus.IN_PROGRESS,
        topic_id=topic_id,
        module_id=contexto.module.id,
        learning_path_id=contexto.path.id,
        knowledge_area_id=contexto.knowledge_area_id,
        started_at=instante,
        questions_total=len(seleccion),
        local_date=user_local_date(instante, usuario.timezone),
        idempotency_key=idempotency_key,
    )
    db.add(actividad)
    db.flush()
    return ActividadAbierta(
        activity=actividad,
        questions=[preguntas.vista_publica(q, position=i) for i, q in enumerate(seleccion, start=1)],
        expires_at=instante + _ttl(cfg),
    )


# ---------------------------------------------------------------------------
# POST /activities/{id}/answers
# ---------------------------------------------------------------------------


def _intento_por_clave(
    db: Session, usuario_id: uuid.UUID, idempotency_key: str
) -> QuestionAttempt | None:
    """Evidencia ya registrada con esa clave (§8.3)."""
    return db.execute(
        sa.select(QuestionAttempt).where(
            QuestionAttempt.user_id == usuario_id,
            QuestionAttempt.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()


def _intentos_previos(
    db: Session, usuario_id: uuid.UUID, actividad_id: uuid.UUID, question_id: uuid.UUID
) -> list[QuestionAttempt]:
    """Respuestas anteriores a esa pregunta **dentro de la misma actividad** (A2)."""
    return list(
        db.execute(
            sa.select(QuestionAttempt)
            .where(
                QuestionAttempt.user_id == usuario_id,
                QuestionAttempt.study_activity_id == actividad_id,
                QuestionAttempt.question_id == question_id,
            )
            .order_by(QuestionAttempt.attempt_no)
        ).scalars()
    )


def responder(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    activity_id: uuid.UUID,
    *,
    question_id: uuid.UUID,
    response: Any,
    response_ms: int = 0,
    hint_used: bool = False,
    idempotency_key: str,
    momento: datetime | None = None,
) -> ResultadoRespuesta:
    """Corrige una respuesta, registra la evidencia y emite `QUESTION_ANSWERED` (§7.6).

    El veredicto es determinista para los cinco tipos cerrados; las abiertas van al
    juez de IA y los ejercicios de SQL al sandbox (`correccion.corregir`).
    """
    instante = ensure_utc(momento) if momento else utcnow()
    actividad = _actividad_del_usuario(db, usuario.id, activity_id)

    repetida = _intento_por_clave(db, usuario.id, idempotency_key)
    if repetida is not None:
        pregunta_previa = db.get(Question, repetida.question_id)
        return ResultadoRespuesta(
            attempt=repetida,
            veredicto=correccion.ResultadoCorreccion(
                result=repetida.result,
                is_correct=bool(repetida.is_correct),
                partial_score=a_float(repetida.partial_score),
                correctness_weight=a_float(repetida.correctness_weight),
                evaluation_method=repetida.evaluation_method,
                correct_answer=None,
                explanation=pregunta_previa.explanation if pregunta_previa else None,
                judge_confidence=a_float(repetida.judge_confidence, 0.0) or None,
                judge_payload=dict(repetida.judge_payload or {}),
                counts_for_mastery=bool(repetida.counts_for_mastery),
            ),
            xp_awarded=int(repetida.xp_awarded),
            receipt=_recibo_de_respuesta(db, cfg, usuario, repetida, actividad, instante),
        )

    _asegurar_abierta(db, cfg, actividad, momento=instante)

    permitidas = {q.id: q for q in _preguntas_de_actividad(db, cfg, actividad)}
    pregunta = permitidas.get(question_id)
    if pregunta is None:
        raise AteneaError(
            code="ATTEMPT_NOT_OPEN",
            details={"question_id": str(question_id), "reason": "question_not_in_activity"},
        )

    previos = _intentos_previos(db, usuario.id, actividad.id, question_id)
    if any(p.is_correct for p in previos):
        raise AteneaError(code="ALREADY_ANSWERED", details={"question_id": str(question_id)})
    attempt_no = len(previos) + 1

    veredicto = correccion.corregir(
        cfg,
        pregunta,
        response,
        attempt_no=attempt_no,
        db=db,
        usuario_id=usuario.id,
        activity_id=actividad.id,
    )
    contexto_evidencia = CONTEXTO_POR_ACTIVIDAD[actividad.activity_type]
    tiempo_minimo_ms = cfg.obtener_int("xp.min_time.answer_ms")
    demasiado_rapida = 0 < int(response_ms) < tiempo_minimo_ms
    cuenta_para_progreso = not demasiado_rapida and veredicto.result != AttemptResult.SKIPPED

    intento = QuestionAttempt(
        user_id=usuario.id,
        question_id=pregunta.id,
        topic_id=pregunta.topic_id,
        knowledge_area_id=actividad.knowledge_area_id,
        study_activity_id=actividad.id,
        context=contexto_evidencia,
        attempt_no=attempt_no,
        response=response if isinstance(response, dict) else {"value": response},
        result=veredicto.result,
        is_correct=veredicto.is_correct,
        partial_score=Decimal(str(round(veredicto.partial_score, 2))),
        correctness_weight=Decimal(str(round(veredicto.correctness_weight, 2))),
        difficulty=pregunta.difficulty,
        evaluation_method=veredicto.evaluation_method,
        judge_confidence=(
            Decimal(str(round(veredicto.judge_confidence, 2)))
            if veredicto.judge_confidence is not None
            else None
        ),
        judge_payload=dict(veredicto.judge_payload or {}),
        response_ms=max(0, int(response_ms)),
        hint_used=bool(hint_used),
        is_retry_of_failed=attempt_no > 1,
        counts_for_progress=cuenta_para_progreso,
        counts_for_mastery=veredicto.counts_for_mastery,
        answered_at=instante,
        local_date=user_local_date(instante, usuario.timezone),
        idempotency_key=idempotency_key,
    )
    db.add(intento)
    db.flush()

    if attempt_no == 1:
        actividad.questions_total = max(int(actividad.questions_total), len(permitidas))
    if veredicto.is_correct and not any(p.is_correct for p in previos):
        actividad.questions_correct = int(actividad.questions_correct) + 1
    if actividad.questions_total:
        actividad.accuracy_pct = Decimal(
            str(round(100.0 * int(actividad.questions_correct) / int(actividad.questions_total), 2))
        )
    db.flush()

    recibo = _recibo_de_respuesta(db, cfg, usuario, intento, actividad, instante)
    intento.xp_awarded = int(recibo.xp.amount) if recibo.xp else 0
    db.flush()

    from app.models.enums import ProvenanceContentType  # noqa: PLC0415 - solo aquí

    return ResultadoRespuesta(
        attempt=intento,
        veredicto=veredicto,
        xp_awarded=int(intento.xp_awarded),
        receipt=recibo,
        provenance=procedencia(
            db, content_type=ProvenanceContentType.QUESTION, content_ids=[pregunta.id]
        ),
    )


def _recibo_de_respuesta(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    intento: QuestionAttempt,
    actividad: StudyActivity,
    momento: datetime,
) -> ReciboRecompensas:
    """Emite `QUESTION_ANSWERED` y devuelve el recibo (idempotente por la clave)."""
    return registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=EventType.QUESTION_ANSWERED,
        payload={
            "question_id": str(intento.question_id),
            "topic_id": str(intento.topic_id),
            "knowledge_area_id": (
                str(intento.knowledge_area_id) if intento.knowledge_area_id else None
            ),
            "lesson_id": str(actividad.lesson_id) if actividad.lesson_id else None,
            "study_activity_id": str(actividad.id),
            "assessment_attempt_id": (
                str(intento.assessment_attempt_id) if intento.assessment_attempt_id else None
            ),
            "context": intento.context.value,
            "attempt_no": int(intento.attempt_no),
            "is_correct": bool(intento.is_correct),
            "partial_score": a_float(intento.partial_score),
            "difficulty": intento.difficulty.value,
            "evaluation_method": intento.evaluation_method.value,
            "response_ms": int(intento.response_ms),
            "is_retry_of_failed": bool(intento.is_retry_of_failed),
            "counts_for_progress": bool(intento.counts_for_progress),
        },
        idempotency_key=f"question-answered:{usuario.id}:{intento.id}:1",
        occurred_at=momento,
        timezone=usuario.timezone,
        cfg=cfg,
    )


# ---------------------------------------------------------------------------
# Latido y abandono
# ---------------------------------------------------------------------------


def latido(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    activity_id: uuid.UUID,
    segundos: int,
    *,
    momento: datetime | None = None,
):
    """Acredita tiempo efectivo sobre la actividad (§7.6; el tiempo no da XP ni dominio)."""
    instante = ensure_utc(momento) if momento else utcnow()
    actividad = _actividad_del_usuario(db, usuario.id, activity_id)
    _asegurar_abierta(db, cfg, actividad, momento=instante)
    return ServicioSesiones(db).registrar_latido(
        actividad, int(segundos), ahora=instante, timezone_name=usuario.timezone
    )


def abandonar(
    db: Session, usuario, activity_id: uuid.UUID, *, momento: datetime | None = None
) -> StudyActivity:
    """Marca la actividad como abandonada, sin recompensa (§7.6)."""
    instante = ensure_utc(momento) if momento else utcnow()
    actividad = _actividad_del_usuario(db, usuario.id, activity_id)
    if actividad.status == AttemptStatus.IN_PROGRESS:
        actividad.status = AttemptStatus.ABANDONED
        actividad.completed_at = instante
        actividad.counts_for_progress = False
        db.flush()
    return actividad


# ---------------------------------------------------------------------------
# POST /activities/{id}/complete
# ---------------------------------------------------------------------------


def _sin_responder(db: Session, cfg: ServicioConfig, actividad: StudyActivity) -> list[uuid.UUID]:
    """Preguntas de la actividad sin ninguna evidencia registrada (regla A7)."""
    presentadas = [q.id for q in _preguntas_de_actividad(db, cfg, actividad)]
    if not presentadas:
        return []
    respondidas = set(
        db.execute(
            sa.select(QuestionAttempt.question_id).where(
                QuestionAttempt.study_activity_id == actividad.id
            )
        ).scalars()
    )
    return [q for q in presentadas if q not in respondidas]


def completar(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    activity_id: uuid.UUID,
    *,
    idempotency_key: str,  # noqa: ARG001 - §8.3 la exige; el ancla real es la actividad
    momento: datetime | None = None,
) -> ReciboRecompensas:
    """Cierra la actividad, dispara el motor y devuelve el `RewardsReceipt` (§7.6, §7.10).

    Regla A7: si queda alguna pregunta sin respuesta registrada, la lección **no** se
    da por terminada. El catálogo de errores de §8.1 no tiene un código propio para
    este caso, así que se usa `UNAVAILABLE` (409) con el detalle de lo que falta.

    La cabecera `Idempotency-Key` es obligatoria por §8.3, pero el ancla de idempotencia
    de esta operación es la **actividad**: una lección solo se cierra una vez, y el
    recibo se reconstruye desde `domain_events` con la clave derivada del cierre. Así
    dos peticiones con claves distintas tampoco pueden pagar dos veces.
    """
    instante = ensure_utc(momento) if momento else utcnow()
    actividad = _actividad_del_usuario(db, usuario.id, activity_id)

    if actividad.activity_type == StudyActivityType.ASSESSMENT:
        raise AteneaError(
            "La prueba del módulo se cierra desde su propio envío.",
            code="ATTEMPT_NOT_OPEN",
            details={"activity_type": actividad.activity_type.value},
        )

    if actividad.status != AttemptStatus.IN_PROGRESS:
        # Reintento de una actividad ya cerrada: se devuelve el **mismo** recibo, sin
        # volver a contar la finalización ni a recalcular el dominio (§7.10 regla 4).
        return _recibo_ya_emitido(db, cfg, actividad)

    faltan = _sin_responder(db, cfg, actividad)
    if faltan:
        raise AteneaError(
            "Responde todas las preguntas antes de terminar la lección.",
            code="UNAVAILABLE",
            details={"unanswered": [str(q) for q in faltan]},
        )
    actividad.status = AttemptStatus.SUBMITTED
    actividad.completed_at = instante
    actividad.elapsed_seconds = max(
        0, int((instante - ensure_utc(actividad.started_at)).total_seconds())
    )
    db.flush()
    ServicioSesiones(db).acumular_tiempo_de_actividad(actividad)

    if actividad.activity_type == StudyActivityType.REVIEW:
        return _completar_repaso(db, cfg, usuario, actividad, instante)
    return _completar_leccion(db, cfg, usuario, actividad, instante)


def _recibo_ya_emitido(
    db: Session, cfg: ServicioConfig, actividad: StudyActivity
) -> ReciboRecompensas:
    """Recibo del cierre que ya ocurrió, reconstruido desde `domain_events` (§7.10 regla 4).

    Si la actividad se cerró sin evento de cierre (por ejemplo, fue abandonada) no hay
    nada que devolver: `409 ATTEMPT_NOT_OPEN`.
    """
    if actividad.activity_type == StudyActivityType.REVIEW:
        clave = f"review-complete:{actividad.user_id}:{actividad.id}:1"
    else:
        veces = db.execute(
            sa.select(UserLessonProgress.completion_count).where(
                UserLessonProgress.user_id == actividad.user_id,
                UserLessonProgress.lesson_id == actividad.lesson_id,
            )
        ).scalar_one_or_none()
        clave = f"lesson-complete:{actividad.user_id}:{actividad.lesson_id}:{int(veces or 0)}"

    evento = buscar_por_clave(db, clave)
    if evento is None:
        raise AteneaError(code="ATTEMPT_NOT_OPEN", details={"status": actividad.status.value})
    return reconstruir_recibo(db, evento, cfg).finalizar()


def _completar_leccion(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    actividad: StudyActivity,
    momento: datetime,
) -> ReciboRecompensas:
    """Emite `LESSON_COMPLETED` (y los derivados del módulo y la ruta) y funde el recibo."""
    progreso = ServicioProgreso(db)
    resultado = progreso.completar_leccion(
        usuario.id,
        actividad.lesson_id,
        questions_total=int(actividad.questions_total),
        questions_correct=int(actividad.questions_correct),
        active_seconds=int(actividad.active_seconds),
        ahora=momento,
        timezone_name=usuario.timezone,
        emitir_eventos=False,
    )
    leccion = db.get(Lesson, actividad.lesson_id)

    recibo = registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=EventType.LESSON_COMPLETED,
        payload={
            "lesson_id": str(actividad.lesson_id),
            "study_activity_id": str(actividad.id),
            "topic_id": str(resultado.topic_id),
            "module_id": str(resultado.module_id),
            "path_id": str(resultado.learning_path_id) if resultado.learning_path_id else None,
            "knowledge_area_id": (
                str(resultado.knowledge_area_id) if resultado.knowledge_area_id else None
            ),
            "questions_total": int(actividad.questions_total),
            "questions_correct": int(actividad.questions_correct),
            "accuracy_pct": a_float(actividad.accuracy_pct),
            # A4 mide la plausibilidad sobre el **tiempo transcurrido** de los relojes
            # del servidor (`completed_at − started_at`), no sobre el tiempo efectivo:
            # un usuario que deja la pestaña abierta late poco y aun así estudió.
            "duration_s": int(actividad.elapsed_seconds or actividad.active_seconds),
            "estimated_seconds": int(leccion.estimated_seconds) if leccion else None,
            "completion_index": resultado.completion_index,
            "is_first_completion": resultado.is_first_completion,
            "is_low_content": bool(leccion.is_low_content) if leccion else False,
            "counts_for_progress": bool(actividad.counts_for_progress),
        },
        idempotency_key=(
            f"lesson-complete:{usuario.id}:{actividad.lesson_id}:{resultado.completion_index}"
        ),
        occurred_at=momento,
        timezone=usuario.timezone,
        cfg=cfg,
    )

    actividad.xp_awarded = int(recibo.xp.amount) if recibo.xp else 0
    actividad.gold_awarded = int(recibo.gold.amount) if recibo.gold else 0
    db.flush()

    aplicar_dominio(
        db,
        cfg,
        usuario,
        recibo,
        topic_id=resultado.topic_id,
        module_id=resultado.module_id,
        knowledge_area_id=resultado.knowledge_area_id,
        clave_base=f"lesson:{actividad.id}",
        momento=momento,
    )

    if resultado.module_completed:
        modulo_recibo = registrar_evento(
            db,
            usuario_id=usuario.id,
            tipo=EventType.MODULE_COMPLETED,
            payload={
                "module_id": str(resultado.module_id),
                "module_index": _posicion_de_modulo(db, resultado.module_id),
                "path_id": str(resultado.learning_path_id) if resultado.learning_path_id else None,
                "knowledge_area_id": (
                    str(resultado.knowledge_area_id) if resultado.knowledge_area_id else None
                ),
            },
            idempotency_key=f"module-complete:{usuario.id}:{resultado.module_id}:1",
            occurred_at=momento,
            timezone=usuario.timezone,
            cfg=cfg,
        )
        fusionar_recibos(recibo, modulo_recibo)
    if resultado.modulo_desbloqueado_id is not None:
        agregar_desbloqueo_modulo(db, recibo, resultado.modulo_desbloqueado_id)
    if resultado.path_completed:
        ruta_recibo = registrar_evento(
            db,
            usuario_id=usuario.id,
            tipo=EventType.PATH_COMPLETED,
            payload={
                "path_id": str(resultado.learning_path_id),
                "knowledge_area_id": (
                    str(resultado.knowledge_area_id) if resultado.knowledge_area_id else None
                ),
                "modules": _modulos_de_ruta(db, resultado.learning_path_id),
            },
            idempotency_key=f"path-complete:{usuario.id}:{resultado.learning_path_id}:1",
            occurred_at=momento,
            timezone=usuario.timezone,
            cfg=cfg,
        )
        fusionar_recibos(recibo, ruta_recibo)
    return recibo.finalizar()


def _completar_repaso(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    actividad: StudyActivity,
    momento: datetime,
) -> ReciboRecompensas:
    """Emite `REVIEW_COMPLETED` y actualiza la estabilidad del tema (§6.5)."""
    total = max(1, int(actividad.questions_total))
    aciertos = int(actividad.questions_correct)
    puntaje = round(100.0 * aciertos / total, 2)

    fila_tema = db.execute(
        sa.select(UserTopicProgress).where(
            UserTopicProgress.user_id == usuario.id,
            UserTopicProgress.topic_id == actividad.topic_id,
        )
    ).scalar_one_or_none()

    recibo = registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=EventType.REVIEW_COMPLETED,
        payload={
            "study_activity_id": str(actividad.id),
            "topic_id": str(actividad.topic_id),
            "knowledge_area_id": (
                str(actividad.knowledge_area_id) if actividad.knowledge_area_id else None
            ),
            "questions_total": int(actividad.questions_total),
            "questions_correct": aciertos,
            "accuracy_pct": puntaje,
            "topic_was_weak": bool(fila_tema.is_weak) if fila_tema else False,
            "counts_for_progress": bool(actividad.counts_for_progress),
        },
        idempotency_key=f"review-complete:{usuario.id}:{actividad.id}:1",
        occurred_at=momento,
        timezone=usuario.timezone,
        cfg=cfg,
    )
    actividad.xp_awarded = int(recibo.xp.amount) if recibo.xp else 0
    actividad.gold_awarded = int(recibo.gold.amount) if recibo.gold else 0
    db.flush()

    ServicioDominio(db).registrar_repaso(usuario.id, actividad.topic_id, puntaje, ahora=momento)
    aplicar_dominio(
        db,
        cfg,
        usuario,
        recibo,
        topic_id=actividad.topic_id,
        module_id=actividad.module_id,
        knowledge_area_id=actividad.knowledge_area_id,
        clave_base=f"review:{actividad.id}",
        momento=momento,
    )
    return recibo.finalizar()


def aplicar_dominio(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    recibo: ReciboRecompensas,
    *,
    topic_id: uuid.UUID | None,
    module_id: uuid.UUID | None,
    knowledge_area_id: uuid.UUID | None,
    clave_base: str,
    momento: datetime,
) -> None:
    """Recalcula el dominio, lo escribe en el recibo y emite sus eventos (§6.4–§6.8, §4.2).

    Los eventos de dominio se emiten **desde aquí** con claves derivadas del hecho que
    los provocó (`<evento>:<user_id>:<entidad>:<n>`, §8.3) en vez de dejárselos a
    `recalcular_cascada`: así reprocesar la misma actividad no intenta insertar dos
    veces la misma clave, y `MASTERY_UPDATED` pasa por el motor de gamificación, que es
    quien hace reaccionar misiones, logros y desbloqueos (§4.2).
    """
    recalculo = ServicioDominio(db).recalcular_cascada(
        usuario.id,
        topic_id=topic_id,
        module_id=module_id,
        knowledge_area_id=knowledge_area_id,
        ahora=momento,
        timezone_name=usuario.timezone,
        emitir_eventos=False,
    )
    agregar_deltas_dominio(db, recibo, recalculo)

    fusionar_recibos(
        recibo,
        registrar_evento(
            db,
            usuario_id=usuario.id,
            tipo=EventType.MASTERY_UPDATED,
            payload={
                "topic_id": str(recalculo.topic_id) if recalculo.topic_id else None,
                "module_id": str(recalculo.module_id) if recalculo.module_id else None,
                "knowledge_area_id": (
                    str(recalculo.knowledge_area_id) if recalculo.knowledge_area_id else None
                ),
                "topic_before": recalculo.topic_before,
                "topic_after": recalculo.topic_after,
                "module_after": recalculo.module_after,
                "area_before": recalculo.area_before,
                "area_after": recalculo.area_after,
                "topics_mastered": recalculo.topics_mastered,
            },
            idempotency_key=f"mastery-updated:{usuario.id}:{clave_base}:1",
            occurred_at=momento,
            timezone=usuario.timezone,
            cfg=cfg,
        ),
    )

    hitos = (
        (
            EventType.TOPIC_MASTERED,
            "topic-mastered",
            recalculo.topic_id,
            recalculo.topic_status == KnowledgeAreaStatus.MASTERED,
            {"topic_id": str(recalculo.topic_id), "mastery": recalculo.topic_after},
        ),
        (
            EventType.MODULE_MASTERED,
            "module-mastered",
            recalculo.module_id,
            recalculo.module_status is not None and recalculo.module_status.value == "mastered",
            {"module_id": str(recalculo.module_id), "mastery": recalculo.module_after},
        ),
        (
            EventType.AREA_MASTERED,
            "area-mastered",
            recalculo.knowledge_area_id,
            recalculo.area_status == KnowledgeAreaStatus.MASTERED,
            {
                "knowledge_area_id": str(recalculo.knowledge_area_id),
                "mastery": recalculo.area_after,
            },
        ),
    )
    for tipo, prefijo, identificador, alcanzado, payload in hitos:
        if not alcanzado or identificador is None:
            continue
        payload["knowledge_area_id"] = (
            str(recalculo.knowledge_area_id) if recalculo.knowledge_area_id else None
        )
        fusionar_recibos(
            recibo,
            registrar_evento(
                db,
                usuario_id=usuario.id,
                tipo=tipo,
                payload=payload,
                idempotency_key=f"{prefijo}:{usuario.id}:{identificador}:1",
                occurred_at=momento,
                timezone=usuario.timezone,
                cfg=cfg,
            ),
        )


def agregar_deltas_dominio(db: Session, recibo: ReciboRecompensas, recalculo) -> None:
    """Traduce el recálculo de dominio a `mastery_deltas` del recibo (§7.10).

    El recibo lleva un delta por ámbito tocado (tema, módulo y conocimiento) con el
    valor **antes** y **después**, que es lo único que la app anima.
    """
    from app.models.content import PathModule  # noqa: PLC0415 - evita el ciclo de importación
    from app.modules.gamification.recompensas import DeltaDominio  # noqa: PLC0415

    ambitos = (
        ("topic", recalculo.topic_id, recalculo.topic_before, recalculo.topic_after,
         recalculo.topic_status),
        ("module", recalculo.module_id, recalculo.module_before, recalculo.module_after,
         recalculo.module_status),
        ("knowledge_area", recalculo.knowledge_area_id, recalculo.area_before,
         recalculo.area_after, recalculo.area_status),
    )
    vistos = {(d.scope, str(d.id)) for d in recibo.mastery_deltas}
    for scope, identificador, antes, despues, estado in ambitos:
        if identificador is None or (scope, str(identificador)) in vistos:
            continue
        vistos.add((scope, str(identificador)))
        if scope == "topic":
            entidad = db.get(Topic, identificador)
            nombre = entidad.title if entidad else None
        elif scope == "module":
            entidad = db.get(PathModule, identificador)
            nombre = (entidad.flavor_name or entidad.title) if entidad else None
        else:
            from app.models.content import KnowledgeArea  # noqa: PLC0415

            entidad = db.get(KnowledgeArea, identificador)
            nombre = entidad.name if entidad else None
        recibo.mastery_deltas.append(
            DeltaDominio(
                scope=scope,
                id=identificador,
                name=nombre,
                before=Decimal(str(round(float(antes), 2))),
                after=Decimal(str(round(float(despues), 2))),
                status=estado.value if estado is not None else None,
            )
        )


def agregar_desbloqueo_modulo(db: Session, recibo: ReciboRecompensas, module_id: uuid.UUID) -> None:
    """Añade el módulo recién desbloqueado a `unlocks` (§7.10)."""
    from app.models.content import PathModule  # noqa: PLC0415 - evita el ciclo de importación
    from app.modules.gamification.recompensas import DesbloqueoRecibo  # noqa: PLC0415

    modulo = db.get(PathModule, module_id)
    if modulo is None:
        return
    recibo.unlocks.append(
        DesbloqueoRecibo(type="module", id=modulo.id, name=modulo.flavor_name or modulo.title)
    )


def _posicion_de_modulo(db: Session, module_id: uuid.UUID) -> int | None:
    """Orden del módulo dentro de su ruta (campo `module_index` del evento)."""
    from app.models.content import PathModule  # noqa: PLC0415

    modulo = db.get(PathModule, module_id)
    return int(modulo.position) if modulo else None


def _modulos_de_ruta(db: Session, path_id: uuid.UUID | None) -> int:
    """Número de módulos de la ruta (campo `modules` de `PATH_COMPLETED`)."""
    from app.models.content import PathModule  # noqa: PLC0415

    if path_id is None:
        return 0
    return int(
        db.execute(
            sa.select(sa.func.count(PathModule.id)).where(PathModule.learning_path_id == path_id)
        ).scalar_one()
    )


# ---------------------------------------------------------------------------
# GET /reviews/recommended
# ---------------------------------------------------------------------------


def repasos_recomendados(
    db: Session, cfg: ServicioConfig, usuario_id: uuid.UUID, *, limite: int = 10
) -> list[SugerenciaRepaso]:
    """Temas en riesgo o débiles, con la duración estimada del repaso (§7.6)."""
    umbral = float(cfg.obtener_decimal("mastery.threshold.at_risk"))
    filas = list(
        db.execute(
            sa.select(UserTopicProgress, Topic.title)
            .join(Topic, Topic.id == UserTopicProgress.topic_id)
            .where(
                UserTopicProgress.user_id == usuario_id,
                sa.or_(
                    UserTopicProgress.is_weak.is_(True),
                    UserTopicProgress.mastery < umbral,
                ),
                UserTopicProgress.evidence_count > 0,
            )
            .order_by(UserTopicProgress.mastery, UserTopicProgress.topic_id)
            .limit(limite)
        )
    )
    if not filas:
        return []

    ids = [fila.topic_id for fila, _ in filas]
    conteos = dict(
        db.execute(
            sa.select(Question.topic_id, sa.func.count(Question.id))
            .where(
                Question.topic_id.in_(ids),
                Question.content_status != ContentStatus.FLAGGED,
                Question.is_flagged.is_(False),
            )
            .group_by(Question.topic_id)
        ).all()
    )
    segundos = dict(
        db.execute(
            sa.select(Question.topic_id, sa.func.sum(Question.estimated_seconds))
            .where(Question.topic_id.in_(ids))
            .group_by(Question.topic_id)
        ).all()
    )

    sugerencias: list[SugerenciaRepaso] = []
    for fila, titulo in filas:
        disponibles = int(conteos.get(fila.topic_id, 0))
        cantidad = preguntas.tamano_de_repaso(cfg, disponibles)
        if cantidad <= 0:
            continue
        medio = int(segundos.get(fila.topic_id, 0) or 0) / max(1, disponibles)
        sugerencias.append(
            SugerenciaRepaso(
                topic_id=fila.topic_id,
                title=titulo,
                module_id=fila.module_id,
                knowledge_area_id=fila.knowledge_area_id,
                mastery=a_float(fila.mastery),
                status=fila.status,
                is_weak=bool(fila.is_weak),
                question_count=cantidad,
                estimated_seconds=round(medio * cantidad),
            )
        )
    return sugerencias


__all__ = [
    "CONTEXTO_POR_ACTIVIDAD",
    "EVENTO_DE_CIERRE",
    "ActividadAbierta",
    "ContenidoLeccion",
    "ResultadoRespuesta",
    "SugerenciaRepaso",
    "abandonar",
    "agregar_deltas_dominio",
    "agregar_desbloqueo_modulo",
    "aplicar_dominio",
    "completar",
    "fusionar_recibos",
    "iniciar_leccion",
    "iniciar_repaso",
    "latido",
    "obtener_leccion",
    "procedencia",
    "repasos_recomendados",
    "responder",
]
