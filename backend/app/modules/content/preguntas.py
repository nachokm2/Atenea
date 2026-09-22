"""Preguntas: vista pública sin clave y muestreo de bancos.

Contrato §3.2 (`questions`, `assessment_questions`), §5.5 (`mastery.assessment.*`,
`mastery.review.questions`), §7.6 y §7.7.

**Única puerta de salida.** Toda pregunta que viaja al cliente pasa por
`vista_publica()`, que nunca copia `answer_key` (§8.7). No existe ninguna otra
función en este paquete que serialice una `Question`.

**Muestreo del banco de la evaluación.** §7.7 exige solapamiento ≤ 30 % con el
intento anterior (`mastery.assessment.max_overlap`). El muestreo es **determinista**
respecto del intento: la misma semilla (usuario, evaluación, número de intento)
produce el mismo conjunto, de modo que reintentar la misma petición idempotente
devuelve exactamente las mismas preguntas.
"""

from __future__ import annotations

import random
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.content import Assessment, AssessmentQuestion, Question, Topic
from app.models.enums import ContentStatus
from app.modules.gamification.servicio_config import ServicioConfig

#: Claves de `questions.body` que revelarían la solución: se recortan en la vista pública.
CLAVES_SENSIBLES_DEL_CUERPO: frozenset[str] = frozenset(
    {"rubric", "rubrica", "solution", "solucion", "expected", "expected_rows", "expected_result"}
)


def cuerpo_publico(body: dict | None) -> dict[str, Any]:
    """Copia de `questions.body` sin las claves que contienen la solución."""
    return {k: v for k, v in dict(body or {}).items() if k not in CLAVES_SENSIBLES_DEL_CUERPO}


def vista_publica(pregunta: Question, *, position: int | None = None) -> dict[str, Any]:
    """Representación de una pregunta apta para el cliente. **Nunca** incluye `answer_key`.

    Tampoco incluye `explanation`: la explicación se entrega *después* de responder,
    en `AnswerResultOut` (§7.6).
    """
    return {
        "question_id": pregunta.id,
        "question_type": pregunta.question_type,
        "difficulty": pregunta.difficulty,
        "stem": pregunta.stem,
        "body": cuerpo_publico(pregunta.body),
        "learning_objective": pregunta.learning_objective,
        "estimated_seconds": int(pregunta.estimated_seconds or 0),
        "topic_id": pregunta.topic_id,
        "position": position,
    }


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------


def preguntas_de_leccion(db: Session, lesson_id: uuid.UUID) -> list[Question]:
    """Preguntas intercaladas de una lección, en orden estable y sin las reportadas."""
    return list(
        db.execute(
            sa.select(Question)
            .where(
                Question.lesson_id == lesson_id,
                Question.content_status != ContentStatus.FLAGGED,
                Question.is_flagged.is_(False),
            )
            .order_by(Question.created_at, Question.id)
        ).scalars()
    )


def preguntas_de_tema(db: Session, topic_id: uuid.UUID) -> list[Question]:
    """Pool completo del tema, sin las preguntas reportadas (§3.2)."""
    return list(
        db.execute(
            sa.select(Question)
            .where(
                Question.topic_id == topic_id,
                Question.content_status != ContentStatus.FLAGGED,
                Question.is_flagged.is_(False),
            )
            .order_by(Question.created_at, Question.id)
        ).scalars()
    )


def banco_de_modulo(db: Session, module_id: uuid.UUID) -> list[Question]:
    """Pool completo del módulo: las preguntas de todos sus temas (§7.6 desafío).

    A diferencia del banco de la evaluación (`assessment_questions`, una tabla
    propia con posiciones fijas), el desafío no tiene banco dedicado: reutiliza
    el mismo pool de preguntas por tema que ya alimenta lección y repaso.
    """
    return list(
        db.execute(
            sa.select(Question)
            .join(Topic, Topic.id == Question.topic_id)
            .where(
                Topic.module_id == module_id,
                Question.content_status != ContentStatus.FLAGGED,
                Question.is_flagged.is_(False),
            )
            .order_by(Topic.position, Question.created_at, Question.id)
        ).scalars()
    )


def muestrear_desafio(
    db: Session, cfg: ServicioConfig, module_id: uuid.UUID, *, semilla: str
) -> list[Question]:
    """Selecciona las preguntas del desafío del módulo (§7.6, `content.challenge_questions`)."""
    banco = banco_de_modulo(db, module_id)
    cantidad = min(len(banco), cfg.obtener_int("content.challenge_questions"))
    if cantidad >= len(banco):
        return banco
    azar = random.Random(semilla)
    return azar.sample(banco, cantidad)


def banco_de_evaluacion(db: Session, assessment_id: uuid.UUID) -> list[Question]:
    """Preguntas activas del banco de una evaluación (§3.2 `assessment_questions`)."""
    return list(
        db.execute(
            sa.select(Question)
            .join(AssessmentQuestion, AssessmentQuestion.question_id == Question.id)
            .where(
                AssessmentQuestion.assessment_id == assessment_id,
                AssessmentQuestion.is_active.is_(True),
                Question.content_status != ContentStatus.FLAGGED,
                Question.is_flagged.is_(False),
            )
            .order_by(AssessmentQuestion.position, Question.id)
        ).scalars()
    )


def por_id(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, Question]:
    """Mapa `{id: Question}` para resolver una lista de preguntas en una consulta."""
    if not ids:
        return {}
    filas = db.execute(sa.select(Question).where(Question.id.in_(ids))).scalars()
    return {fila.id: fila for fila in filas}


# ---------------------------------------------------------------------------
# Muestreo
# ---------------------------------------------------------------------------


def tamano_de_repaso(cfg: ServicioConfig, disponibles: int) -> int:
    """Número de preguntas de un repaso: entre `min` y `max` de `mastery.review.questions`."""
    rango = cfg.obtener_json("mastery.review.questions")
    maximo = int(rango["max"])
    # `min` es el tamaño deseable; si el tema no tiene tantas preguntas se hace un
    # repaso más corto antes que negárselo al usuario.
    return max(0, min(int(disponibles), maximo))


def muestrear_repaso(
    db: Session,
    cfg: ServicioConfig,
    topic_id: uuid.UUID,
    *,
    semilla: str,
) -> list[Question]:
    """Selecciona las 4–8 preguntas de un repaso del tema (§7.6, `mastery.review.questions`)."""
    pool = preguntas_de_tema(db, topic_id)
    cantidad = tamano_de_repaso(cfg, len(pool))
    if cantidad >= len(pool):
        return pool
    azar = random.Random(semilla)
    return azar.sample(pool, cantidad)


def maximo_repetidas(cantidad: int, max_overlap: float) -> int:
    """Cuántas preguntas del intento anterior pueden repetirse (§7.7: ≤ 30 %)."""
    return int(cantidad * float(max_overlap))


def muestrear_banco(
    banco: list[Question],
    *,
    cantidad: int,
    previas: list[uuid.UUID],
    max_overlap: float,
    semilla: str,
) -> list[Question]:
    """Muestrea `cantidad` preguntas del banco respetando el solapamiento máximo.

    Prioriza las preguntas que **no** salieron en el intento anterior. Solo cuando el
    banco no da para más se completan con repetidas, hasta el tope de solapamiento;
    si ni así alcanza (banco más pequeño que el examen) se devuelve todo lo que hay,
    porque negar el intento sería peor que repetir.
    """
    if cantidad <= 0 or not banco:
        return []
    vistas = set(previas)
    azar = random.Random(semilla)

    frescas = [q for q in banco if q.id not in vistas]
    repetibles = [q for q in banco if q.id in vistas]
    azar.shuffle(frescas)
    azar.shuffle(repetibles)

    seleccion = frescas[:cantidad]
    faltan = cantidad - len(seleccion)
    if faltan > 0:
        tope = maximo_repetidas(cantidad, max_overlap)
        seleccion.extend(repetibles[: min(faltan, tope)])
    return seleccion[:cantidad]


def muestrear_evaluacion(
    db: Session,
    cfg: ServicioConfig,
    evaluacion: Assessment,
    *,
    previas: list[uuid.UUID],
    semilla: str,
) -> list[Question]:
    """Banco muestreado para un intento de evaluación de módulo (§7.7)."""
    banco = banco_de_evaluacion(db, evaluacion.id)
    cantidad = int(evaluacion.question_count or cfg.obtener_int("mastery.assessment.question_count"))
    return muestrear_banco(
        banco,
        cantidad=cantidad,
        previas=previas,
        max_overlap=float(cfg.obtener_decimal("mastery.assessment.max_overlap")),
        semilla=semilla,
    )


def solapamiento(seleccion: list[uuid.UUID], previas: list[uuid.UUID]) -> float:
    """Fracción de la selección que ya salió en el intento anterior (0–1)."""
    if not seleccion:
        return 0.0
    vistas = set(previas)
    return len([q for q in seleccion if q in vistas]) / len(seleccion)


__all__ = [
    "CLAVES_SENSIBLES_DEL_CUERPO",
    "banco_de_evaluacion",
    "banco_de_modulo",
    "cuerpo_publico",
    "maximo_repetidas",
    "muestrear_banco",
    "muestrear_desafio",
    "muestrear_evaluacion",
    "muestrear_repaso",
    "por_id",
    "preguntas_de_leccion",
    "preguntas_de_tema",
    "solapamiento",
    "tamano_de_repaso",
    "vista_publica",
]
