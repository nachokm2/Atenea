"""Evaluación de módulo: entrada, intento, respuestas y envío (§7.7).

Contrato §3.2 (`assessments`), §3.4 (`assessment_attempts`), §4.2
(`ASSESSMENT_STARTED`, `ASSESSMENT_COMPLETED`), §5.5 (`mastery.assessment.*`),
§6.6 (`E_mod`) y §7.10 (`assessment_result`).

La «Prueba del módulo» es el hito mayor del módulo (§5.9 D1) y la única forma de
dominarlo: sin evaluación rendida `M_mod <= 0.70` (§6.6).

Reglas duras:

* **Muestreo** con solapamiento ≤ `mastery.assessment.max_overlap` (30 %) respecto
  del intento anterior, determinista por intento (`preguntas.muestrear_evaluacion`).
* **Tope diario** `mastery.assessment.max_attempts_per_day` → `409 ASSESSMENT_ATTEMPT_LIMIT`.
* **Enfriamiento** tras reprobar: `mastery.assessment.cooldown_hours` = `[4, 24, 48]`
  → `409 ASSESSMENT_COOLDOWN` con `details.cooldown_until` y `details.can_waive_with_review`.
* **Feedback mínimo** mientras se responde: correcto/incorrecto, sin explicación. La
  explicación y la fuente llegan en la revisión posterior.
* **Reprobar no borra progreso**: el envío devuelve temas débiles y sugerencias de
  repaso, y el dominio ya ganado se conserva.
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
from app.models.content import Assessment, PathModule, Question, Topic
from app.models.enums import (
    ActivityContext,
    AssessmentOutcome,
    AttemptResult,
    AttemptStatus,
    EventType,
    StudyActivityType,
)
from app.models.progress import (
    AssessmentAttempt,
    QuestionAttempt,
    StudyActivity,
    UserModuleProgress,
)
from app.modules.content import correccion, lecciones, modulos, preguntas
from app.modules.gamification.eventos import registrar_evento
from app.modules.gamification.recompensas import ReciboRecompensas
from app.modules.gamification.servicio_config import ServicioConfig
from app.modules.progress import a_float
from app.modules.progress.dominio import ServicioDominio, puntaje_efectivo_evaluacion
from app.modules.progress.progreso import ServicioProgreso
from app.modules.progress.sesiones import ServicioSesiones


@dataclass(slots=True)
class InfoEvaluacion:
    """Pantalla de entrada de la prueba (§7.7 · P11)."""

    assessment: Assessment
    module: PathModule
    attempts_used: int
    attempts_total: int
    max_attempts_per_day: int
    cooldown_until: datetime | None
    can_start: bool
    blocked_reason: str | None
    pass_score: float
    question_count: int
    best_score: float | None
    best_effective: float | None
    passed_at: datetime | None
    reward_preview: dict[str, int]


@dataclass(slots=True)
class IntentoAbierto:
    """Intento recién creado con su banco muestreado (§7.7 `AssessmentAttemptOut`)."""

    attempt: AssessmentAttempt
    questions: list[dict[str, Any]]
    creado: bool = True


@dataclass(slots=True)
class RespuestaRegistrada:
    """Feedback mínimo de `POST /assessment-attempts/{id}/answers` (§7.7)."""

    recorded: bool
    index: int
    total: int
    is_correct: bool


@dataclass(slots=True)
class ResultadoEvaluacion:
    """`assessment_result` del recibo (§7.10 regla 6)."""

    score_pct: float
    effective_score_pct: float
    outcome: AssessmentOutcome
    passed: bool
    correct_count: int
    question_count: int
    per_topic: list[dict[str, Any]] = field(default_factory=list)
    weak_topics: list[dict[str, Any]] = field(default_factory=list)
    cooldown_until: datetime | None = None
    review_suggestions: list[dict[str, Any]] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        """Forma JSON exacta que viaja en `RewardsReceipt.assessment_result`."""
        return {
            "score_pct": self.score_pct,
            "effective_score_pct": self.effective_score_pct,
            "outcome": self.outcome.value,
            "passed": self.passed,
            "correct_count": self.correct_count,
            "question_count": self.question_count,
            "per_topic": self.per_topic,
            "weak_topics": self.weak_topics,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "review_suggestions": self.review_suggestions,
        }


@dataclass(slots=True)
class RevisionIntento:
    """Revisión de un intento enviado, ya con explicación y fuente (§7.7)."""

    attempt: AssessmentAttempt
    items: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Lectura y guardas
# ---------------------------------------------------------------------------


def _intentos_del_usuario(
    db: Session, usuario_id: uuid.UUID, assessment_id: uuid.UUID
) -> list[AssessmentAttempt]:
    """Intentos de esa evaluación, del más antiguo al más reciente."""
    return list(
        db.execute(
            sa.select(AssessmentAttempt)
            .where(
                AssessmentAttempt.user_id == usuario_id,
                AssessmentAttempt.assessment_id == assessment_id,
            )
            .order_by(AssessmentAttempt.attempt_no)
        ).scalars()
    )


def _horas_de_enfriamiento(cfg: ServicioConfig, intentos_fallidos: int) -> int:
    """Horas de enfriamiento tras reprobar, según `mastery.assessment.cooldown_hours`."""
    horas = [int(h) for h in cfg.obtener_lista("mastery.assessment.cooldown_hours")]
    if not horas:
        return 0
    return horas[min(max(0, intentos_fallidos - 1), len(horas) - 1)]


def _enfriamiento_vigente(
    intentos: list[AssessmentAttempt], *, momento: datetime
) -> datetime | None:
    """Fecha hasta la que hay enfriamiento activo, o `None` si ya se puede reintentar."""
    for intento in reversed(intentos):
        if intento.cooldown_until is None or intento.cooldown_waived_at is not None:
            continue
        limite = ensure_utc(intento.cooldown_until)
        return limite if limite > momento else None
    return None


def _tope_diario(cfg: ServicioConfig, evaluacion: Assessment) -> int:
    """Intentos por día: el menor entre la evaluación y `game_configs` (§5.5)."""
    return min(
        int(evaluacion.max_attempts_per_day),
        cfg.obtener_int("mastery.assessment.max_attempts_per_day"),
    )


def _usados_hoy(intentos: list[AssessmentAttempt], hoy) -> int:
    """Intentos abiertos en la fecha local de hoy (§8.6)."""
    return len([i for i in intentos if i.local_date == hoy])


def info_evaluacion(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    module_id: uuid.UUID,
    *,
    momento: datetime | None = None,
) -> InfoEvaluacion:
    """Pantalla de entrada: reglas, recompensa, intentos usados y enfriamiento (§7.7)."""
    instante = ensure_utc(momento) if momento else utcnow()
    contexto = modulos.contexto_de_modulo(db, usuario.id, module_id)
    avance = modulos.asegurar_desbloqueado(db, usuario.id, contexto)
    evaluacion = modulos.evaluacion_de_modulo(db, module_id)

    intentos = _intentos_del_usuario(db, usuario.id, evaluacion.id)
    hoy = user_local_date(instante, usuario.timezone)
    usados = _usados_hoy(intentos, hoy)
    tope = _tope_diario(cfg, evaluacion)
    enfriamiento = _enfriamiento_vigente(intentos, momento=instante)

    motivo: str | None = None
    if enfriamiento is not None:
        motivo = "ASSESSMENT_COOLDOWN"
    elif usados >= tope:
        motivo = "ASSESSMENT_ATTEMPT_LIMIT"

    return InfoEvaluacion(
        assessment=evaluacion,
        module=contexto.module,
        attempts_used=usados,
        attempts_total=len(intentos),
        max_attempts_per_day=tope,
        cooldown_until=enfriamiento,
        can_start=motivo is None,
        blocked_reason=motivo,
        pass_score=a_float(evaluacion.pass_score),
        question_count=int(evaluacion.question_count),
        # `is not None`, no la verdad del valor: un 0 % es un puntaje real y
        # `Decimal('0.00')` es falso en Python. Con la comprobación de verdad,
        # quien saca cero ve su marca en el mapa —que sí usa `is not None`— y
        # la ve desaparecer al abrir esta pantalla.
        best_score=(
            a_float(avance.assessment_best_score)
            if avance.assessment_best_score is not None
            else None
        ),
        best_effective=(
            a_float(avance.assessment_best_effective)
            if avance.assessment_best_effective is not None
            else None
        ),
        passed_at=avance.assessment_passed_at,
        reward_preview={
            "xp": cfg.obtener_int("xp.assessment_passed"),
            "gold": cfg.obtener_int("gold.assessment_passed"),
        },
    )


# ---------------------------------------------------------------------------
# POST /assessments/{id}/start
# ---------------------------------------------------------------------------


def _intento_por_clave(
    db: Session, usuario_id: uuid.UUID, idempotency_key: str
) -> AssessmentAttempt | None:
    """Intento ya creado con esa `Idempotency-Key` (§8.3)."""
    return db.execute(
        sa.select(AssessmentAttempt).where(
            AssessmentAttempt.user_id == usuario_id,
            AssessmentAttempt.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()


def _preguntas_del_intento(db: Session, intento: AssessmentAttempt) -> list[Question]:
    """Preguntas muestreadas del intento, en el orden en que se sirvieron."""
    ids = [uuid.UUID(str(x)) for x in (intento.question_ids or [])]
    mapa = preguntas.por_id(db, ids)
    return [mapa[i] for i in ids if i in mapa]


def iniciar_intento(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    assessment_id: uuid.UUID,
    *,
    idempotency_key: str,
    device: str | None = None,
    momento: datetime | None = None,
) -> IntentoAbierto:
    """Crea el intento y muestrea el banco con solapamiento ≤ 30 % (§7.7)."""
    instante = ensure_utc(momento) if momento else utcnow()
    existente = _intento_por_clave(db, usuario.id, idempotency_key)
    if existente is not None:
        pool = _preguntas_del_intento(db, existente)
        return IntentoAbierto(
            attempt=existente,
            questions=[preguntas.vista_publica(q, position=i) for i, q in enumerate(pool, start=1)],
            creado=False,
        )

    evaluacion, contexto = modulos.contexto_de_evaluacion(db, usuario.id, assessment_id)
    modulos.asegurar_desbloqueado(db, usuario.id, contexto)
    modulos.asegurar_contenido_listo(evaluacion.content_status, target_id=evaluacion.id)

    intentos = _intentos_del_usuario(db, usuario.id, evaluacion.id)
    hoy = user_local_date(instante, usuario.timezone)
    enfriamiento = _enfriamiento_vigente(intentos, momento=instante)
    if enfriamiento is not None:
        raise AteneaError(
            code="ASSESSMENT_COOLDOWN",
            details={
                "cooldown_until": enfriamiento.isoformat(),
                "can_waive_with_review": True,
            },
        )
    tope = _tope_diario(cfg, evaluacion)
    if _usados_hoy(intentos, hoy) >= tope:
        raise AteneaError(
            code="ASSESSMENT_ATTEMPT_LIMIT",
            details={"max_attempts_per_day": tope, "attempts_used": _usados_hoy(intentos, hoy)},
        )

    attempt_no = len(intentos) + 1
    previas = [uuid.UUID(str(x)) for x in (intentos[-1].question_ids or [])] if intentos else []
    seleccion = preguntas.muestrear_evaluacion(
        db,
        cfg,
        evaluacion,
        previas=previas,
        semilla=f"{usuario.id}:{evaluacion.id}:{attempt_no}",
    )
    if not seleccion:
        raise AteneaError(
            code="CONTENT_NOT_READY",
            details={"assessment_id": str(evaluacion.id), "reason": "empty_bank"},
        )

    intento = AssessmentAttempt(
        user_id=usuario.id,
        assessment_id=evaluacion.id,
        module_id=contexto.module.id,
        learning_path_id=contexto.path.id,
        knowledge_area_id=contexto.knowledge_area_id,
        attempt_no=attempt_no,
        status=AttemptStatus.IN_PROGRESS,
        question_ids=[str(q.id) for q in seleccion],
        question_count=len(seleccion),
        started_at=instante,
        local_date=hoy,
        idempotency_key=idempotency_key,
    )
    db.add(intento)
    db.flush()

    sesiones = ServicioSesiones(db)
    sesion = sesiones.abrir_sesion(usuario.id, usuario.timezone, device=device, ahora=instante)
    db.add(
        StudyActivity(
            user_id=usuario.id,
            session_id=sesion.id,
            activity_type=StudyActivityType.ASSESSMENT,
            status=AttemptStatus.IN_PROGRESS,
            assessment_id=evaluacion.id,
            module_id=contexto.module.id,
            learning_path_id=contexto.path.id,
            knowledge_area_id=contexto.knowledge_area_id,
            started_at=instante,
            questions_total=len(seleccion),
            local_date=hoy,
            idempotency_key=f"assessment:{intento.id}",
        )
    )
    db.flush()

    registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=EventType.ASSESSMENT_STARTED,
        payload={
            "assessment_id": str(evaluacion.id),
            "attempt_id": str(intento.id),
            "attempt_no": attempt_no,
            "question_count": len(seleccion),
        },
        idempotency_key=f"assessment-started:{usuario.id}:{intento.id}:1",
        occurred_at=instante,
        timezone=usuario.timezone,
        cfg=cfg,
    )
    return IntentoAbierto(
        attempt=intento,
        questions=[preguntas.vista_publica(q, position=i) for i, q in enumerate(seleccion, start=1)],
    )


# ---------------------------------------------------------------------------
# POST /assessment-attempts/{id}/answers
# ---------------------------------------------------------------------------


def _intento_del_usuario(
    db: Session, usuario_id: uuid.UUID, attempt_id: uuid.UUID
) -> AssessmentAttempt:
    """Carga un intento propio; los ajenos responden `404` (§8.7)."""
    intento = db.get(AssessmentAttempt, attempt_id)
    if intento is None or intento.user_id != usuario_id:
        raise NotFound()
    return intento


def _actividad_de_intento(db: Session, intento: AssessmentAttempt) -> StudyActivity | None:
    """Actividad de estudio asociada al intento (contabilidad de tiempo)."""
    return db.execute(
        sa.select(StudyActivity).where(
            StudyActivity.user_id == intento.user_id,
            StudyActivity.idempotency_key == f"assessment:{intento.id}",
        )
    ).scalar_one_or_none()


def registrar_respuesta(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    attempt_id: uuid.UUID,
    *,
    question_id: uuid.UUID,
    response: Any,
    response_ms: int = 0,
    idempotency_key: str,
    momento: datetime | None = None,
) -> RespuestaRegistrada:
    """Registra una respuesta del examen con **feedback mínimo** (§7.7).

    En una evaluación no hay revancha: cada pregunta se responde una sola vez, así que
    `attempt_no` es siempre 1 y el peso de dominio es el de un acierto limpio (§6.4).
    """
    instante = ensure_utc(momento) if momento else utcnow()
    intento = _intento_del_usuario(db, usuario.id, attempt_id)

    respondidas = list(
        db.execute(
            sa.select(QuestionAttempt).where(
                QuestionAttempt.assessment_attempt_id == intento.id
            )
        ).scalars()
    )
    repetida = next((r for r in respondidas if r.idempotency_key == idempotency_key), None)
    if repetida is not None:
        return RespuestaRegistrada(
            recorded=True,
            index=len(respondidas),
            total=int(intento.question_count),
            is_correct=bool(repetida.is_correct),
        )

    if intento.status != AttemptStatus.IN_PROGRESS:
        raise AteneaError(code="ATTEMPT_NOT_OPEN", details={"status": intento.status.value})

    permitidas = {q.id: q for q in _preguntas_del_intento(db, intento)}
    pregunta = permitidas.get(question_id)
    if pregunta is None:
        raise AteneaError(
            code="ATTEMPT_NOT_OPEN",
            details={"question_id": str(question_id), "reason": "question_not_in_attempt"},
        )
    if any(r.question_id == question_id for r in respondidas):
        raise AteneaError(code="ALREADY_ANSWERED", details={"question_id": str(question_id)})

    veredicto = correccion.corregir(
        cfg,
        pregunta,
        response,
        attempt_no=1,
        db=db,
        usuario_id=getattr(usuario, "id", None),
        activity_id=intento.id,
    )
    actividad = _actividad_de_intento(db, intento)
    evidencia = QuestionAttempt(
        user_id=usuario.id,
        question_id=pregunta.id,
        topic_id=pregunta.topic_id,
        knowledge_area_id=intento.knowledge_area_id,
        study_activity_id=actividad.id if actividad else None,
        assessment_attempt_id=intento.id,
        context=ActivityContext.ASSESSMENT,
        attempt_no=1,
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
        counts_for_progress=veredicto.result != AttemptResult.SKIPPED,
        counts_for_mastery=veredicto.counts_for_mastery,
        answered_at=instante,
        local_date=user_local_date(instante, usuario.timezone),
        idempotency_key=idempotency_key,
    )
    db.add(evidencia)
    db.flush()

    registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=EventType.QUESTION_ANSWERED,
        payload={
            "question_id": str(pregunta.id),
            "topic_id": str(pregunta.topic_id),
            "knowledge_area_id": (
                str(intento.knowledge_area_id) if intento.knowledge_area_id else None
            ),
            "lesson_id": None,
            "assessment_attempt_id": str(intento.id),
            "context": ActivityContext.ASSESSMENT.value,
            "attempt_no": 1,
            "is_correct": bool(veredicto.is_correct),
            "partial_score": veredicto.partial_score,
            "difficulty": pregunta.difficulty.value,
            "evaluation_method": veredicto.evaluation_method.value,
            "response_ms": max(0, int(response_ms)),
            "is_retry_of_failed": False,
            "counts_for_progress": bool(evidencia.counts_for_progress),
        },
        idempotency_key=f"question-answered:{usuario.id}:{evidencia.id}:1",
        occurred_at=instante,
        timezone=usuario.timezone,
        cfg=cfg,
    )

    return RespuestaRegistrada(
        recorded=True,
        index=len(respondidas) + 1,
        total=int(intento.question_count),
        is_correct=bool(veredicto.is_correct),
    )


# ---------------------------------------------------------------------------
# POST /assessment-attempts/{id}/submit
# ---------------------------------------------------------------------------


def _desenlace(cfg: ServicioConfig, puntaje: float, umbral: float) -> AssessmentOutcome:
    """Traduce el puntaje al enum `AssessmentOutcome` (§2 y §5.5)."""
    if puntaje >= 100.0:
        return AssessmentOutcome.PASSED_PERFECT
    if puntaje >= float(cfg.obtener_int("mastery.assessment.distinction_score")):
        return AssessmentOutcome.PASSED_DISTINCTION
    if puntaje >= umbral:
        return AssessmentOutcome.PASSED
    return AssessmentOutcome.FAILED


def _desglose_por_tema(
    db: Session, evidencias: list[QuestionAttempt], cfg: ServicioConfig
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`per_topic[]` y `weak_topics[]` del resultado (§7.7 y regla R3 de §5.5)."""
    umbral_debil = float(cfg.obtener_json("mastery.weakness_rules")["R3_assessment_topic_lt"])
    agregado: dict[uuid.UUID, list[int]] = {}
    for evidencia in evidencias:
        totales = agregado.setdefault(evidencia.topic_id, [0, 0])
        totales[0] += 1 if evidencia.is_correct else 0
        totales[1] += 1

    titulos = {}
    if agregado:
        titulos = dict(
            db.execute(
                sa.select(Topic.id, Topic.title).where(Topic.id.in_(list(agregado)))
            ).all()
        )

    per_topic: list[dict[str, Any]] = []
    debiles: list[dict[str, Any]] = []
    for topic_id, (correctas, total) in agregado.items():
        pct = round(100.0 * correctas / total, 2) if total else 0.0
        fila = {
            "topic_id": str(topic_id),
            "title": titulos.get(topic_id),
            "correct": correctas,
            "total": total,
            "pct": pct,
        }
        per_topic.append(fila)
        if pct < umbral_debil:
            debiles.append(fila)
    per_topic.sort(key=lambda f: f["pct"])
    return per_topic, debiles


def enviar_intento(
    db: Session,
    cfg: ServicioConfig,
    usuario,
    attempt_id: uuid.UUID,
    *,
    idempotency_key: str,  # noqa: ARG001 - §8.3 la exige; el ancla real es el intento
    momento: datetime | None = None,
) -> ReciboRecompensas:
    """Cierra el intento, calcula puntaje y dominio, y devuelve el recibo (§7.7, §7.10).

    La cabecera `Idempotency-Key` es obligatoria por §8.3, pero el ancla de idempotencia
    es el **intento**: se envía una sola vez y el recibo se reconstruye desde
    `domain_events` con la clave derivada del intento.

    Reprobar **no** borra progreso: el dominio ya ganado se conserva y el resultado
    trae los temas débiles y las sugerencias de repaso para la siguiente pasada.
    """
    instante = ensure_utc(momento) if momento else utcnow()
    intento = _intento_del_usuario(db, usuario.id, attempt_id)
    evaluacion = db.get(Assessment, intento.assessment_id)
    if evaluacion is None:  # pragma: no cover - la FK lo impide
        raise NotFound()

    clave_evento = f"assessment-complete:{usuario.id}:{intento.id}:1"
    if intento.status == AttemptStatus.SUBMITTED:
        recibo = registrar_evento(
            db,
            usuario_id=usuario.id,
            tipo=EventType.ASSESSMENT_COMPLETED,
            payload=_payload_de_intento(intento),
            idempotency_key=clave_evento,
            occurred_at=instante,
            timezone=usuario.timezone,
            cfg=cfg,
        )
        recibo.assessment_result = _resultado_persistido(cfg, intento, instante).como_dict()
        return recibo.finalizar()

    evidencias = list(
        db.execute(
            sa.select(QuestionAttempt)
            .where(QuestionAttempt.assessment_attempt_id == intento.id)
            .order_by(QuestionAttempt.answered_at)
        ).scalars()
    )
    total = int(intento.question_count) or len(evidencias)
    correctas = len([e for e in evidencias if e.is_correct])
    puntaje = round(100.0 * correctas / total, 2) if total else 0.0
    umbral = a_float(evaluacion.pass_score)

    servicio_dominio = ServicioDominio(db)
    historico = [(int(i.attempt_no), a_float(i.score)) for i in
                 _intentos_del_usuario(db, usuario.id, evaluacion.id)
                 if i.score is not None and i.id != intento.id]
    historico.append((int(intento.attempt_no), puntaje))
    efectivo_de_este = max(
        0.0,
        puntaje
        - min(
            servicio_dominio.cfg.penalizacion_reintento_por_intento
            * 100.0
            * max(0, int(intento.attempt_no) - 1),
            servicio_dominio.cfg.penalizacion_reintento_max * 100.0,
        ),
    )
    desenlace = _desenlace(cfg, puntaje, umbral)
    aprobado = desenlace != AssessmentOutcome.FAILED

    per_topic, debiles = _desglose_por_tema(db, evidencias, cfg)

    intento.status = AttemptStatus.SUBMITTED
    intento.submitted_at = instante
    intento.correct_count = correctas
    intento.score = Decimal(str(puntaje))
    intento.effective_score = Decimal(str(round(efectivo_de_este, 2)))
    intento.outcome = desenlace
    intento.per_topic_scores = per_topic
    intento.weak_topic_ids = [f["topic_id"] for f in debiles]
    if not aprobado:
        fallidos = len(
            [
                i
                for i in _intentos_del_usuario(db, usuario.id, evaluacion.id)
                if i.outcome == AssessmentOutcome.FAILED
            ]
        )
        intento.cooldown_until = instante + timedelta(
            hours=_horas_de_enfriamiento(cfg, max(1, fallidos))
        )
    db.flush()

    actividad = _actividad_de_intento(db, intento)
    if actividad is not None and actividad.status == AttemptStatus.IN_PROGRESS:
        actividad.status = AttemptStatus.SUBMITTED
        actividad.completed_at = instante
        actividad.elapsed_seconds = max(
            0, int((instante - ensure_utc(actividad.started_at)).total_seconds())
        )
        actividad.questions_total = total
        actividad.questions_correct = correctas
        actividad.accuracy_pct = Decimal(str(puntaje))
        db.flush()
        ServicioSesiones(db).acumular_tiempo_de_actividad(actividad)

    avance = db.execute(
        sa.select(UserModuleProgress).where(
            UserModuleProgress.user_id == usuario.id,
            UserModuleProgress.module_id == intento.module_id,
        )
    ).scalar_one_or_none()
    if avance is None:
        ServicioProgreso(db).asegurar_progreso_ruta(usuario.id, intento.learning_path_id)
        avance = db.execute(
            sa.select(UserModuleProgress).where(
                UserModuleProgress.user_id == usuario.id,
                UserModuleProgress.module_id == intento.module_id,
            )
        ).scalar_one()
    avance.assessment_attempts = int(avance.assessment_attempts) + 1
    if avance.assessment_best_score is None or puntaje > a_float(avance.assessment_best_score):
        avance.assessment_best_score = Decimal(str(puntaje))
    efectivo_global = puntaje_efectivo_evaluacion(historico, servicio_dominio.cfg)
    avance.assessment_best_effective = Decimal(str(round(float(efectivo_global), 2)))
    if aprobado and avance.assessment_passed_at is None:
        avance.assessment_passed_at = instante
    db.flush()

    recibo = registrar_evento(
        db,
        usuario_id=usuario.id,
        tipo=EventType.ASSESSMENT_COMPLETED,
        payload=_payload_de_intento(intento),
        idempotency_key=clave_evento,
        occurred_at=instante,
        timezone=usuario.timezone,
        cfg=cfg,
    )
    intento.xp_awarded = int(recibo.xp.amount) if recibo.xp else 0
    intento.gold_awarded = int(recibo.gold.amount) if recibo.gold else 0
    db.flush()

    lecciones.aplicar_dominio(
        db,
        cfg,
        usuario,
        recibo,
        topic_id=None,
        module_id=intento.module_id,
        knowledge_area_id=intento.knowledge_area_id,
        clave_base=f"assessment:{intento.id}",
        momento=instante,
    )

    progreso = ServicioProgreso(db)
    estado_modulo = progreso.recalcular_modulo(
        usuario.id,
        intento.module_id,
        ahora=instante,
        timezone_name=usuario.timezone,
        emitir_eventos=False,
    )
    if estado_modulo.completado_ahora:
        modulo = db.get(PathModule, intento.module_id)
        modulo_recibo = registrar_evento(
            db,
            usuario_id=usuario.id,
            tipo=EventType.MODULE_COMPLETED,
            payload={
                "module_id": str(intento.module_id),
                "module_index": int(modulo.position) if modulo else None,
                "path_id": str(intento.learning_path_id) if intento.learning_path_id else None,
                "knowledge_area_id": (
                    str(intento.knowledge_area_id) if intento.knowledge_area_id else None
                ),
            },
            idempotency_key=f"module-complete:{usuario.id}:{intento.module_id}:1",
            occurred_at=instante,
            timezone=usuario.timezone,
            cfg=cfg,
        )
        lecciones.fusionar_recibos(recibo, modulo_recibo)
    if estado_modulo.modulo_desbloqueado_id is not None:
        lecciones.agregar_desbloqueo_modulo(db, recibo, estado_modulo.modulo_desbloqueado_id)

    estado_ruta = progreso.recalcular_ruta(
        usuario.id,
        intento.learning_path_id,
        ahora=instante,
        timezone_name=usuario.timezone,
        emitir_eventos=False,
    )
    if estado_ruta.completada_ahora:
        ruta_recibo = registrar_evento(
            db,
            usuario_id=usuario.id,
            tipo=EventType.PATH_COMPLETED,
            payload={
                "path_id": str(intento.learning_path_id),
                "knowledge_area_id": (
                    str(intento.knowledge_area_id) if intento.knowledge_area_id else None
                ),
            },
            idempotency_key=f"path-complete:{usuario.id}:{intento.learning_path_id}:1",
            occurred_at=instante,
            timezone=usuario.timezone,
            cfg=cfg,
        )
        lecciones.fusionar_recibos(recibo, ruta_recibo)

    recibo.assessment_result = _resultado_persistido(cfg, intento, instante).como_dict()
    return recibo.finalizar()


def _payload_de_intento(intento: AssessmentAttempt) -> dict[str, Any]:
    """Payload canónico de `ASSESSMENT_COMPLETED` (§4.2).

    Lleva `duration_s` medido con los relojes **del servidor** porque el motor lo
    necesita para la regla A4 (§6.9): una prueba exige `20 s x n_preguntas`.
    """
    duracion = 0
    if intento.submitted_at is not None and intento.started_at is not None:
        duracion = max(
            0,
            int((ensure_utc(intento.submitted_at) - ensure_utc(intento.started_at)).total_seconds()),
        )
    return {
        "duration_s": duracion,
        "assessment_id": str(intento.assessment_id),
        "attempt_id": str(intento.id),
        "module_id": str(intento.module_id),
        "path_id": str(intento.learning_path_id) if intento.learning_path_id else None,
        "knowledge_area_id": (
            str(intento.knowledge_area_id) if intento.knowledge_area_id else None
        ),
        "attempt_no": int(intento.attempt_no),
        "score_pct": a_float(intento.score),
        "effective_score_pct": a_float(intento.effective_score),
        "passed": intento.outcome != AssessmentOutcome.FAILED,
        "outcome": intento.outcome.value if intento.outcome else None,
        "question_count": int(intento.question_count),
        "per_topic_scores": list(intento.per_topic_scores or []),
        "weak_topic_ids": list(intento.weak_topic_ids or []),
        "counts_for_progress": True,
    }


def _resultado_persistido(
    cfg: ServicioConfig, intento: AssessmentAttempt, momento: datetime
) -> ResultadoEvaluacion:
    """Reconstruye `assessment_result` desde el intento ya cerrado (idempotencia §7.10)."""
    debiles = [
        fila
        for fila in list(intento.per_topic_scores or [])
        if fila.get("topic_id") in set(intento.weak_topic_ids or [])
    ]
    sugerencias = []
    if debiles:
        rango = cfg.obtener_json("mastery.review.questions")
        sugerencias = [
            {
                "topic_id": fila["topic_id"],
                "title": fila.get("title"),
                "reason": "assessment_weak_topic",
                "question_count": int(rango["min"]),
            }
            for fila in debiles
        ]
    return ResultadoEvaluacion(
        score_pct=a_float(intento.score),
        effective_score_pct=a_float(intento.effective_score),
        outcome=intento.outcome or AssessmentOutcome.FAILED,
        passed=intento.outcome is not None and intento.outcome != AssessmentOutcome.FAILED,
        correct_count=int(intento.correct_count),
        question_count=int(intento.question_count),
        per_topic=list(intento.per_topic_scores or []),
        weak_topics=debiles,
        cooldown_until=(
            ensure_utc(intento.cooldown_until)
            if intento.cooldown_until is not None
            and ensure_utc(intento.cooldown_until) > momento
            else None
        ),
        review_suggestions=sugerencias,
    )


# ---------------------------------------------------------------------------
# GET /assessment-attempts/{id}
# ---------------------------------------------------------------------------


def revision_intento(
    db: Session, usuario, attempt_id: uuid.UUID
) -> RevisionIntento:
    """Revisión de respuestas con explicación y fuente (§7.7).

    Se sirve la **explicación**, nunca la `answer_key`: lo que el usuario ve es el
    texto pedagógico y la respuesta que dio, no la estructura de corrección.
    """
    from app.models.enums import ProvenanceContentType  # noqa: PLC0415

    intento = _intento_del_usuario(db, usuario.id, attempt_id)
    pool = _preguntas_del_intento(db, intento)
    evidencias = {
        fila.question_id: fila
        for fila in db.execute(
            sa.select(QuestionAttempt).where(
                QuestionAttempt.assessment_attempt_id == intento.id
            )
        ).scalars()
    }
    trazas: dict[uuid.UUID, list] = {}
    for traza in lecciones.procedencia(
        db, content_type=ProvenanceContentType.QUESTION, content_ids=[q.id for q in pool]
    ):
        trazas.setdefault(traza.content_id, []).append(traza)

    items = []
    for indice, pregunta in enumerate(pool, start=1):
        evidencia = evidencias.get(pregunta.id)
        items.append(
            {
                **preguntas.vista_publica(pregunta, position=indice),
                "explanation": pregunta.explanation,
                "response": dict(evidencia.response or {}) if evidencia else None,
                "result": evidencia.result.value if evidencia else AttemptResult.SKIPPED.value,
                "is_correct": bool(evidencia.is_correct) if evidencia else False,
                "partial_score": a_float(evidencia.partial_score) if evidencia else 0.0,
                "evaluation_method": (
                    evidencia.evaluation_method.value if evidencia else None
                ),
                "provenance": [
                    {
                        "chunk_id": str(t.chunk_id) if t.chunk_id else None,
                        "document_id": str(t.document_id) if t.document_id else None,
                        "origin": t.origin.value,
                    }
                    for t in trazas.get(pregunta.id, [])
                ],
            }
        )
    return RevisionIntento(attempt=intento, items=items)


__all__ = [
    "InfoEvaluacion",
    "IntentoAbierto",
    "RespuestaRegistrada",
    "ResultadoEvaluacion",
    "RevisionIntento",
    "enviar_intento",
    "info_evaluacion",
    "iniciar_intento",
    "registrar_respuesta",
    "revision_intento",
]
