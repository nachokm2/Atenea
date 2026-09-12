"""Fase B — generación **perezosa** de un módulo: lecciones, bloques y preguntas.

Reglas que gobiernan esta fase:

- **Perezosa**: solo se genera el módulo que el usuario va a estudiar (el 1 al confirmar
  la ruta, el siguiente al desbloquearlo). Nunca la ruta entera de golpe.
- **Caché permanente**: si ya hay contenido para ese módulo y esas versiones de
  documento, **no se llama al modelo**. El contenido es reutilizable (las Rutas del
  Reino las estudian muchos usuarios sin duplicarlo, D17) y regenerar cuesta dinero.
  La invalidación es explícita: sube la versión del documento o se fuerza la
  regeneración (que consume la cuota `module_regenerations`).
- **Procedencia completa**: cada lección, cada bloque y cada pregunta deja su rastro en
  `content_provenance` (fragmento, versión de documento, modelo y plantilla de prompt).
- **Honestidad sobre el respaldo**: sin fragmentos que lo sostengan, el contenido se
  marca `model_knowledge` y la lección queda `is_low_content` (regla A8: paga la mitad).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import AteneaError, NotFound
from app.core.logging import get_logger
from app.models.content import (
    Assessment,
    AssessmentQuestion,
    LearningPath,
    Lesson,
    LessonBlock,
    PathModule,
    Question,
    Topic,
)
from app.models.enums import (
    ContentStatus,
    CoverageLevel,
    EventType,
    JobStatus,
    JobType,
    ProvenanceContentType,
    ProvenanceOrigin,
    QuestionType,
)
from app.models.ingestion import ContentProvenance
from app.modules.ai import costos
from app.modules.ai.arquitecto_ruta import evaluar_material, recuperar, registrar_procedencia
from app.modules.ai.esquemas_salida import (
    SalidaLeccion,
    SalidaLotePreguntas,
    SalidaPregunta,
    esquema_estricto,
    generar_validado,
)
from app.modules.ai.proveedor import (
    TAREA_LESSON,
    TAREA_QUESTIONS,
    FragmentoContexto,
    ProveedorIA,
    SolicitudIA,
    modelo_para_tarea,
    plantilla_para_tarea,
)
from app.modules.gamification import eventos as bus
from app.modules.gamification.servicio_config import ServicioConfig

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ResultadoModulo:
    """Salida de la Fase B para un módulo."""

    module_id: uuid.UUID
    lessons: int = 0
    questions: int = 0
    desde_cache: bool = False
    llamadas_ia: int = 0
    coste_usd: Decimal = Decimal("0")
    job_id: uuid.UUID | None = None
    notas: list[str] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        """Resumen serializable para `generation_jobs.result`."""
        return {
            "module_id": str(self.module_id),
            "lessons": self.lessons,
            "questions": self.questions,
            "from_cache": self.desde_cache,
            "ai_calls": self.llamadas_ia,
            "cost_usd": str(self.coste_usd),
            "notes": self.notas,
        }


# ---------------------------------------------------------------------------
# Caché permanente
# ---------------------------------------------------------------------------


def lecciones_del_modulo(db: Session, module_id: uuid.UUID) -> list[Lesson]:
    """Lecciones ya generadas de un módulo, en orden de tema y posición."""
    filas = db.execute(
        sa.select(Lesson)
        .join(Topic, Topic.id == Lesson.topic_id)
        .where(Topic.module_id == module_id)
        .order_by(Topic.position, Lesson.position)
    ).scalars()
    return list(filas)


def versiones_usadas(db: Session, module_id: uuid.UUID) -> set[uuid.UUID]:
    """Versiones de documento con las que se generó el contenido de este módulo."""
    lecciones = [leccion.id for leccion in lecciones_del_modulo(db, module_id)]
    if not lecciones:
        return set()
    filas = db.execute(
        sa.select(ContentProvenance.document_version_id).where(
            ContentProvenance.content_type == ProvenanceContentType.LESSON,
            ContentProvenance.content_id.in_(lecciones),
            ContentProvenance.document_version_id.is_not(None),
        )
    ).all()
    return {fila[0] for fila in filas if fila[0] is not None}


def contenido_vigente(db: Session, modulo: PathModule) -> bool:
    """`True` si ya hay contenido válido para este módulo y las versiones vigentes.

    Es la condición que evita la llamada al modelo. Se cumple cuando el módulo está
    `READY`, tiene lecciones, y las versiones de documento con las que se generó siguen
    siendo las vigentes de la biblioteca de la ruta.
    """
    if modulo.content_status is not ContentStatus.READY:
        return False
    if not lecciones_del_modulo(db, modulo.id):
        return False
    path = db.get(LearningPath, modulo.learning_path_id)
    if path is None or path.knowledge_base_id is None:
        # Ruta sin material: el contenido no caduca por versiones de documento.
        return True
    informe = evaluar_material(db, None, path.knowledge_base_id)
    vigentes = set(informe.document_version_ids)
    usadas = versiones_usadas(db, modulo.id)
    if not usadas:
        # Se generó con conocimiento del modelo: sigue siendo válido.
        return True
    return usadas.issubset(vigentes)


# ---------------------------------------------------------------------------
# Parámetros de contenido
# ---------------------------------------------------------------------------


def _tipos_admitidos(cfg: ServicioConfig, tema: Topic) -> list[str]:
    """Tipos de pregunta del tema: los sugeridos en la Fase A, filtrados por el MVP."""
    permitidos = [str(t) for t in (cfg.obtener_lista("content.mvp_question_types", []) or [])]
    sugeridos = [str(t) for t in (tema.suggested_question_types or []) if str(t) in permitidos]
    return sugeridos or permitidos


def _limitar_abiertas(preguntas: list[SalidaPregunta], maximo: int) -> list[SalidaPregunta]:
    """Aplica `content.open_questions_per_lesson_max` (§5.8)."""
    resultado: list[SalidaPregunta] = []
    abiertas = 0
    for pregunta in preguntas:
        if pregunta.question_type is QuestionType.OPEN_SHORT:
            if abiertas >= maximo:
                continue
            abiertas += 1
        resultado.append(pregunta)
    return resultado


# ---------------------------------------------------------------------------
# Fase B
# ---------------------------------------------------------------------------


def generar_modulo(
    db: Session,
    cfg: ServicioConfig,
    proveedor: ProveedorIA,
    *,
    module_id: uuid.UUID,
    usuario_id: uuid.UUID | None = None,
    forzar: bool = False,
) -> ResultadoModulo:
    """Genera (o devuelve de caché) el contenido completo de un módulo.

    Si `contenido_vigente` es cierto y no se fuerza, **no se llama al proveedor**: se
    devuelve el recuento del contenido existente con `desde_cache = True`.
    """
    modulo = db.get(PathModule, module_id)
    if modulo is None:
        raise NotFound("No encontramos ese módulo.")
    path = db.get(LearningPath, modulo.learning_path_id)
    if path is None:
        raise NotFound("No encontramos esa ruta.")
    if usuario_id is not None and path.user_id not in (None, usuario_id):
        raise NotFound("No encontramos ese módulo.")

    if not forzar and contenido_vigente(db, modulo):
        lecciones = lecciones_del_modulo(db, modulo.id)
        preguntas = int(
            db.execute(
                sa.select(sa.func.count(Question.id))
                .join(Topic, Topic.id == Question.topic_id)
                .where(Topic.module_id == modulo.id)
            ).scalar_one()
        )
        return ResultadoModulo(
            module_id=modulo.id,
            lessons=len(lecciones),
            questions=preguntas,
            desde_cache=True,
        )

    if forzar:
        costos.verificar_cuota(db, cfg, usuario_id, costos.CUOTA_REGENERACIONES)
    costos.verificar_presupuesto(db, cfg)

    plantilla_leccion = plantilla_para_tarea(db, TAREA_LESSON)
    plantilla_preguntas = plantilla_para_tarea(db, TAREA_QUESTIONS)
    job = costos.crear_job(
        db,
        job_type=JobType.MODULE_GENERATION,
        usuario_id=usuario_id or path.user_id,
        target_type="module",
        target_id=modulo.id,
        learning_path_id=path.id,
        prompt_template_id=plantilla_leccion.id,
        payload={"module_index": modulo.position, "forced": forzar},
        progress_label=f"Escribiendo el módulo {modulo.position}",
    )
    modulo.content_status = ContentStatus.GENERATING
    db.flush()

    temas = list(
        db.execute(
            sa.select(Topic).where(Topic.module_id == modulo.id).order_by(Topic.position)
        ).scalars()
    )
    if not temas:
        costos.cerrar_job(db, job, estado=JobStatus.FAILED, error="El módulo no tiene temas.")
        raise NotFound("Ese módulo todavía no tiene temas.")

    minutos = int((cfg.obtener_json("content.lesson.target_minutes", {}) or {}).get("default", 9))
    por_tema = int(cfg.obtener("content.questions_per_topic", 5))
    max_abiertas = int(cfg.obtener("content.open_questions_per_lesson_max", 1))
    distribucion = cfg.obtener_json("content.difficulty_distribution", {}) or {}
    modelo_leccion = modelo_para_tarea(cfg, TAREA_LESSON)
    modelo_preguntas = modelo_para_tarea(cfg, TAREA_QUESTIONS)

    total_lecciones = 0
    total_preguntas = 0
    llamadas = 0
    coste = Decimal("0")
    notas: list[str] = []

    try:
        for tema in temas:
            fragmentos = _fragmentos_del_tema(db, cfg, path=path, tema=tema)
            if not fragmentos and tema.coverage is not CoverageLevel.INSUFFICIENT:
                tema.coverage = CoverageLevel.INSUFFICIENT
                notas.append(f"«{tema.title}» se escribió sin respaldo del material.")

            leccion, respuesta_leccion = _generar_leccion(
                db,
                cfg,
                proveedor,
                tema=tema,
                fragmentos=fragmentos,
                plantilla=plantilla_leccion,
                modelo=modelo_leccion,
                minutos=minutos,
                job_id=job.id,
            )
            costos.registrar_uso(db, job, respuesta_leccion.uso)
            llamadas += 1 + respuesta_leccion.reintentos
            coste += respuesta_leccion.uso.cost_usd
            total_lecciones += 1

            creadas, respuesta_preguntas = _generar_preguntas(
                db,
                cfg,
                proveedor,
                tema=tema,
                leccion=leccion,
                fragmentos=fragmentos,
                plantilla=plantilla_preguntas,
                modelo=modelo_preguntas,
                cuantas=por_tema,
                max_abiertas=max_abiertas,
                distribucion=distribucion,
                job_id=job.id,
            )
            costos.registrar_uso(db, job, respuesta_preguntas.uso)
            llamadas += 1 + respuesta_preguntas.reintentos
            coste += respuesta_preguntas.uso.cost_usd
            total_preguntas += creadas

            leccion.question_count = creadas
            tema.lesson_count = 1
            tema.content_status = ContentStatus.READY
            db.flush()
    except AteneaError as error:
        costos.cerrar_job(db, job, estado=JobStatus.FAILED, error=str(error))
        modulo.content_status = ContentStatus.NEEDS_ATTENTION
        db.flush()
        bus.crear_evento_dominio(
            db,
            usuario_id=usuario_id or path.user_id,
            tipo=EventType.GENERATION_FAILED,
            payload={
                "job_id": str(job.id),
                "job_type": JobType.MODULE_GENERATION.value,
                "target_id": str(modulo.id),
                "reason": getattr(error, "code", "GENERATION_FAILED"),
            },
            idempotency_key=f"generation-failed:{job.id}",
            source_module="ai",
        )
        raise

    _armar_banco_evaluacion(db, cfg, modulo)

    modulo.lesson_count = total_lecciones
    modulo.topic_count = len(temas)
    modulo.content_status = ContentStatus.READY
    modulo.generated_by_job_id = job.id
    db.flush()

    resultado = ResultadoModulo(
        module_id=modulo.id,
        lessons=total_lecciones,
        questions=total_preguntas,
        desde_cache=False,
        llamadas_ia=llamadas,
        coste_usd=coste,
        job_id=job.id,
        notas=notas,
    )
    costos.cerrar_job(db, job, estado=JobStatus.SUCCEEDED, resultado=resultado.como_dict())

    bus.crear_evento_dominio(
        db,
        usuario_id=usuario_id or path.user_id,
        tipo=EventType.MODULE_CONTENT_READY,
        payload={
            "path_id": str(path.id),
            "module_id": str(modulo.id),
            "module_index": modulo.position,
            "lessons": total_lecciones,
            "questions": total_preguntas,
        },
        idempotency_key=f"module-content-ready:{modulo.id}:{job.id}",
        source_module="ai",
    )
    logger.info(
        "ai.fase_b",
        module_id=str(modulo.id),
        lessons=total_lecciones,
        questions=total_preguntas,
        ai_calls=llamadas,
        cost_usd=str(coste),
    )
    return resultado


# ---------------------------------------------------------------------------
# Piezas
# ---------------------------------------------------------------------------


def _fragmentos_del_tema(
    db: Session, cfg: ServicioConfig, *, path: LearningPath, tema: Topic
) -> list[FragmentoContexto]:
    """Recupera el contexto del tema, reforzando lo que la Fase A ya le asignó."""
    preferidos: list[uuid.UUID] = []
    for crudo in tema.source_chunk_ids or []:
        try:
            preferidos.append(uuid.UUID(str(crudo)))
        except (ValueError, AttributeError, TypeError):
            continue
    objetivos = " ".join(str(o) for o in (tema.learning_objectives or []))
    return recuperar(
        db,
        cfg,
        knowledge_base_id=path.knowledge_base_id,
        user_id=path.user_id,
        consulta=f"{tema.title} {objetivos}",
        ids_preferidos=preferidos,
    )


def _generar_leccion(
    db: Session,
    cfg: ServicioConfig,
    proveedor: ProveedorIA,
    *,
    tema: Topic,
    fragmentos: list[FragmentoContexto],
    plantilla: Any,
    modelo: str,
    minutos: int,
    job_id: uuid.UUID,
) -> tuple[Lesson, Any]:
    """Genera y persiste una lección con sus bloques y su procedencia."""
    objetivos = [str(o) for o in (tema.learning_objectives or [])]
    indice = {fragmento.etiqueta: fragmento for fragmento in fragmentos}
    instruccion = (
        "## Encargo\n"
        f"- Tema: {tema.title}\n"
        f"- Objetivos de aprendizaje: {'; '.join(objetivos) or 'los del tema'}\n"
        f"- Dificultad declarada: {tema.difficulty.value}\n"
        f"- Duración objetivo: {minutos} minutos\n"
        f"- Cobertura del material para este tema: {tema.coverage.value}\n"
        "\nDevuelve la lección completa en JSON."
    )
    solicitud = SolicitudIA(
        tarea=TAREA_LESSON,
        sistema=plantilla.body,
        instruccion=instruccion,
        fragmentos=fragmentos,
        datos={
            "topic_title": tema.title,
            "objectives": objetivos,
            "lesson_minutes": minutos,
            "difficulty": tema.difficulty.value,
        },
        esquema=esquema_estricto(SalidaLeccion),
        modelo=modelo,
        max_tokens=8_000,
        plantilla_id=getattr(plantilla, "id", None),
        semilla=str(tema.id),
    )
    salida, respuesta = generar_validado(proveedor, solicitud, SalidaLeccion)

    sin_respaldo = not fragmentos or tema.coverage is CoverageLevel.INSUFFICIENT
    leccion = Lesson(
        topic_id=tema.id,
        position=1,
        title=salida.title[:140],
        summary=salida.summary or None,
        estimated_seconds=salida.estimated_seconds,
        content_status=ContentStatus.READY,
        origin=ProvenanceOrigin.MODEL_KNOWLEDGE if sin_respaldo else ProvenanceOrigin.SOURCE,
        is_low_content=sin_respaldo,
        coverage_report=[
            {"objective": entrada.objective, "status": entrada.status.value}
            for entrada in salida.coverage_report
        ],
        block_count=len(salida.blocks),
        question_count=0,
        generated_by_job_id=job_id,
    )
    db.add(leccion)
    db.flush()

    usados_leccion: list[FragmentoContexto] = []
    for bloque in salida.blocks:
        citados = [indice[i] for i in bloque.source_chunk_ids if i in indice]
        usados_leccion.extend(citados)
        fila = LessonBlock(
            lesson_id=leccion.id,
            position=bloque.position,
            block_type=bloque.block_type,
            body=bloque.body,
            payload=bloque.payload or {},
            origin=bloque.origin if citados else ProvenanceOrigin.MODEL_KNOWLEDGE,
        )
        db.add(fila)
        db.flush()
        registrar_procedencia(
            db,
            content_type=ProvenanceContentType.LESSON_BLOCK,
            content_id=fila.id,
            fragmentos=citados,
            job_id=job_id,
            plantilla_id=getattr(plantilla, "id", None),
            model_id=respuesta.uso.model_id,
            block_key=str(bloque.position),
        )

    unicos = list({fragmento.chunk_id: fragmento for fragmento in usados_leccion}.values())
    registrar_procedencia(
        db,
        content_type=ProvenanceContentType.LESSON,
        content_id=leccion.id,
        fragmentos=unicos or fragmentos,
        job_id=job_id,
        plantilla_id=getattr(plantilla, "id", None),
        model_id=respuesta.uso.model_id,
        origen=ProvenanceOrigin.MODEL_KNOWLEDGE if sin_respaldo else ProvenanceOrigin.SOURCE,
    )
    return leccion, respuesta


def _generar_preguntas(
    db: Session,
    cfg: ServicioConfig,
    proveedor: ProveedorIA,
    *,
    tema: Topic,
    leccion: Lesson,
    fragmentos: list[FragmentoContexto],
    plantilla: Any,
    modelo: str,
    cuantas: int,
    max_abiertas: int,
    distribucion: dict[str, Any],
    job_id: uuid.UUID,
) -> tuple[int, Any]:
    """Genera y persiste el pool de preguntas de un tema."""
    objetivos = [str(o) for o in (tema.learning_objectives or [])]
    tipos = _tipos_admitidos(cfg, tema)
    indice = {fragmento.etiqueta: fragmento for fragmento in fragmentos}
    reparto = ", ".join(f"{clave} {float(valor):.0%}" for clave, valor in distribucion.items())
    instruccion = (
        "## Encargo\n"
        f"- Tema: {tema.title}\n"
        f"- Objetivos de aprendizaje: {'; '.join(objetivos) or 'los del tema'}\n"
        f"- Número de preguntas: {cuantas}\n"
        f"- Tipos admitidos: {', '.join(tipos)}\n"
        f"- Como máximo {max_abiertas} pregunta(s) abierta(s)\n"
        f"- Distribución de dificultad: {reparto or 'equilibrada'}\n"
        "\nDevuelve el lote completo de preguntas en JSON."
    )
    solicitud = SolicitudIA(
        tarea=TAREA_QUESTIONS,
        sistema=plantilla.body,
        instruccion=instruccion,
        fragmentos=fragmentos,
        datos={
            "topic_title": tema.title,
            "objectives": objetivos,
            "types": tipos,
            "count": cuantas,
            "difficulty_distribution": distribucion,
        },
        esquema=esquema_estricto(SalidaLotePreguntas),
        modelo=modelo,
        max_tokens=12_000,
        plantilla_id=getattr(plantilla, "id", None),
        semilla=f"{tema.id}:preguntas",
    )
    salida, respuesta = generar_validado(proveedor, solicitud, SalidaLotePreguntas)

    admitidas = _limitar_abiertas(
        [pregunta for pregunta in salida.questions if pregunta.clave_completa()], max_abiertas
    )
    creadas = 0
    for pregunta in admitidas[:cuantas]:
        citados = [indice[i] for i in pregunta.source_chunk_ids if i in indice]
        fila = Question(
            topic_id=tema.id,
            lesson_id=leccion.id,
            question_type=pregunta.question_type,
            difficulty=pregunta.difficulty,
            stem=pregunta.stem,
            body=pregunta.body,
            answer_key=pregunta.answer_key,
            explanation=pregunta.explanation or None,
            learning_objective=(pregunta.learning_objective or None),
            estimated_seconds=pregunta.estimated_seconds,
            origin=ProvenanceOrigin.SOURCE if citados else ProvenanceOrigin.MODEL_KNOWLEDGE,
            content_status=ContentStatus.READY,
            generated_by_job_id=job_id,
        )
        db.add(fila)
        db.flush()
        registrar_procedencia(
            db,
            content_type=ProvenanceContentType.QUESTION,
            content_id=fila.id,
            fragmentos=citados,
            job_id=job_id,
            plantilla_id=getattr(plantilla, "id", None),
            model_id=respuesta.uso.model_id,
            origen=ProvenanceOrigin.SOURCE if citados else ProvenanceOrigin.MODEL_KNOWLEDGE,
        )
        creadas += 1
    return creadas, respuesta


def _armar_banco_evaluacion(db: Session, cfg: ServicioConfig, modulo: PathModule) -> int:
    """Llena el banco de la evaluación del módulo con las preguntas ya generadas."""
    evaluacion = db.execute(
        sa.select(Assessment).where(Assessment.module_id == modulo.id)
    ).scalar_one_or_none()
    if evaluacion is None:
        n_preguntas = int(cfg.obtener("mastery.assessment.question_count", 10))
        ratio = Decimal(str(cfg.obtener("mastery.assessment.bank_ratio", "2.5")))
        evaluacion = Assessment(
            module_id=modulo.id,
            question_count=n_preguntas,
            pass_score=Decimal(str(cfg.obtener("mastery.assessment.pass_score", 70))),
            bank_size=int(Decimal(n_preguntas) * ratio),
            max_attempts_per_day=int(cfg.obtener("mastery.assessment.max_attempts_per_day", 2)),
            content_status=ContentStatus.PENDING,
        )
        db.add(evaluacion)
        db.flush()

    candidatas = list(
        db.execute(
            sa.select(Question.id)
            .join(Topic, Topic.id == Question.topic_id)
            .where(
                Topic.module_id == modulo.id,
                Question.content_status == ContentStatus.READY,
                Question.is_flagged.is_(False),
            )
            .order_by(Topic.position, Question.created_at, Question.id)
        ).all()
    )
    ya_en_banco = {
        fila[0]
        for fila in db.execute(
            sa.select(AssessmentQuestion.question_id).where(
                AssessmentQuestion.assessment_id == evaluacion.id
            )
        ).all()
    }
    posicion = len(ya_en_banco)
    agregadas = 0
    for (question_id,) in candidatas:
        if question_id in ya_en_banco or posicion >= (evaluacion.bank_size or 25):
            continue
        posicion += 1
        db.add(
            AssessmentQuestion(
                assessment_id=evaluacion.id,
                question_id=question_id,
                position=posicion,
                is_active=True,
            )
        )
        agregadas += 1
    evaluacion.content_status = (
        ContentStatus.READY if posicion >= evaluacion.question_count else ContentStatus.NEEDS_ATTENTION
    )
    db.flush()
    return agregadas


__all__ = [
    "ResultadoModulo",
    "contenido_vigente",
    "generar_modulo",
    "lecciones_del_modulo",
    "versiones_usadas",
]
