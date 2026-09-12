"""Adaptación: detección **determinista** de debilidad y decisión de repaso o re-explicación.

La regla del brief se aplica aquí en su forma más estricta: **la IA solo redacta la
explicación alternativa**. Detectar que un estudiante está atascado, decidir si toca
repasar o volver a explicar, y elegir el enfoque son decisiones deterministas del
servidor, calculadas sobre `question_attempts` y `assessment_attempts`.

Reglas de debilidad (`mastery.weakness_rules`, CONTRACT.md §5.5; la regla que dispara se
guarda en `user_topic_progress.weak_rule`):

| Regla | Condición |
|---|---|
| `R1` | `R1_errors_in_last_10` errores en las últimas 10 respuestas del tema |
| `R2` | precisión < `R2_accuracy_lt` % con al menos `R2_min_attempts` respuestas |
| `R3` | puntaje del tema en la última evaluación < `R3_assessment_topic_lt` % |
| `R4` | `R4_min_questions` respuestas que tardaron más de `R4_time_multiplier` × lo estimado |
| `R5` | un objetivo de aprendizaje con 0 aciertos en sus últimas `R5_objective_zero_of` |

`progress` es el dueño de `WEAKNESS_DETECTED` y de escribir `user_topic_progress`: este
módulo **calcula y decide**, no persiste progreso.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.logging import get_logger
from app.models.content import LearningPath, PathModule, Question, Topic
from app.models.enums import JobStatus, JobType, ProvenanceContentType, ProvenanceOrigin
from app.models.ingestion import ContentProvenance
from app.models.progress import AssessmentAttempt, QuestionAttempt, UserTopicProgress
from app.modules.ai import costos
from app.modules.ai.arquitecto_ruta import (
    parametros_recuperacion,
    recuperar,
    registrar_procedencia,
)
from app.modules.ai.esquemas_salida import SalidaExplicacion, esquema_estricto, generar_validado
from app.modules.ai.proveedor import (
    TAREA_REEXPLICACION,
    FragmentoContexto,
    ProveedorIA,
    SolicitudIA,
    modelo_para_tarea,
    plantilla_para_tarea,
)
from app.modules.gamification.servicio_config import ServicioConfig

logger = get_logger(__name__)

#: Enfoques de re-explicación, en orden de rotación (§7.6: "enfoque rotativo").
ENFOQUES: Final[tuple[str, ...]] = (
    "analogy",
    "step_by_step",
    "example_first",
    "contrast",
    "from_scratch",
)

#: Acciones que puede decidir el adaptativo.
ACCION_NINGUNA: Final[str] = "none"
ACCION_REPASO: Final[str] = "review"
ACCION_REEXPLICAR: Final[str] = "reexplain"


# ---------------------------------------------------------------------------
# Parámetros
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReglasDebilidad:
    """Valores de `mastery.weakness_rules` (§5.5)."""

    r1_errors_in_last_10: int = 3
    r2_accuracy_lt: float = 50.0
    r2_min_attempts: int = 5
    r3_assessment_topic_lt: float = 60.0
    r4_time_multiplier: float = 2.0
    r4_min_questions: int = 2
    r5_objective_zero_of: int = 3


def reglas_debilidad(cfg: ServicioConfig | None) -> ReglasDebilidad:
    """Lee `mastery.weakness_rules` de `game_configs`."""
    if cfg is None:
        return ReglasDebilidad()
    crudo = cfg.obtener_json("mastery.weakness_rules", {}) or {}
    base = ReglasDebilidad()
    return ReglasDebilidad(
        r1_errors_in_last_10=int(crudo.get("R1_errors_in_last_10", base.r1_errors_in_last_10)),
        r2_accuracy_lt=float(crudo.get("R2_accuracy_lt", base.r2_accuracy_lt)),
        r2_min_attempts=int(crudo.get("R2_min_attempts", base.r2_min_attempts)),
        r3_assessment_topic_lt=float(
            crudo.get("R3_assessment_topic_lt", base.r3_assessment_topic_lt)
        ),
        r4_time_multiplier=float(crudo.get("R4_time_multiplier", base.r4_time_multiplier)),
        r4_min_questions=int(crudo.get("R4_min_questions", base.r4_min_questions)),
        r5_objective_zero_of=int(crudo.get("R5_objective_zero_of", base.r5_objective_zero_of)),
    )


# ---------------------------------------------------------------------------
# Detección
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Debilidad:
    """Debilidad detectada en un tema, con la regla y su evidencia."""

    topic_id: uuid.UUID
    rule: str
    evidence: dict[str, Any] = field(default_factory=dict)


def _ultimas_respuestas(
    db: Session, usuario_id: uuid.UUID, topic_id: uuid.UUID, limite: int
) -> list[QuestionAttempt]:
    """Últimas respuestas del usuario en ese tema, de la más reciente a la más antigua."""
    filas = db.execute(
        sa.select(QuestionAttempt)
        .where(
            QuestionAttempt.user_id == usuario_id,
            QuestionAttempt.topic_id == topic_id,
            QuestionAttempt.counts_for_mastery.is_(True),
        )
        .order_by(QuestionAttempt.answered_at.desc(), QuestionAttempt.id.desc())
        .limit(limite)
    ).scalars()
    return list(filas)


def detectar_debilidad(
    db: Session,
    cfg: ServicioConfig | None,
    *,
    usuario_id: uuid.UUID,
    topic_id: uuid.UUID,
) -> Debilidad | None:
    """Evalúa R1…R5 en orden y devuelve la primera que se cumpla.

    Es una función **determinista**: no consulta a ningún modelo y, con los mismos
    datos, devuelve siempre lo mismo.
    """
    reglas = reglas_debilidad(cfg)
    intentos = _ultimas_respuestas(db, usuario_id, topic_id, 10)

    # R1 · errores en las últimas 10 respuestas
    errores = sum(1 for intento in intentos if not intento.is_correct)
    if errores >= reglas.r1_errors_in_last_10:
        return Debilidad(topic_id, "R1", {"errors_last_10": errores, "attempts": len(intentos)})

    # R2 · precisión baja con evidencia suficiente
    if len(intentos) >= reglas.r2_min_attempts:
        aciertos = sum(1 for intento in intentos if intento.is_correct)
        precision = 100.0 * aciertos / len(intentos)
        if precision < reglas.r2_accuracy_lt:
            return Debilidad(
                topic_id,
                "R2",
                {"accuracy_pct": round(precision, 2), "attempts": len(intentos)},
            )

    # R3 · el tema puntuó bajo en la última evaluación
    puntaje = _puntaje_de_evaluacion(db, usuario_id, topic_id)
    if puntaje is not None and puntaje < reglas.r3_assessment_topic_lt:
        return Debilidad(topic_id, "R3", {"assessment_topic_pct": round(puntaje, 2)})

    # R4 · tarda mucho más de lo estimado
    lentas = _respuestas_lentas(db, intentos, reglas.r4_time_multiplier)
    if lentas >= reglas.r4_min_questions:
        return Debilidad(
            topic_id, "R4", {"slow_questions": lentas, "multiplier": reglas.r4_time_multiplier}
        )

    # R5 · un objetivo concreto sin un solo acierto
    objetivo = _objetivo_en_cero(db, usuario_id, topic_id, reglas.r5_objective_zero_of)
    if objetivo is not None:
        return Debilidad(
            topic_id, "R5", {"objective": objetivo, "of": reglas.r5_objective_zero_of}
        )
    return None


def _puntaje_de_evaluacion(
    db: Session, usuario_id: uuid.UUID, topic_id: uuid.UUID
) -> float | None:
    """Puntaje del tema en el último intento de evaluación que lo incluyó."""
    modulo_id = db.execute(sa.select(Topic.module_id).where(Topic.id == topic_id)).scalar_one_or_none()
    if modulo_id is None:
        return None
    intento = db.execute(
        sa.select(AssessmentAttempt)
        .where(
            AssessmentAttempt.user_id == usuario_id,
            AssessmentAttempt.module_id == modulo_id,
            AssessmentAttempt.submitted_at.is_not(None),
        )
        .order_by(AssessmentAttempt.submitted_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if intento is None:
        return None
    for entrada in intento.per_topic_scores or []:
        if isinstance(entrada, dict) and str(entrada.get("topic_id")) == str(topic_id):
            try:
                return float(entrada.get("pct"))
            except (TypeError, ValueError):  # pragma: no cover - dato corrupto
                return None
    return None


def _respuestas_lentas(
    db: Session, intentos: list[QuestionAttempt], multiplicador: float
) -> int:
    """Cuenta las respuestas que tardaron más de `multiplicador` × lo estimado."""
    if not intentos:
        return 0
    ids = {intento.question_id for intento in intentos}
    estimados = {
        fila[0]: int(fila[1] or 45)
        for fila in db.execute(
            sa.select(Question.id, Question.estimated_seconds).where(Question.id.in_(ids))
        ).all()
    }
    lentas = 0
    for intento in intentos:
        estimado_ms = estimados.get(intento.question_id, 45) * 1000
        if int(intento.response_ms or 0) > multiplicador * estimado_ms:
            lentas += 1
    return lentas


def _objetivo_en_cero(
    db: Session, usuario_id: uuid.UUID, topic_id: uuid.UUID, de_cuantas: int
) -> str | None:
    """Devuelve el objetivo de aprendizaje sin ningún acierto en sus últimas N."""
    filas = db.execute(
        sa.select(Question.learning_objective, QuestionAttempt.is_correct, QuestionAttempt.answered_at)
        .join(QuestionAttempt, QuestionAttempt.question_id == Question.id)
        .where(
            QuestionAttempt.user_id == usuario_id,
            QuestionAttempt.topic_id == topic_id,
            Question.learning_objective.is_not(None),
        )
        .order_by(QuestionAttempt.answered_at.desc())
        .limit(60)
    ).all()
    por_objetivo: dict[str, list[bool]] = {}
    for objetivo, correcto, _ in filas:
        por_objetivo.setdefault(str(objetivo), []).append(bool(correcto))
    for objetivo, resultados in por_objetivo.items():
        ventana = resultados[:de_cuantas]
        if len(ventana) >= de_cuantas and not any(ventana):
            return objetivo
    return None


# ---------------------------------------------------------------------------
# Decisión
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Decision:
    """Qué hacer con un tema en el que el estudiante flojea."""

    topic_id: uuid.UUID
    accion: str
    rule: str | None = None
    approach: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    motivo: str = ""

    def como_dict(self) -> dict[str, Any]:
        """Representación serializable para la respuesta de la API."""
        return {
            "topic_id": str(self.topic_id),
            "action": self.accion,
            "rule": self.rule,
            "approach": self.approach,
            "evidence": self.evidence,
            "reason": self.motivo,
        }


def explicaciones_previas(db: Session, usuario_id: uuid.UUID, topic_id: uuid.UUID) -> int:
    """Cuántas re-explicaciones se han generado ya para ese tema.

    Se cuenta sobre `content_provenance` (el rastro que deja cada explicación); es lo
    que permite **rotar el enfoque** en lugar de repetir el mismo.
    """
    return int(
        db.execute(
            sa.select(sa.func.count(sa.func.distinct(ContentProvenance.block_key))).where(
                ContentProvenance.content_type == ProvenanceContentType.EXPLANATION,
                ContentProvenance.content_id == topic_id,
            )
        ).scalar_one()
        or 0
    )


def enfoque_siguiente(previas: int) -> str:
    """Enfoque rotativo: nunca dos veces el mismo seguido."""
    return ENFOQUES[previas % len(ENFOQUES)]


def decidir(
    db: Session,
    cfg: ServicioConfig | None,
    *,
    usuario_id: uuid.UUID,
    topic_id: uuid.UUID,
    debilidad: Debilidad | None = None,
) -> Decision:
    """Decide de forma determinista entre no hacer nada, repasar o re-explicar.

    Política:

    - Sin debilidad → no se hace nada.
    - `R3` (falló en la evaluación) o `R5` (un objetivo entero en cero) → el problema es
      de **comprensión**: toca re-explicar con otro enfoque.
    - Si ya se repasó desde la última detección y sigue débil → re-explicar.
    - En el resto de los casos → repaso dirigido (más barato y suele bastar).
    """
    hallazgo = debilidad or detectar_debilidad(db, cfg, usuario_id=usuario_id, topic_id=topic_id)
    if hallazgo is None:
        return Decision(topic_id=topic_id, accion=ACCION_NINGUNA, motivo="Sin debilidad detectada.")

    previas = explicaciones_previas(db, usuario_id, topic_id)
    progreso = db.execute(
        sa.select(UserTopicProgress).where(
            UserTopicProgress.user_id == usuario_id,
            UserTopicProgress.topic_id == topic_id,
        )
    ).scalar_one_or_none()
    ya_repaso = bool(progreso and progreso.weak_detected_at and int(progreso.stability_s or 0) > 0)

    if hallazgo.rule in ("R3", "R5") or ya_repaso:
        return Decision(
            topic_id=topic_id,
            accion=ACCION_REEXPLICAR,
            rule=hallazgo.rule,
            approach=enfoque_siguiente(previas),
            evidence=hallazgo.evidence,
            motivo=(
                "El fallo es de comprensión: te lo explicamos de otra forma."
                if hallazgo.rule in ("R3", "R5")
                else "Ya repasaste y sigue costándote: te lo explicamos de otra forma."
            ),
        )
    return Decision(
        topic_id=topic_id,
        accion=ACCION_REPASO,
        rule=hallazgo.rule,
        evidence=hallazgo.evidence,
        motivo="Un repaso dirigido debería bastar.",
    )


# ---------------------------------------------------------------------------
# Re-explicación (lo único que escribe la IA)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ExplicacionGenerada:
    """Explicación alternativa lista para `ExplanationOut` (§7.6)."""

    topic_id: uuid.UUID
    approach: str
    body: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    check_question: str = ""
    job_id: uuid.UUID | None = None
    coste_usd: Decimal = Decimal("0")
    llamadas_ia: int = 0

    def como_dict(self) -> dict[str, Any]:
        """Representación serializable."""
        return {
            "topic_id": str(self.topic_id),
            "approach": self.approach,
            "body": self.body,
            "citations": self.citations,
            "check_question": self.check_question,
        }


def _citas(fragmentos: list[FragmentoContexto], etiquetas: list[str]) -> list[dict[str, Any]]:
    """Convierte las etiquetas citadas por el modelo en citas con su trazabilidad."""
    indice = {fragmento.etiqueta: fragmento for fragmento in fragmentos}
    citas: list[dict[str, Any]] = []
    for etiqueta in etiquetas:
        fragmento = indice.get(etiqueta)
        if fragmento is None:
            continue
        citas.append(
            {
                "chunk_id": str(fragmento.chunk_id),
                "document_id": str(fragmento.document_id) if fragmento.document_id else None,
                "document_title": fragmento.document_title,
                "page_start": fragmento.page_start,
                "page_end": fragmento.page_end,
            }
        )
    return citas


def reexplicar(
    db: Session,
    cfg: ServicioConfig,
    proveedor: ProveedorIA,
    *,
    topic_id: uuid.UUID,
    usuario_id: uuid.UUID | None = None,
    decision: Decision | None = None,
) -> ExplicacionGenerada:
    """Genera la explicación alternativa de un tema con el enfoque que toque."""
    tema = db.get(Topic, topic_id)
    if tema is None:
        raise NotFound("No encontramos ese tema.")
    modulo = db.get(PathModule, tema.module_id)
    path = db.get(LearningPath, modulo.learning_path_id) if modulo else None
    if path is None:
        raise NotFound("No encontramos ese tema.")
    if usuario_id is not None and path.user_id not in (None, usuario_id):
        raise NotFound("No encontramos ese tema.")

    costos.verificar_cuota(db, cfg, usuario_id, costos.CUOTA_REEXPLICACIONES)
    costos.verificar_presupuesto(db, cfg)

    previas = explicaciones_previas(db, usuario_id or uuid.uuid4(), topic_id)
    enfoque = (decision.approach if decision and decision.approach else enfoque_siguiente(previas))
    evidencia = decision.evidence if decision else {}

    plantilla = plantilla_para_tarea(db, TAREA_REEXPLICACION)
    job = costos.crear_job(
        db,
        job_type=JobType.RE_EXPLANATION,
        usuario_id=usuario_id,
        target_type="topic",
        target_id=tema.id,
        learning_path_id=path.id,
        prompt_template_id=plantilla.id,
        payload={"approach": enfoque, "rule": decision.rule if decision else None},
        progress_label="Buscando otra forma de explicarlo",
    )

    objetivos = [str(o) for o in (tema.learning_objectives or [])]
    parametros = parametros_recuperacion(cfg)
    preferidos: list[uuid.UUID] = []
    for crudo in tema.source_chunk_ids or []:
        try:
            preferidos.append(uuid.UUID(str(crudo)))
        except (ValueError, AttributeError, TypeError):
            continue
    fragmentos = recuperar(
        db,
        cfg,
        knowledge_base_id=path.knowledge_base_id,
        user_id=path.user_id,
        consulta=f"{tema.title} {' '.join(objetivos)}",
        ids_preferidos=preferidos,
        top_k=parametros.reexplain_top_k,
    )

    instruccion = (
        "## Encargo\n"
        f"- Tema: {tema.title}\n"
        f"- Objetivos: {'; '.join(objetivos) or 'los del tema'}\n"
        f"- Enfoque obligatorio: {enfoque}\n"
        f"- Evidencia del atasco: {evidencia or 'errores repetidos en este tema'}\n"
        "\nDevuelve la explicación alternativa en JSON."
    )
    solicitud = SolicitudIA(
        tarea=TAREA_REEXPLICACION,
        sistema=plantilla.body,
        instruccion=instruccion,
        fragmentos=fragmentos,
        datos={
            "approach": enfoque,
            "topic_title": tema.title,
            "objectives": objetivos,
            "evidence": evidencia,
        },
        esquema=esquema_estricto(SalidaExplicacion),
        modelo=modelo_para_tarea(cfg, TAREA_REEXPLICACION),
        max_tokens=4_000,
        plantilla_id=plantilla.id,
        semilla=f"{tema.id}:{enfoque}",
    )
    salida, respuesta = generar_validado(proveedor, solicitud, SalidaExplicacion)
    costos.registrar_uso(db, job, respuesta.uso)

    citados = [
        fragmento
        for fragmento in fragmentos
        if fragmento.etiqueta in set(salida.citations)
    ]
    registrar_procedencia(
        db,
        content_type=ProvenanceContentType.EXPLANATION,
        content_id=tema.id,
        fragmentos=citados,
        job_id=job.id,
        plantilla_id=plantilla.id,
        model_id=respuesta.uso.model_id,
        origen=ProvenanceOrigin.SOURCE if citados else ProvenanceOrigin.MODEL_KNOWLEDGE,
        block_key=f"{enfoque}:{previas + 1}",
    )

    resultado = ExplicacionGenerada(
        topic_id=tema.id,
        approach=salida.approach or enfoque,
        body=salida.body,
        citations=_citas(fragmentos, list(salida.citations)),
        check_question=salida.check_question,
        job_id=job.id,
        coste_usd=respuesta.uso.cost_usd,
        llamadas_ia=1 + respuesta.reintentos,
    )
    costos.cerrar_job(db, job, estado=JobStatus.SUCCEEDED, resultado=resultado.como_dict())
    logger.info(
        "ai.reexplicacion",
        topic_id=str(tema.id),
        approach=resultado.approach,
        citations=len(resultado.citations),
        cost_usd=str(respuesta.uso.cost_usd),
    )
    return resultado


__all__ = [
    "ACCION_NINGUNA",
    "ACCION_REEXPLICAR",
    "ACCION_REPASO",
    "ENFOQUES",
    "Debilidad",
    "Decision",
    "ExplicacionGenerada",
    "ReglasDebilidad",
    "decidir",
    "detectar_debilidad",
    "enfoque_siguiente",
    "explicaciones_previas",
    "reexplicar",
    "reglas_debilidad",
]
