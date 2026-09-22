"""Evaluación de módulo: entrada, muestreo, envío aprobado y reprobado (§7.7).

Reprobar **no** borra progreso: el intento devuelve temas débiles, sugerencias de
repaso y el enfriamiento, y el dominio ya ganado se conserva.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa

from app.core.errors import AteneaError
from app.core.time import utcnow
from app.models.content import Topic
from app.models.enums import AssessmentOutcome, AttemptStatus
from app.models.progress import AssessmentAttempt, UserModuleProgress
from app.modules.content import evaluaciones, preguntas
from app.modules.progress.progreso import ServicioProgreso

pytestmark = pytest.mark.db

#: Duración simulada del examen: por encima de `20 s x n_preguntas` (§6.9 A4).
SEGUNDOS_DE_EXAMEN = 300


def _clave() -> str:
    """Una `Idempotency-Key` nueva (UUID v4, §8.3)."""
    return str(uuid.uuid4())


def _responder(db, cfg, usuario, intento, *, aciertos: int) -> None:
    """Responde el intento con exactamente `aciertos` respuestas correctas.

    El intento se atrasa `SEGUNDOS_DE_EXAMEN` para superar el tiempo mínimo plausible
    de la regla A4 (§6.9: `20 s x n_preguntas`): la prueba no puede esperarlos de verdad.
    """
    fila = db.get(AssessmentAttempt, intento.attempt.id)
    fila.started_at = utcnow() - timedelta(seconds=SEGUNDOS_DE_EXAMEN)
    db.flush()
    for indice, pregunta in enumerate(intento.questions):
        correcta = indice < aciertos
        evaluaciones.registrar_respuesta(
            db,
            cfg,
            usuario,
            intento.attempt.id,
            question_id=pregunta["question_id"],
            response={"option_id": "a" if correcta else "b"},
            response_ms=9000,
            idempotency_key=_clave(),
        )


# ---------------------------------------------------------------------------
# Pantalla de entrada
# ---------------------------------------------------------------------------


def test_info_evaluacion_muestra_reglas_intentos_y_recompensa(db, cfg, usuario, contenido):
    """`GET /modules/{id}/assessment` trae reglas, intentos usados y recompensa (P11)."""
    ServicioProgreso(db).asegurar_progreso_ruta(usuario.id, contenido.ruta.id)

    info = evaluaciones.info_evaluacion(db, cfg, usuario, contenido.modulo1.id)

    assert info.can_start is True
    assert info.attempts_used == 0
    assert info.max_attempts_per_day == 2
    assert info.pass_score == 70.0
    assert info.reward_preview["xp"] == cfg.obtener_int("xp.assessment_passed")
    assert info.reward_preview["gold"] == cfg.obtener_int("gold.assessment_passed")
    assert info.assessment_attempts == 0


def test_info_evaluacion_trae_el_historico_de_intentos_de_por_vida(db, cfg, usuario, contenido):
    """`assessment_attempts` es el contador real de `UserModuleProgress`, no
    `attempts_used` (el de hoy): sin esto P11 nunca podía mostrar cuántas veces
    se ha rendido la prueba de este módulo en total."""
    intento = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )
    _responder(db, cfg, usuario, intento, aciertos=len(intento.questions))
    evaluaciones.enviar_intento(db, cfg, usuario, intento.attempt.id, idempotency_key=_clave())

    info = evaluaciones.info_evaluacion(db, cfg, usuario, contenido.modulo1.id)

    assert info.assessment_attempts == 1
    # Distinto de `attempts_used`, que es solo el de hoy y coincide aquí por
    # casualidad: no deben confundirse ni fusionarse en el mismo campo.
    assert info.attempts_used == info.assessment_attempts == 1


def test_info_evaluacion_trae_los_temas_del_modulo_en_orden(db, cfg, usuario, contenido):
    """P11 «Qué entra»: `topic_titles` trae los temas del módulo, en orden (§7.7)."""
    ServicioProgreso(db).asegurar_progreso_ruta(usuario.id, contenido.ruta.id)

    otro_tema = Topic(
        module_id=contenido.modulo1.id, position=2, title="Subconsultas", lesson_count=1
    )
    db.add(otro_tema)
    db.flush()

    info = evaluaciones.info_evaluacion(db, cfg, usuario, contenido.modulo1.id)

    assert info.topic_titles == ["JOINs", "Subconsultas"]


def test_info_de_un_modulo_bloqueado_responde_module_locked(db, cfg, usuario, contenido):
    """Entrar a la prueba de un módulo bloqueado da `409 MODULE_LOCKED` (§8.1)."""
    ServicioProgreso(db).asegurar_progreso_ruta(usuario.id, contenido.ruta.id)

    with pytest.raises(AteneaError) as excinfo:
        evaluaciones.info_evaluacion(db, cfg, usuario, contenido.modulo2.id)

    assert excinfo.value.code == "MODULE_LOCKED"


# ---------------------------------------------------------------------------
# Muestreo del banco
# ---------------------------------------------------------------------------


def test_iniciar_intento_muestrea_el_banco_sin_claves(db, cfg, usuario, contenido):
    """El intento entrega `question_count` preguntas y ninguna trae `answer_key`."""
    intento = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )

    assert intento.attempt.attempt_no == 1
    assert len(intento.questions) == contenido.evaluacion.question_count
    for pregunta in intento.questions:
        assert "answer_key" not in pregunta


def test_iniciar_intento_es_idempotente(db, cfg, usuario, contenido):
    """La misma clave devuelve el mismo intento con las mismas preguntas (§8.3)."""
    clave = _clave()
    primero = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=clave
    )
    segundo = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=clave
    )

    assert segundo.creado is False
    assert segundo.attempt.id == primero.attempt.id
    assert [q["question_id"] for q in segundo.questions] == [
        q["question_id"] for q in primero.questions
    ]


def test_el_segundo_intento_respeta_el_solapamiento_maximo(db, cfg, usuario, contenido):
    """§7.7: como mucho el 30 % de las preguntas se repite respecto del intento anterior."""
    primero = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )
    _responder(db, cfg, usuario, primero, aciertos=0)
    evaluaciones.enviar_intento(db, cfg, usuario, primero.attempt.id, idempotency_key=_clave())

    fila = db.get(AssessmentAttempt, primero.attempt.id)
    fila.cooldown_until = None  # el enfriamiento se prueba aparte
    db.flush()

    segundo = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )

    previas = [uuid.UUID(str(x)) for x in primero.attempt.question_ids]
    nuevas = [q["question_id"] for q in segundo.questions]
    tope = float(cfg.obtener_decimal("mastery.assessment.max_overlap"))
    assert preguntas.solapamiento(nuevas, previas) <= tope


# ---------------------------------------------------------------------------
# Respuestas
# ---------------------------------------------------------------------------


def test_la_respuesta_del_examen_da_feedback_minimo(db, cfg, usuario, contenido):
    """§7.7: correcto/incorrecto y el avance, **sin explicación**."""
    intento = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )

    registro = evaluaciones.registrar_respuesta(
        db,
        cfg,
        usuario,
        intento.attempt.id,
        question_id=intento.questions[0]["question_id"],
        response={"option_id": "a"},
        response_ms=9000,
        idempotency_key=_clave(),
    )

    assert registro.recorded is True
    assert registro.index == 1
    assert registro.total == contenido.evaluacion.question_count
    assert registro.is_correct is True
    assert not hasattr(registro, "explanation")


def test_no_se_puede_responder_dos_veces_la_misma_pregunta(db, cfg, usuario, contenido):
    """En un examen no hay revancha: `409 ALREADY_ANSWERED`."""
    intento = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )
    pregunta_id = intento.questions[0]["question_id"]
    evaluaciones.registrar_respuesta(
        db, cfg, usuario, intento.attempt.id, question_id=pregunta_id,
        response={"option_id": "a"}, idempotency_key=_clave(),
    )

    with pytest.raises(AteneaError) as excinfo:
        evaluaciones.registrar_respuesta(
            db, cfg, usuario, intento.attempt.id, question_id=pregunta_id,
            response={"option_id": "b"}, idempotency_key=_clave(),
        )

    assert excinfo.value.code == "ALREADY_ANSWERED"


# ---------------------------------------------------------------------------
# Envío: aprobado
# ---------------------------------------------------------------------------


def test_evaluacion_aprobada_paga_y_actualiza_dominio(db, cfg, usuario, contenido):
    """Aprobar devuelve el recibo con XP, oro y `assessment_result` (§7.7, §7.10)."""
    intento = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )
    _responder(db, cfg, usuario, intento, aciertos=len(intento.questions))

    recibo = evaluaciones.enviar_intento(
        db, cfg, usuario, intento.attempt.id, idempotency_key=_clave()
    )

    assert recibo.event_type == "ASSESSMENT_COMPLETED"
    assert recibo.xp is not None and recibo.xp.amount > 0
    assert recibo.gold is not None and recibo.gold.amount > 0

    resultado = recibo.assessment_result
    assert resultado["passed"] is True
    assert resultado["score_pct"] == 100.0
    assert resultado["outcome"] == AssessmentOutcome.PASSED_PERFECT.value
    assert resultado["weak_topics"] == []
    assert resultado["cooldown_until"] is None

    avance = db.execute(
        sa.select(UserModuleProgress).where(
            UserModuleProgress.user_id == usuario.id,
            UserModuleProgress.module_id == contenido.modulo1.id,
        )
    ).scalar_one()
    assert avance.assessment_passed_at is not None
    assert float(avance.assessment_best_score) == 100.0
    assert float(avance.assessment_best_effective) == 100.0
    assert avance.assessment_attempts == 1


def test_reenviar_con_la_misma_clave_devuelve_el_mismo_recibo(db, cfg, usuario, contenido):
    """§7.10 regla 4: el reintento no vuelve a otorgar nada."""
    intento = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )
    _responder(db, cfg, usuario, intento, aciertos=len(intento.questions))
    clave = _clave()

    primero = evaluaciones.enviar_intento(
        db, cfg, usuario, intento.attempt.id, idempotency_key=clave
    )
    segundo = evaluaciones.enviar_intento(
        db, cfg, usuario, intento.attempt.id, idempotency_key=clave
    )

    assert segundo.receipt_id == primero.receipt_id
    assert segundo.xp.amount == primero.xp.amount
    avance = db.execute(
        sa.select(UserModuleProgress).where(
            UserModuleProgress.user_id == usuario.id,
            UserModuleProgress.module_id == contenido.modulo1.id,
        )
    ).scalar_one()
    assert avance.assessment_attempts == 1


# ---------------------------------------------------------------------------
# Envío: reprobado
# ---------------------------------------------------------------------------


def test_evaluacion_reprobada_no_borra_progreso_y_sugiere_repaso(db, cfg, usuario, contenido):
    """Reprobar deja enfriamiento, temas débiles y sugerencias, sin tocar el dominio ganado."""
    intento = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )
    _responder(db, cfg, usuario, intento, aciertos=0)

    recibo = evaluaciones.enviar_intento(
        db, cfg, usuario, intento.attempt.id, idempotency_key=_clave()
    )

    resultado = recibo.assessment_result
    assert resultado["passed"] is False
    assert resultado["outcome"] == AssessmentOutcome.FAILED.value
    assert resultado["score_pct"] == 0.0
    assert resultado["cooldown_until"] is not None
    assert resultado["weak_topics"], "reprobar debe señalar los temas débiles"
    assert resultado["review_suggestions"], "reprobar debe proponer un repaso"

    fila = db.get(AssessmentAttempt, intento.attempt.id)
    assert fila.status == AttemptStatus.SUBMITTED
    assert fila.cooldown_until is not None

    avance = db.execute(
        sa.select(UserModuleProgress).where(
            UserModuleProgress.user_id == usuario.id,
            UserModuleProgress.module_id == contenido.modulo1.id,
        )
    ).scalar_one()
    assert avance.assessment_passed_at is None
    assert avance.completed_at is None
    assert avance.assessment_attempts == 1


def test_el_enfriamiento_bloquea_el_siguiente_intento(db, cfg, usuario, contenido):
    """Tras reprobar, reintentar da `409 ASSESSMENT_COOLDOWN` con su detalle (§8.1)."""
    intento = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )
    _responder(db, cfg, usuario, intento, aciertos=0)
    evaluaciones.enviar_intento(db, cfg, usuario, intento.attempt.id, idempotency_key=_clave())

    with pytest.raises(AteneaError) as excinfo:
        evaluaciones.iniciar_intento(
            db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
        )

    assert excinfo.value.code == "ASSESSMENT_COOLDOWN"
    assert "cooldown_until" in excinfo.value.details
    assert excinfo.value.details["can_waive_with_review"] is True


def test_el_tope_diario_de_intentos_se_respeta(db, cfg, usuario, contenido):
    """Con el enfriamiento anulado sigue mandando `mastery.assessment.max_attempts_per_day`."""
    for _ in range(2):
        intento = evaluaciones.iniciar_intento(
            db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
        )
        _responder(db, cfg, usuario, intento, aciertos=0)
        evaluaciones.enviar_intento(db, cfg, usuario, intento.attempt.id, idempotency_key=_clave())
        fila = db.get(AssessmentAttempt, intento.attempt.id)
        fila.cooldown_until = None
        db.flush()

    with pytest.raises(AteneaError) as excinfo:
        evaluaciones.iniciar_intento(
            db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
        )

    assert excinfo.value.code == "ASSESSMENT_ATTEMPT_LIMIT"
    assert excinfo.value.details["max_attempts_per_day"] == 2


def test_la_penalizacion_por_reintento_baja_el_puntaje_efectivo(db, cfg, usuario, contenido):
    """§6.6: `E_mod = max_k(score_k − 0.05·(k−1))`, en escala 0–100."""
    primero = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )
    _responder(db, cfg, usuario, primero, aciertos=0)
    evaluaciones.enviar_intento(db, cfg, usuario, primero.attempt.id, idempotency_key=_clave())
    fila = db.get(AssessmentAttempt, primero.attempt.id)
    fila.cooldown_until = None
    db.flush()

    segundo = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )
    _responder(db, cfg, usuario, segundo, aciertos=len(segundo.questions))
    recibo = evaluaciones.enviar_intento(
        db, cfg, usuario, segundo.attempt.id, idempotency_key=_clave()
    )

    assert recibo.assessment_result["score_pct"] == 100.0
    assert recibo.assessment_result["effective_score_pct"] == 95.0


# ---------------------------------------------------------------------------
# Revisión posterior
# ---------------------------------------------------------------------------


def test_la_revision_trae_explicacion_pero_nunca_la_clave(db, cfg, usuario, contenido):
    """§7.7: la revisión muestra la explicación; `answer_key` no sale nunca (§8.7)."""
    intento = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )
    _responder(db, cfg, usuario, intento, aciertos=1)
    evaluaciones.enviar_intento(db, cfg, usuario, intento.attempt.id, idempotency_key=_clave())

    revision = evaluaciones.revision_intento(db, usuario, intento.attempt.id)

    assert len(revision.items) == contenido.evaluacion.question_count
    for item in revision.items:
        assert "answer_key" not in item
        assert item["explanation"] is not None
    assert revision.items[0]["is_correct"] is True
