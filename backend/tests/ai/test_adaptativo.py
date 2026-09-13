"""Adaptativo: detección determinista de debilidad y re-explicación con enfoque rotativo."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
import sqlalchemy as sa

from app.core.time import utcnow
from app.models.content import Assessment, PathModule, Question, Topic
from app.models.enums import (
    ActivityContext,
    AssessmentOutcome,
    AttemptResult,
    AttemptStatus,
    ContentStatus,
    DifficultyLevel,
    EvaluationMethod,
    JobStatus,
    JobType,
    ProvenanceContentType,
    QuestionType,
)
from app.models.ingestion import ContentProvenance, GenerationJob
from app.models.progress import AssessmentAttempt, QuestionAttempt
from app.modules.ai import adaptativo, arquitecto_ruta as fase_a


@pytest.fixture
def tema(db, cfg, proveedor, ruta) -> Topic:
    """Tema real de una ruta ya diseñada."""
    fase_a.disenar_ruta(db, cfg, proveedor, learning_path_id=ruta.id, usuario_id=ruta.user_id)
    proveedor.reiniciar_contador()
    return db.execute(
        sa.select(Topic)
        .join(PathModule, PathModule.id == Topic.module_id)
        .where(PathModule.learning_path_id == ruta.id)
        .order_by(Topic.position)
        .limit(1)
    ).scalar_one()


def _pregunta(db, tema: Topic, *, objetivo: str = "Explicar el concepto", segundos: int = 45) -> Question:
    """Pregunta mínima del tema, para colgar de ella las evidencias."""
    fila = Question(
        topic_id=tema.id,
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=DifficultyLevel.MEDIUM,
        stem="¿Cuál es la respuesta?",
        body={"options": [{"key": "a", "text": "una"}, {"key": "b", "text": "otra"}]},
        answer_key={"correct_option": "a"},
        learning_objective=objetivo,
        estimated_seconds=segundos,
        content_status=ContentStatus.READY,
    )
    db.add(fila)
    db.flush()
    return fila


def _respuesta(
    db,
    usuario,
    tema: Topic,
    pregunta: Question,
    *,
    correcta: bool,
    hace_minutos: int = 0,
    response_ms: int = 8_000,
) -> QuestionAttempt:
    """Evidencia de respuesta (`question_attempts`, append-only)."""
    momento = utcnow() - dt.timedelta(minutes=hace_minutos)
    fila = QuestionAttempt(
        user_id=usuario.id,
        question_id=pregunta.id,
        topic_id=tema.id,
        context=ActivityContext.LESSON,
        attempt_no=1,
        response={"choice": "a" if correcta else "b"},
        result=AttemptResult.CORRECT if correcta else AttemptResult.INCORRECT,
        is_correct=correcta,
        partial_score=100 if correcta else 0,
        correctness_weight=1 if correcta else 0,
        difficulty=DifficultyLevel.MEDIUM,
        evaluation_method=EvaluationMethod.DETERMINISTIC,
        response_ms=response_ms,
        answered_at=momento,
        local_date=momento.date(),
        idempotency_key=f"att-{uuid.uuid4()}",
    )
    db.add(fila)
    db.flush()
    return fila


# ---------------------------------------------------------------------------
# Detección determinista
# ---------------------------------------------------------------------------


def test_sin_evidencias_no_hay_debilidad(db, cfg, usuario, tema) -> None:
    """Sin respuestas no se inventa una debilidad."""
    assert adaptativo.detectar_debilidad(db, cfg, usuario_id=usuario.id, topic_id=tema.id) is None


def test_r1_errores_en_las_ultimas_diez(db, cfg, usuario, tema) -> None:
    """`R1_errors_in_last_10 = 3`: tres errores recientes bastan."""
    pregunta = _pregunta(db, tema)
    for indice in range(3):
        _respuesta(db, usuario, tema, pregunta, correcta=False, hace_minutos=indice)
    for indice in range(3, 7):
        _respuesta(db, usuario, tema, pregunta, correcta=True, hace_minutos=indice)

    debilidad = adaptativo.detectar_debilidad(db, cfg, usuario_id=usuario.id, topic_id=tema.id)
    assert debilidad is not None
    assert debilidad.rule == "R1"
    assert debilidad.evidence["errors_last_10"] == 3


def test_dos_errores_no_bastan(db, cfg, usuario, tema) -> None:
    """Por debajo del umbral no se molesta al estudiante."""
    pregunta = _pregunta(db, tema)
    for indice in range(2):
        _respuesta(db, usuario, tema, pregunta, correcta=False, hace_minutos=indice)
    for indice in range(2, 6):
        _respuesta(db, usuario, tema, pregunta, correcta=True, hace_minutos=indice)
    assert adaptativo.detectar_debilidad(db, cfg, usuario_id=usuario.id, topic_id=tema.id) is None


def test_r3_puntaje_bajo_en_la_evaluacion(db, cfg, usuario, tema, ruta) -> None:
    """`R3_assessment_topic_lt = 60`: el tema falló en la prueba del módulo."""
    modulo = db.get(PathModule, tema.module_id)
    evaluacion = db.execute(
        sa.select(Assessment).where(Assessment.module_id == modulo.id)
    ).scalar_one()
    momento = utcnow()
    db.add(
        AssessmentAttempt(
            user_id=usuario.id,
            assessment_id=evaluacion.id,
            module_id=modulo.id,
            learning_path_id=ruta.id,
            attempt_no=1,
            question_count=10,
            question_ids=[],
            correct_count=4,
            score=40,
            effective_score=40,
            outcome=AssessmentOutcome.FAILED,
            status=AttemptStatus.SUBMITTED,
            per_topic_scores=[{"topic_id": str(tema.id), "pct": 40.0}],
            weak_topic_ids=[str(tema.id)],
            started_at=momento,
            submitted_at=momento,
            local_date=momento.date(),
            idempotency_key=f"asm-{uuid.uuid4()}",
        )
    )
    db.flush()

    debilidad = adaptativo.detectar_debilidad(db, cfg, usuario_id=usuario.id, topic_id=tema.id)
    assert debilidad is not None
    assert debilidad.rule == "R3"
    assert debilidad.evidence["assessment_topic_pct"] == 40.0


def test_r4_tarda_el_doble_de_lo_estimado(db, cfg, usuario, tema) -> None:
    """`R4`: dos respuestas por encima de `R4_time_multiplier` × lo estimado."""
    pregunta = _pregunta(db, tema, segundos=30)
    for indice in range(2):
        _respuesta(
            db, usuario, tema, pregunta, correcta=True, hace_minutos=indice, response_ms=90_000
        )
    _respuesta(db, usuario, tema, pregunta, correcta=True, hace_minutos=3, response_ms=5_000)

    debilidad = adaptativo.detectar_debilidad(db, cfg, usuario_id=usuario.id, topic_id=tema.id)
    assert debilidad is not None
    assert debilidad.rule == "R4"
    assert debilidad.evidence["slow_questions"] == 2


def test_r5_un_objetivo_entero_en_cero(db, cfg, usuario, tema) -> None:
    """`R5`: un objetivo concreto sin un solo acierto, aunque el resto vaya bien."""
    bueno = _pregunta(db, tema, objetivo="Objetivo dominado")
    malo = _pregunta(db, tema, objetivo="Objetivo atascado")
    for indice in range(8):
        _respuesta(db, usuario, tema, bueno, correcta=True, hace_minutos=indice)
    for indice in range(3):
        _respuesta(db, usuario, tema, malo, correcta=False, hace_minutos=30 + indice)

    debilidad = adaptativo.detectar_debilidad(db, cfg, usuario_id=usuario.id, topic_id=tema.id)
    assert debilidad is not None
    assert debilidad.rule == "R5"
    assert debilidad.evidence["objective"] == "Objetivo atascado"


def test_las_reglas_salen_de_game_configs(cfg) -> None:
    """Los umbrales son los de `mastery.weakness_rules` (§5.5)."""
    reglas = adaptativo.reglas_debilidad(cfg)
    assert reglas.r1_errors_in_last_10 == 3
    assert reglas.r2_accuracy_lt == 50
    assert reglas.r3_assessment_topic_lt == 60
    assert reglas.r4_time_multiplier == 2.0
    assert reglas.r5_objective_zero_of == 3


# ---------------------------------------------------------------------------
# Decisión
# ---------------------------------------------------------------------------


def test_sin_debilidad_no_se_hace_nada(db, cfg, usuario, tema) -> None:
    """Sin debilidad, ni repaso ni re-explicación: ni una llamada de IA."""
    decision = adaptativo.decidir(db, cfg, usuario_id=usuario.id, topic_id=tema.id)
    assert decision.accion == adaptativo.ACCION_NINGUNA
    assert decision.approach is None


def test_errores_repetidos_llevan_a_repaso(db, cfg, usuario, tema) -> None:
    """R1 se resuelve primero con un repaso dirigido: más barato y suele bastar."""
    pregunta = _pregunta(db, tema)
    for indice in range(3):
        _respuesta(db, usuario, tema, pregunta, correcta=False, hace_minutos=indice)

    decision = adaptativo.decidir(db, cfg, usuario_id=usuario.id, topic_id=tema.id)
    assert decision.accion == adaptativo.ACCION_REPASO
    assert decision.rule == "R1"
    assert decision.approach is None


def test_fallo_de_comprension_lleva_a_reexplicar(db, cfg, usuario, tema) -> None:
    """R3 y R5 son fallos de comprensión: toca explicarlo de otra forma."""
    debilidad = adaptativo.Debilidad(topic_id=tema.id, rule="R3", evidence={"assessment_topic_pct": 40})
    decision = adaptativo.decidir(
        db, cfg, usuario_id=usuario.id, topic_id=tema.id, debilidad=debilidad
    )
    assert decision.accion == adaptativo.ACCION_REEXPLICAR
    assert decision.approach == adaptativo.ENFOQUES[0]


def test_el_enfoque_rota(db) -> None:
    """El enfoque nunca se repite seguido: rota por la lista del contrato (§7.6)."""
    enfoques = [adaptativo.enfoque_siguiente(indice) for indice in range(len(adaptativo.ENFOQUES) + 1)]
    assert enfoques[: len(adaptativo.ENFOQUES)] == list(adaptativo.ENFOQUES)
    assert enfoques[-1] == adaptativo.ENFOQUES[0]
    assert len(set(adaptativo.ENFOQUES)) == len(adaptativo.ENFOQUES)


# ---------------------------------------------------------------------------
# Re-explicación (lo único que escribe la IA)
# ---------------------------------------------------------------------------


def test_reexplicar_genera_texto_con_citas(db, cfg, proveedor, usuario, tema) -> None:
    """La IA solo redacta: devuelve el texto, su enfoque y las citas del material."""
    decision = adaptativo.Decision(
        topic_id=tema.id, accion=adaptativo.ACCION_REEXPLICAR, rule="R3", approach="contrast"
    )
    explicacion = adaptativo.reexplicar(
        db, cfg, proveedor, topic_id=tema.id, usuario_id=usuario.id, decision=decision
    )

    assert explicacion.approach == "contrast"
    assert len(explicacion.body) > 40
    assert explicacion.check_question
    assert explicacion.citations
    assert all("chunk_id" in cita for cita in explicacion.citations)
    assert proveedor.uso_acumulado.llamadas == 1

    job = db.get(GenerationJob, explicacion.job_id)
    assert job is not None
    assert job.job_type is JobType.RE_EXPLANATION
    assert job.status is JobStatus.SUCCEEDED
    assert job.model_id == "claude-sonnet-5"

    procedencia = list(
        db.execute(
            sa.select(ContentProvenance).where(
                ContentProvenance.content_type == ProvenanceContentType.EXPLANATION,
                ContentProvenance.content_id == tema.id,
            )
        ).scalars()
    )
    assert procedencia
    assert all(fila.block_key.startswith("contrast:") for fila in procedencia)


def test_la_segunda_reexplicacion_cambia_de_enfoque(db, cfg, proveedor, usuario, tema) -> None:
    """Si hay que volver a explicarlo, se prueba otro ángulo, no el mismo."""
    primera = adaptativo.reexplicar(db, cfg, proveedor, topic_id=tema.id, usuario_id=usuario.id)
    segunda = adaptativo.reexplicar(db, cfg, proveedor, topic_id=tema.id, usuario_id=usuario.id)
    assert primera.approach != segunda.approach
    assert adaptativo.explicaciones_previas(db, usuario.id, tema.id) == 2


def test_reexplicar_respeta_la_cuota(db, cfg, proveedor, usuario, tema) -> None:
    """`ai.quotas_per_day.re_explanations = 10`: agotada, se corta con 429."""
    from app.core.errors import QuotaExceeded
    from app.modules.ai import costos

    for _ in range(10):
        db.add(
            GenerationJob(
                user_id=usuario.id,
                job_type=JobType.RE_EXPLANATION,
                status=JobStatus.SUCCEEDED,
                queued_at=utcnow(),
            )
        )
    db.flush()
    assert costos.estado_cuota(db, cfg, usuario.id, costos.CUOTA_REEXPLICACIONES).agotada is True

    with pytest.raises(QuotaExceeded):
        adaptativo.reexplicar(db, cfg, proveedor, topic_id=tema.id, usuario_id=usuario.id)
    assert proveedor.uso_acumulado.llamadas == 0


def test_tema_ajeno_no_existe(db, cfg, proveedor, tema) -> None:
    """§8.7: el tema de otro usuario devuelve 404."""
    from app.core.errors import NotFound

    with pytest.raises(NotFound):
        adaptativo.reexplicar(db, cfg, proveedor, topic_id=tema.id, usuario_id=uuid.uuid4())
