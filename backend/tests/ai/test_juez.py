"""Juez de respuestas abiertas: veredicto estructurado, escalado y degradación."""

from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.core.time import utcnow
from app.models.content import Lesson, PathModule, Question, Topic
from app.models.enums import (
    AttemptResult,
    ContentStatus,
    DifficultyLevel,
    EvaluationMethod,
    JobStatus,
    JobType,
    QuestionType,
)
from app.models.ingestion import GenerationJob
from app.modules.ai import arquitecto_ruta as fase_a, juez

RUBRICA = {
    "criteria": [
        {"key": "c1", "text": "Define correctamente el concepto de índice", "weight": 50},
        {"key": "c2", "text": "Menciona el coste de escritura que introduce", "weight": 50},
    ],
    "max_words": 80,
}


@pytest.fixture
def pregunta_abierta(db, cfg, proveedor, ruta) -> Question:
    """Pregunta `open_short` con rúbrica, colgada de un tema real."""
    fase_a.disenar_ruta(db, cfg, proveedor, learning_path_id=ruta.id, usuario_id=ruta.user_id)
    proveedor.reiniciar_contador()
    tema = db.execute(
        sa.select(Topic)
        .join(PathModule, PathModule.id == Topic.module_id)
        .where(PathModule.learning_path_id == ruta.id)
        .order_by(Topic.position)
        .limit(1)
    ).scalar_one()
    leccion = Lesson(topic_id=tema.id, position=1, title="Índices", content_status=ContentStatus.READY)
    db.add(leccion)
    db.flush()
    fila = Question(
        topic_id=tema.id,
        lesson_id=leccion.id,
        question_type=QuestionType.OPEN_SHORT,
        difficulty=DifficultyLevel.MEDIUM,
        stem="¿Qué es un índice y qué coste tiene?",
        body={"rubric": RUBRICA},
        answer_key={
            "reference_answer": "Un índice acelera la búsqueda y encarece la escritura.",
            "must_include": ["indice", "escritura"],
        },
        explanation="Un índice acelera la lectura a cambio de encarecer la escritura.",
        content_status=ContentStatus.READY,
    )
    db.add(fila)
    db.flush()
    return fila


def test_respuesta_demasiado_corta_no_gasta_una_llamada(
    db, cfg, proveedor, pregunta_abierta, usuario
) -> None:
    """`ai.judge.min_words`: por debajo del mínimo se resuelve sin IA."""
    resultado = juez.juzgar_respuesta(
        db, cfg, proveedor, question=pregunta_abierta, texto="no sé", usuario_id=usuario.id
    )
    assert resultado.result is AttemptResult.INCORRECT
    assert resultado.evaluation_method is EvaluationMethod.DETERMINISTIC
    assert resultado.partial_score == 0.0
    assert resultado.payload["reason"] == "too_short"
    assert proveedor.uso_acumulado.llamadas == 0


def test_veredicto_estructurado(db, cfg, proveedor, pregunta_abierta, usuario) -> None:
    """Una respuesta razonada devuelve un veredicto completo y trazado."""
    texto = (
        "Un indice define una estructura que acelera la busqueda de filas y menciona "
        "el coste de escritura que introduce al mantenerlo actualizado correctamente"
    )
    resultado = juez.juzgar_respuesta(
        db, cfg, proveedor, question=pregunta_abierta, texto=texto, usuario_id=usuario.id
    )

    assert resultado.evaluation_method is EvaluationMethod.LLM_JUDGE
    assert resultado.result in (AttemptResult.CORRECT, AttemptResult.PARTIAL)
    assert 0.0 <= resultado.partial_score <= 100.0
    assert 0.0 <= resultado.confidence <= 1.0
    assert resultado.feedback
    assert {criterio["key"] for criterio in resultado.payload["criteria"]} == {"c1", "c2"}
    assert resultado.payload["model_id"] == "claude-haiku-4-5"
    assert resultado.escalado is False

    job = db.get(GenerationJob, resultado.job_id)
    assert job is not None
    assert job.job_type is JobType.ANSWER_JUDGEMENT
    assert job.status is JobStatus.SUCCEEDED
    assert job.input_tokens > 0


def test_escala_cuando_falta_confianza(db, cfg, proveedor, pregunta_abierta, usuario) -> None:
    """D20: bajo `min_confidence` se escala al modelo mayor y se da el beneficio de la duda."""
    resultado = juez.juzgar_respuesta(
        db,
        cfg,
        proveedor,
        question=pregunta_abierta,
        texto="acelera la busqueda",
        usuario_id=usuario.id,
    )
    assert resultado.escalado is True
    assert proveedor.uso_acumulado.llamadas == 2
    assert proveedor.uso_acumulado.por_tarea["judge"] == 1
    assert proveedor.uso_acumulado.por_tarea["judge_escalation"] == 1
    assert resultado.payload["benefit_of_doubt"] is True
    # Beneficio de la duda: nunca por debajo de `benefit_of_doubt_score`.
    assert resultado.partial_score >= 60.0
    assert resultado.result is not AttemptResult.INCORRECT


def test_degradacion_elegante_sin_presupuesto(
    db, cfg, proveedor, pregunta_abierta, usuario
) -> None:
    """Con el presupuesto agotado la respuesta espera revisión, no revienta."""
    db.add(
        GenerationJob(
            user_id=usuario.id,
            job_type=JobType.PATH_DESIGN,
            status=JobStatus.SUCCEEDED,
            cost_usd=Decimal("30.000000"),
            queued_at=utcnow(),
        )
    )
    db.flush()

    resultado = juez.juzgar_respuesta(
        db,
        cfg,
        proveedor,
        question=pregunta_abierta,
        texto="Un indice acelera la busqueda de filas y encarece la escritura del dato",
        usuario_id=usuario.id,
    )
    assert resultado.result is AttemptResult.NEEDS_REVIEW
    assert resultado.evaluation_method is EvaluationMethod.PENDING
    assert resultado.payload["reason"] == "ai_budget_exceeded"
    assert proveedor.uso_acumulado.llamadas == 0


def test_parametros_del_juez_salen_de_game_configs(cfg) -> None:
    """Los umbrales son los de `ai.judge`, no literales del código."""
    parametros = juez.parametros_juez(cfg)
    assert parametros.correct_score == 70
    assert parametros.partial_score == 40
    assert parametros.min_confidence == 0.6
    assert parametros.benefit_of_doubt_score == 60
    assert parametros.min_words == 3
