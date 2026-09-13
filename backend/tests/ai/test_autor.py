"""Fase B: lecciones y preguntas válidas, caché permanente y procedencia completa."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.content import (
    Assessment,
    AssessmentQuestion,
    LessonBlock,
    PathModule,
    Question,
    Topic,
)
from app.models.enums import (
    ContentStatus,
    JobStatus,
    JobType,
    ProvenanceContentType,
    QuestionType,
)
from app.models.ingestion import ContentProvenance, GenerationJob
from app.modules.ai import arquitecto_ruta as fase_a, autor_leccion as fase_b
from app.modules.ai.esquemas_salida import TIPOS_PREGUNTA_MVP


@pytest.fixture
def modulo(db, cfg, proveedor, ruta) -> PathModule:
    """Primer módulo de una ruta ya diseñada (Fase A hecha)."""
    fase_a.disenar_ruta(db, cfg, proveedor, learning_path_id=ruta.id, usuario_id=ruta.user_id)
    proveedor.reiniciar_contador()
    return db.execute(
        sa.select(PathModule)
        .where(PathModule.learning_path_id == ruta.id)
        .order_by(PathModule.position)
        .limit(1)
    ).scalar_one()


def test_genera_leccion_y_preguntas_validas(db, cfg, proveedor, modulo, ruta) -> None:
    """El módulo queda con sus lecciones, bloques y preguntas listos para estudiar."""
    resultado = fase_b.generar_modulo(
        db, cfg, proveedor, module_id=modulo.id, usuario_id=ruta.user_id
    )

    assert resultado.desde_cache is False
    assert resultado.lessons == modulo.topic_count
    assert resultado.questions > 0
    assert resultado.llamadas_ia >= 2 * resultado.lessons

    lecciones = fase_b.lecciones_del_modulo(db, modulo.id)
    assert lecciones
    for leccion in lecciones:
        assert leccion.content_status is ContentStatus.READY
        assert leccion.block_count >= 1
        assert leccion.estimated_seconds >= 60
        bloques = list(
            db.execute(
                sa.select(LessonBlock)
                .where(LessonBlock.lesson_id == leccion.id)
                .order_by(LessonBlock.position)
            ).scalars()
        )
        assert [b.position for b in bloques] == list(range(1, len(bloques) + 1))
        # Markdown restringido: nada de HTML ni de URLs (§3.2).
        for bloque in bloques:
            assert "<script" not in (bloque.body or "").lower()
            assert "http://" not in (bloque.body or "")

    preguntas = list(
        db.execute(
            sa.select(Question)
            .join(Topic, Topic.id == Question.topic_id)
            .where(Topic.module_id == modulo.id)
        ).scalars()
    )
    assert preguntas
    for pregunta in preguntas:
        assert pregunta.question_type in TIPOS_PREGUNTA_MVP
        assert pregunta.stem.strip()
        assert pregunta.answer_key
        assert pregunta.explanation
        assert pregunta.content_status is ContentStatus.READY

    db.refresh(modulo)
    assert modulo.content_status is ContentStatus.READY
    assert modulo.lesson_count == len(lecciones)


def test_no_vuelve_a_llamar_al_proveedor_si_hay_cache(db, cfg, proveedor, modulo, ruta) -> None:
    """La caché permanente es la regla de oro: contenido vigente, cero llamadas."""
    primero = fase_b.generar_modulo(
        db, cfg, proveedor, module_id=modulo.id, usuario_id=ruta.user_id
    )
    llamadas = proveedor.uso_acumulado.llamadas
    assert llamadas > 0

    segundo = fase_b.generar_modulo(
        db, cfg, proveedor, module_id=modulo.id, usuario_id=ruta.user_id
    )
    assert segundo.desde_cache is True
    assert segundo.lessons == primero.lessons
    assert segundo.questions == primero.questions
    assert segundo.llamadas_ia == 0
    assert proveedor.uso_acumulado.llamadas == llamadas
    assert fase_b.contenido_vigente(db, modulo) is True

    # Tampoco se crea un trabajo nuevo cuando se sirve de caché.
    trabajos = int(
        db.execute(
            sa.select(sa.func.count(GenerationJob.id)).where(
                GenerationJob.job_type == JobType.MODULE_GENERATION,
                GenerationJob.target_id == modulo.id,
            )
        ).scalar_one()
    )
    assert trabajos == 1


def test_la_cache_caduca_con_una_version_nueva_del_documento(
    db, cfg, proveedor, modulo, ruta, biblioteca
) -> None:
    """Subir una versión nueva invalida el contenido: hay que volver a generarlo."""
    fase_b.generar_modulo(db, cfg, proveedor, module_id=modulo.id, usuario_id=ruta.user_id)
    assert fase_b.contenido_vigente(db, modulo) is True

    from app.core.time import utcnow
    from app.models.enums import DocumentStatus
    from app.models.ingestion import Document, DocumentVersion

    documento = db.execute(
        sa.select(Document).where(Document.knowledge_base_id == biblioteca.id)
    ).scalar_one()
    anterior = db.execute(
        sa.select(DocumentVersion).where(
            DocumentVersion.document_id == documento.id,
            DocumentVersion.is_current.is_(True),
        )
    ).scalar_one()
    anterior.is_current = False
    anterior.status = DocumentStatus.SUPERSEDED
    db.flush()
    db.add(
        DocumentVersion(
            document_id=documento.id,
            version_number=2,
            content_hash="b" * 64,
            storage_key="local/manual-sql-v2.pdf",
            byte_size=130_000,
            word_count=anterior.word_count,
            token_count=anterior.token_count,
            chunk_count=anterior.chunk_count,
            status=DocumentStatus.READY,
            is_current=True,
            processed_at=utcnow(),
        )
    )
    db.flush()

    assert fase_b.contenido_vigente(db, modulo) is False


def test_deja_procedencia_de_todo_lo_generado(db, cfg, proveedor, modulo, ruta) -> None:
    """Lección, bloques y preguntas dejan su rastro en `content_provenance`."""
    fase_b.generar_modulo(db, cfg, proveedor, module_id=modulo.id, usuario_id=ruta.user_id)

    lecciones = [leccion.id for leccion in fase_b.lecciones_del_modulo(db, modulo.id)]
    bloques = [
        fila[0]
        for fila in db.execute(
            sa.select(LessonBlock.id).where(LessonBlock.lesson_id.in_(lecciones))
        ).all()
    ]
    preguntas = [
        fila[0]
        for fila in db.execute(
            sa.select(Question.id)
            .join(Topic, Topic.id == Question.topic_id)
            .where(Topic.module_id == modulo.id)
        ).all()
    ]

    for tipo, ids in (
        (ProvenanceContentType.LESSON, lecciones),
        (ProvenanceContentType.LESSON_BLOCK, bloques),
        (ProvenanceContentType.QUESTION, preguntas),
    ):
        trazados = {
            fila[0]
            for fila in db.execute(
                sa.select(ContentProvenance.content_id).where(
                    ContentProvenance.content_type == tipo,
                    ContentProvenance.content_id.in_(ids),
                )
            ).all()
        }
        assert trazados == set(ids), f"falta procedencia de {tipo.value}"

    # El modelo y el trabajo quedan anotados en cada fila.
    filas = list(
        db.execute(
            sa.select(ContentProvenance).where(
                ContentProvenance.content_type == ProvenanceContentType.LESSON,
                ContentProvenance.content_id.in_(lecciones),
            )
        ).scalars()
    )
    assert all(fila.model_id == "claude-sonnet-5" for fila in filas)
    assert all(fila.generation_job_id is not None for fila in filas)
    assert all(fila.processed_at is not None for fila in filas)


def test_arma_el_banco_de_la_evaluacion(db, cfg, proveedor, modulo, ruta) -> None:
    """La evaluación del módulo se llena con las preguntas ya generadas."""
    fase_b.generar_modulo(db, cfg, proveedor, module_id=modulo.id, usuario_id=ruta.user_id)

    evaluacion = db.execute(
        sa.select(Assessment).where(Assessment.module_id == modulo.id)
    ).scalar_one()
    banco = list(
        db.execute(
            sa.select(AssessmentQuestion).where(
                AssessmentQuestion.assessment_id == evaluacion.id
            )
        ).scalars()
    )
    assert banco
    assert len(banco) <= evaluacion.bank_size
    assert all(fila.is_active for fila in banco)
    assert evaluacion.content_status in (ContentStatus.READY, ContentStatus.NEEDS_ATTENTION)


def test_como_mucho_una_pregunta_abierta_por_leccion(db, cfg, proveedor, modulo, ruta) -> None:
    """`content.open_questions_per_lesson_max` se aplica al persistir (§5.8)."""
    fase_b.generar_modulo(db, cfg, proveedor, module_id=modulo.id, usuario_id=ruta.user_id)
    for leccion in fase_b.lecciones_del_modulo(db, modulo.id):
        abiertas = int(
            db.execute(
                sa.select(sa.func.count(Question.id)).where(
                    Question.lesson_id == leccion.id,
                    Question.question_type == QuestionType.OPEN_SHORT,
                )
            ).scalar_one()
        )
        assert abiertas <= 1


def test_el_trabajo_registra_tokens_y_coste(db, cfg, proveedor, modulo, ruta) -> None:
    """Cada llamada suma en `generation_jobs`: es la fuente de verdad del coste."""
    resultado = fase_b.generar_modulo(
        db, cfg, proveedor, module_id=modulo.id, usuario_id=ruta.user_id
    )
    job = db.get(GenerationJob, resultado.job_id)
    assert job is not None
    assert job.status is JobStatus.SUCCEEDED
    assert job.job_type is JobType.MODULE_GENERATION
    assert job.input_tokens > 0
    assert job.output_tokens > 0
    assert job.model_id in ("claude-sonnet-5", "claude-opus-5")
    assert job.result["lessons"] == resultado.lessons


def test_modulo_ajeno_no_existe(db, cfg, proveedor, modulo) -> None:
    """§8.7: el contenido de otro usuario devuelve 404."""
    from app.core.errors import NotFound

    with pytest.raises(NotFound):
        fase_b.generar_modulo(db, cfg, proveedor, module_id=modulo.id, usuario_id=uuid.uuid4())


def test_modulo_inexistente(db, cfg, proveedor) -> None:
    """Un módulo que no existe es un 404 limpio."""
    from app.core.errors import NotFound

    with pytest.raises(NotFound):
        fase_b.generar_modulo(db, cfg, proveedor, module_id=uuid.uuid4())
