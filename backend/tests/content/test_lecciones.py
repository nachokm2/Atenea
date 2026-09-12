"""Ciclo de la lección: abrir, responder, completar y recompensar (§7.6, §7.10).

Todas estas pruebas usan la base real dentro de una transacción que se revierte.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa

from app.core.errors import AteneaError
from app.core.time import utcnow
from app.models.enums import AttemptResult, ModuleStatus, ProgressState
from app.models.progress import (
    QuestionAttempt,
    UserLessonProgress,
    UserModuleProgress,
)
from app.modules.content import lecciones, preguntas
from app.modules.progress.progreso import ServicioProgreso

pytestmark = pytest.mark.db


def _clave() -> str:
    """Una `Idempotency-Key` nueva (UUID v4, §8.3)."""
    return str(uuid.uuid4())


def _responder_todo(db, cfg, usuario, actividad_id, pool, *, correctas=True):
    """Responde todas las preguntas de la actividad y devuelve el último resultado."""
    respuestas = {
        "multiple_choice": {"option_id": "a"} if correctas else {"option_id": "b"},
        "true_false": {"value": correctas},
        "fill_blank": {"blanks": ["INNER JOIN" if correctas else "cross join"]},
        "matching": {"pairs": {"1": "a", "2": "b"} if correctas else {"1": "b", "2": "a"}},
        "ordering": {"order": ["x", "y", "z"] if correctas else ["z", "y", "x"]},
    }
    ultimo = None
    for pregunta in pool:
        ultimo = lecciones.responder(
            db,
            cfg,
            usuario,
            actividad_id,
            question_id=pregunta.id,
            response=respuestas[pregunta.question_type.value],
            response_ms=6400,
            idempotency_key=_clave(),
        )
    return ultimo


# ---------------------------------------------------------------------------
# Apertura de la actividad
# ---------------------------------------------------------------------------


def test_iniciar_leccion_abre_la_actividad_y_entrega_preguntas_sin_clave(db, cfg, usuario, contenido):
    """`POST /lessons/{id}/start` crea `study_activities` y sirve preguntas sin claves."""
    abierta = lecciones.iniciar_leccion(
        db, cfg, usuario, contenido.leccion1.id, idempotency_key=_clave()
    )

    assert abierta.creada is True
    assert abierta.activity.lesson_id == contenido.leccion1.id
    assert abierta.activity.topic_id == contenido.tema.id
    assert abierta.activity.knowledge_area_id == contenido.area.id
    assert len(abierta.questions) == 2
    for pregunta in abierta.questions:
        assert "answer_key" not in pregunta


def test_iniciar_leccion_es_idempotente(db, cfg, usuario, contenido):
    """La misma `Idempotency-Key` devuelve la misma actividad, no una nueva (§8.3)."""
    clave = _clave()
    primera = lecciones.iniciar_leccion(
        db, cfg, usuario, contenido.leccion1.id, idempotency_key=clave
    )
    segunda = lecciones.iniciar_leccion(
        db, cfg, usuario, contenido.leccion1.id, idempotency_key=clave
    )

    assert segunda.creada is False
    assert segunda.activity.id == primera.activity.id


def test_leccion_de_un_modulo_bloqueado_responde_module_locked(db, cfg, usuario, contenido):
    """El segundo módulo nace `LOCKED`: entrar da `409 MODULE_LOCKED` (§8.1)."""
    ServicioProgreso(db).asegurar_progreso_ruta(usuario.id, contenido.ruta.id)
    from app.models.content import Lesson, Topic

    tema2 = Topic(module_id=contenido.modulo2.id, position=1, title="GROUP BY", lesson_count=1)
    db.add(tema2)
    db.flush()
    leccion = Lesson(topic_id=tema2.id, position=1, title="Contar filas")
    db.add(leccion)
    db.flush()

    with pytest.raises(AteneaError) as excinfo:
        lecciones.obtener_leccion(db, usuario.id, leccion.id)

    assert excinfo.value.code == "MODULE_LOCKED"
    assert excinfo.value.status_code == 409


# ---------------------------------------------------------------------------
# Respuestas
# ---------------------------------------------------------------------------


def test_respuesta_correcta_produce_recibo_con_xp(db, cfg, usuario, contenido):
    """Acertar paga XP y el importe lo decide el motor, no este módulo (§7.10)."""
    abierta = lecciones.iniciar_leccion(
        db, cfg, usuario, contenido.leccion1.id, idempotency_key=_clave()
    )
    pregunta = contenido.preguntas_l1[0]

    resultado = lecciones.responder(
        db,
        cfg,
        usuario,
        abierta.activity.id,
        question_id=pregunta.id,
        response={"option_id": "a"},
        response_ms=6400,
        idempotency_key=_clave(),
    )

    assert resultado.attempt.result == AttemptResult.CORRECT
    assert resultado.attempt.is_correct is True
    assert resultado.receipt.xp is not None
    assert resultado.receipt.xp.amount > 0
    assert resultado.xp_awarded == resultado.receipt.xp.amount
    assert resultado.veredicto.explanation is not None


def test_repetir_la_respuesta_con_la_misma_clave_no_duplica_recompensas(db, cfg, usuario, contenido):
    """A6: el reintento devuelve el mismo recibo y no crea otra evidencia (§8.3)."""
    abierta = lecciones.iniciar_leccion(
        db, cfg, usuario, contenido.leccion1.id, idempotency_key=_clave()
    )
    pregunta = contenido.preguntas_l1[0]
    clave = _clave()

    primera = lecciones.responder(
        db, cfg, usuario, abierta.activity.id, question_id=pregunta.id,
        response={"option_id": "a"}, response_ms=6400, idempotency_key=clave,
    )
    segunda = lecciones.responder(
        db, cfg, usuario, abierta.activity.id, question_id=pregunta.id,
        response={"option_id": "a"}, response_ms=6400, idempotency_key=clave,
    )

    evidencias = db.execute(
        sa.select(sa.func.count(QuestionAttempt.id)).where(
            QuestionAttempt.study_activity_id == abierta.activity.id
        )
    ).scalar_one()
    assert evidencias == 1
    assert segunda.attempt.id == primera.attempt.id
    assert segunda.receipt.receipt_id == primera.receipt.receipt_id
    assert segunda.receipt.xp.amount == primera.receipt.xp.amount


def test_pregunta_ajena_a_la_actividad_responde_attempt_not_open(db, cfg, usuario, contenido):
    """A2: solo se puntúan las preguntas que la actividad presentó."""
    abierta = lecciones.iniciar_leccion(
        db, cfg, usuario, contenido.leccion1.id, idempotency_key=_clave()
    )

    with pytest.raises(AteneaError) as excinfo:
        lecciones.responder(
            db, cfg, usuario, abierta.activity.id,
            question_id=contenido.banco[0].id,
            response={"option_id": "a"}, idempotency_key=_clave(),
        )

    assert excinfo.value.code == "ATTEMPT_NOT_OPEN"


def test_pregunta_ya_acertada_responde_already_answered(db, cfg, usuario, contenido):
    """A2: una pregunta se puntúa una sola vez por intento."""
    abierta = lecciones.iniciar_leccion(
        db, cfg, usuario, contenido.leccion1.id, idempotency_key=_clave()
    )
    pregunta = contenido.preguntas_l1[0]
    lecciones.responder(
        db, cfg, usuario, abierta.activity.id, question_id=pregunta.id,
        response={"option_id": "a"}, response_ms=6400, idempotency_key=_clave(),
    )

    with pytest.raises(AteneaError) as excinfo:
        lecciones.responder(
            db, cfg, usuario, abierta.activity.id, question_id=pregunta.id,
            response={"option_id": "a"}, response_ms=6400, idempotency_key=_clave(),
        )

    assert excinfo.value.code == "ALREADY_ANSWERED"


def test_pregunta_fallada_admite_revancha_con_attempt_no_mayor(db, cfg, usuario, contenido):
    """Fallar no cierra la pregunta: el segundo intento pesa menos (§6.4)."""
    abierta = lecciones.iniciar_leccion(
        db, cfg, usuario, contenido.leccion1.id, idempotency_key=_clave()
    )
    pregunta = contenido.preguntas_l1[0]
    lecciones.responder(
        db, cfg, usuario, abierta.activity.id, question_id=pregunta.id,
        response={"option_id": "b"}, response_ms=6400, idempotency_key=_clave(),
    )

    segunda = lecciones.responder(
        db, cfg, usuario, abierta.activity.id, question_id=pregunta.id,
        response={"option_id": "a"}, response_ms=6400, idempotency_key=_clave(),
    )

    assert segunda.attempt.attempt_no == 2
    assert segunda.attempt.is_correct is True
    assert float(segunda.attempt.correctness_weight) == 0.5
    assert segunda.attempt.is_retry_of_failed is True


# ---------------------------------------------------------------------------
# Cierre de la actividad
# ---------------------------------------------------------------------------


def test_completar_sin_responder_todo_rechaza_por_la_regla_a7(db, cfg, usuario, contenido):
    """A7: sin todas las respuestas registradas no hay `LESSON_COMPLETED`."""
    abierta = lecciones.iniciar_leccion(
        db, cfg, usuario, contenido.leccion1.id, idempotency_key=_clave()
    )

    with pytest.raises(AteneaError) as excinfo:
        lecciones.completar(db, cfg, usuario, abierta.activity.id, idempotency_key=_clave())

    assert excinfo.value.status_code == 409
    assert "unanswered" in excinfo.value.details


def test_completar_la_leccion_devuelve_recibo_con_xp_y_oro(db, cfg, usuario, contenido):
    """`POST /activities/{id}/complete` devuelve el `RewardsReceipt` del motor (§7.10)."""
    inicio = utcnow() - timedelta(seconds=200)
    abierta = lecciones.iniciar_leccion(
        db, cfg, usuario, contenido.leccion1.id, idempotency_key=_clave(), momento=inicio
    )
    _responder_todo(db, cfg, usuario, abierta.activity.id, contenido.preguntas_l1)

    recibo = lecciones.completar(
        db, cfg, usuario, abierta.activity.id, idempotency_key=_clave()
    )

    assert recibo.event_type == "LESSON_COMPLETED"
    assert recibo.xp is not None and recibo.xp.amount > 0
    assert recibo.gold is not None and recibo.gold.amount > 0
    assert "xp" in recibo.presentation_order
    assert recibo.mastery_deltas, "el recibo debe traer el delta de dominio del tema"

    avance = db.execute(
        sa.select(UserLessonProgress).where(
            UserLessonProgress.user_id == usuario.id,
            UserLessonProgress.lesson_id == contenido.leccion1.id,
        )
    ).scalar_one()
    assert avance.status == ProgressState.COMPLETED
    assert avance.completion_count == 1


def test_completar_dos_veces_con_la_misma_clave_no_duplica_el_recibo(db, cfg, usuario, contenido):
    """§7.10 regla 4: el reintento devuelve el **mismo** `receipt_id` sin otorgar nada."""
    inicio = utcnow() - timedelta(seconds=200)
    abierta = lecciones.iniciar_leccion(
        db, cfg, usuario, contenido.leccion1.id, idempotency_key=_clave(), momento=inicio
    )
    _responder_todo(db, cfg, usuario, abierta.activity.id, contenido.preguntas_l1)
    clave = _clave()

    primero = lecciones.completar(db, cfg, usuario, abierta.activity.id, idempotency_key=clave)
    xp_tras_el_primero = primero.xp.amount
    segundo = lecciones.completar(db, cfg, usuario, abierta.activity.id, idempotency_key=clave)

    assert segundo.receipt_id == primero.receipt_id
    assert segundo.xp.amount == xp_tras_el_primero
    avance = db.execute(
        sa.select(UserLessonProgress).where(
            UserLessonProgress.user_id == usuario.id,
            UserLessonProgress.lesson_id == contenido.leccion1.id,
        )
    ).scalar_one()
    assert avance.completion_count == 1


def test_latido_acredita_tiempo_sin_dar_dominio(db, cfg, usuario, contenido):
    """El tiempo mide dedicación y nunca alimenta XP ni dominio (§1.1).

    El servidor jamás acredita más segundos de los que pasaron desde el latido
    anterior, así que la actividad se abre 60 s antes del latido.
    """
    abierta = lecciones.iniciar_leccion(
        db,
        cfg,
        usuario,
        contenido.leccion1.id,
        idempotency_key=_clave(),
        momento=utcnow() - timedelta(seconds=60),
    )

    resultado = lecciones.latido(db, cfg, usuario, abierta.activity.id, 30)

    assert resultado.acreditados == 30
    assert resultado.active_seconds == 30
    assert abierta.activity.active_seconds == 30


def test_abandonar_no_paga_nada(db, cfg, usuario, contenido):
    """Abandonar cierra la actividad sin recompensa (§7.6)."""
    abierta = lecciones.iniciar_leccion(
        db, cfg, usuario, contenido.leccion1.id, idempotency_key=_clave()
    )

    actividad = lecciones.abandonar(db, usuario, abierta.activity.id)

    assert actividad.status.value == "abandoned"
    assert actividad.counts_for_progress is False
    assert actividad.xp_awarded == 0


# ---------------------------------------------------------------------------
# Progresión del módulo
# ---------------------------------------------------------------------------


def test_completar_las_lecciones_y_aprobar_cierra_el_modulo_y_desbloquea_el_siguiente(
    db, cfg, usuario, contenido
):
    """A7: módulo completo = todas las lecciones **y** evaluación aprobada (§6.9).

    Al cerrarse, el siguiente módulo pasa de `LOCKED` a `AVAILABLE`.
    """
    from app.modules.content import evaluaciones

    for leccion, pool in (
        (contenido.leccion1, contenido.preguntas_l1),
        (contenido.leccion2, contenido.preguntas_l2),
    ):
        inicio = utcnow() - timedelta(seconds=200)
        abierta = lecciones.iniciar_leccion(
            db, cfg, usuario, leccion.id, idempotency_key=_clave(), momento=inicio
        )
        _responder_todo(db, cfg, usuario, abierta.activity.id, pool)
        lecciones.completar(db, cfg, usuario, abierta.activity.id, idempotency_key=_clave())

    avance_modulo = db.execute(
        sa.select(UserModuleProgress).where(
            UserModuleProgress.user_id == usuario.id,
            UserModuleProgress.module_id == contenido.modulo1.id,
        )
    ).scalar_one()
    assert avance_modulo.lessons_completed == 2
    assert avance_modulo.completed_at is None, "sin evaluación aprobada el módulo sigue abierto"

    intento = evaluaciones.iniciar_intento(
        db, cfg, usuario, contenido.evaluacion.id, idempotency_key=_clave()
    )
    for pregunta in intento.questions:
        evaluaciones.registrar_respuesta(
            db, cfg, usuario, intento.attempt.id,
            question_id=pregunta["question_id"],
            response={"option_id": "a"},
            response_ms=9000,
            idempotency_key=_clave(),
        )
    recibo = evaluaciones.enviar_intento(
        db, cfg, usuario, intento.attempt.id, idempotency_key=_clave()
    )

    assert recibo.assessment_result["passed"] is True
    db.refresh(avance_modulo)
    # `MASTERED` es el estado superior de `COMPLETED`: se alcanza cuando además
    # `M_mod >= 80` con la evaluación aprobada (§6.6).
    assert avance_modulo.status in (ModuleStatus.COMPLETED, ModuleStatus.MASTERED)
    assert avance_modulo.completed_at is not None

    siguiente = db.execute(
        sa.select(UserModuleProgress).where(
            UserModuleProgress.user_id == usuario.id,
            UserModuleProgress.module_id == contenido.modulo2.id,
        )
    ).scalar_one()
    assert siguiente.status == ModuleStatus.AVAILABLE
    assert siguiente.unlocked_at is not None
    assert any(u.type == "module" for u in recibo.unlocks)


# ---------------------------------------------------------------------------
# Repasos
# ---------------------------------------------------------------------------


def test_repaso_abre_actividad_con_preguntas_del_tema(db, cfg, usuario, contenido):
    """`POST /reviews/start` abre un repaso con las preguntas del tema (§7.6)."""
    ServicioProgreso(db).asegurar_progreso_ruta(usuario.id, contenido.ruta.id)

    abierta = lecciones.iniciar_repaso(
        db, cfg, usuario, contenido.tema.id, idempotency_key=_clave()
    )

    rango = cfg.obtener_json("mastery.review.questions")
    assert abierta.activity.activity_type.value == "review"
    assert 0 < len(abierta.questions) <= int(rango["max"])
    for pregunta in abierta.questions:
        assert "answer_key" not in pregunta


def test_el_muestreo_del_repaso_es_estable_para_la_misma_actividad(db, cfg, usuario, contenido):
    """El conjunto presentado se reconstruye igual: A7 puede comprobarse después."""
    ServicioProgreso(db).asegurar_progreso_ruta(usuario.id, contenido.ruta.id)
    clave = _clave()
    abierta = lecciones.iniciar_repaso(db, cfg, usuario, contenido.tema.id, idempotency_key=clave)

    servidas = [q["question_id"] for q in abierta.questions]
    reconstruidas = [
        q.id
        for q in preguntas.muestrear_repaso(
            db,
            cfg,
            contenido.tema.id,
            semilla=f"{usuario.id}:{contenido.tema.id}:{clave}",
        )
    ]

    assert servidas == reconstruidas
