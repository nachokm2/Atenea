"""Fase A: recuperación híbrida, esquema de ruta válido, cobertura y material insuficiente."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.content import Assessment, LearningPath, PathModule, Topic
from app.models.enums import (
    ContentStatus,
    CoverageLevel,
    CoveragePolicy,
    JobStatus,
    JobType,
    PathStatus,
    ProvenanceContentType,
)
from app.models.ingestion import ContentProvenance, GenerationJob
from app.modules.ai import arquitecto_ruta as fase_a
from app.modules.ai.esquemas_salida import SalidaRuta, esquema_estricto, validar
from app.modules.ai.proveedor import TAREA_PATH_DESIGN, SolicitudIA, plantilla_para_tarea


# ---------------------------------------------------------------------------
# Recuperación híbrida (§6.12)
# ---------------------------------------------------------------------------


def test_recuperacion_devuelve_fragmentos_con_traza(db, cfg, usuario, biblioteca) -> None:
    """La recuperación devuelve fragmentos ordenados y con su procedencia."""
    fragmentos = fase_a.recuperar(
        db,
        cfg,
        knowledge_base_id=biblioteca.id,
        user_id=usuario.id,
        consulta="JOIN filas tabla izquierda",
    )
    assert fragmentos
    assert fragmentos[0].rank == 1
    assert all(fragmento.document_title == "Manual de SQL.pdf" for fragmento in fragmentos)
    assert all(fragmento.document_version_id is not None for fragmento in fragmentos)
    assert "JOIN" in fragmentos[0].text


def test_recuperacion_respeta_el_tope(db, cfg, usuario, biblioteca) -> None:
    """`top_k` acota lo que se envía al modelo: cada token cuesta dinero."""
    fragmentos = fase_a.recuperar(
        db,
        cfg,
        knowledge_base_id=biblioteca.id,
        user_id=usuario.id,
        consulta="consulta filas",
        top_k=2,
    )
    assert len(fragmentos) <= 2


def test_recuperacion_aisla_por_usuario(db, cfg, biblioteca) -> None:
    """§8.7: el material de otro usuario jamás se recupera."""
    fragmentos = fase_a.recuperar(
        db,
        cfg,
        knowledge_base_id=biblioteca.id,
        user_id=uuid.uuid4(),
        consulta="JOIN",
    )
    assert fragmentos == []


def test_recuperacion_sin_biblioteca(db, cfg) -> None:
    """Una ruta sin material no recupera nada, y no revienta."""
    assert fase_a.recuperar(db, cfg, knowledge_base_id=None, consulta="lo que sea") == []


# ---------------------------------------------------------------------------
# Material insuficiente
# ---------------------------------------------------------------------------


def test_detecta_material_insuficiente(db, cfg, proveedor, ruta_sin_material) -> None:
    """Sin palabras suficientes no se diseña nada ni se llama al modelo (§5.8)."""
    with pytest.raises(fase_a.MaterialInsuficiente) as error:
        fase_a.disenar_ruta(
            db,
            cfg,
            proveedor,
            learning_path_id=ruta_sin_material.id,
            usuario_id=ruta_sin_material.user_id,
        )
    assert error.value.code == "DOCUMENT_UNREADABLE"
    assert error.value.status_code == 422
    assert error.value.details["min_words"] == 300
    assert error.value.details["words"] == 0
    # Ni una llamada: el freno es anterior al proveedor.
    assert proveedor.uso_acumulado.llamadas == 0


def test_informe_de_material(db, cfg, biblioteca) -> None:
    """El informe mide el corpus vigente y decide si alcanza."""
    informe = fase_a.evaluar_material(db, cfg, biblioteca.id)
    assert informe.suficiente is True
    assert informe.words >= informe.min_words
    assert len(informe.document_version_ids) == 1


# ---------------------------------------------------------------------------
# Diseño de la ruta
# ---------------------------------------------------------------------------


def test_la_salida_del_proveedor_valida_contra_el_esquema(db, cfg, proveedor, usuario, biblioteca) -> None:
    """El esquema de ruta que produce el proveedor cumple el esquema estricto."""
    fragmentos = fase_a.recuperar(
        db, cfg, knowledge_base_id=biblioteca.id, user_id=usuario.id, consulta="SQL"
    )
    plantilla = plantilla_para_tarea(db, TAREA_PATH_DESIGN)
    solicitud = SolicitudIA(
        tarea=TAREA_PATH_DESIGN,
        sistema=plantilla.body,
        instruccion="Diseña la ruta.",
        fragmentos=fragmentos,
        datos={"area_name": "SQL", "modules_min": 4, "modules_max": 10},
        esquema=esquema_estricto(SalidaRuta),
    )
    salida = validar(SalidaRuta, proveedor.generar_estructurado(solicitud).contenido)
    assert 4 <= len(salida.modules) <= 10
    assert all(modulo.topics for modulo in salida.modules)
    assert all(tema.learning_objectives for modulo in salida.modules for tema in modulo.topics)


def test_disena_y_persiste_la_ruta(db, cfg, proveedor, ruta) -> None:
    """La Fase A persiste módulos, temas, evaluaciones y procedencia."""
    resultado = fase_a.disenar_ruta(
        db, cfg, proveedor, learning_path_id=ruta.id, usuario_id=ruta.user_id
    )

    assert resultado.desde_cache is False
    assert 4 <= resultado.modules <= 10
    assert resultado.topics >= resultado.modules

    modulos = list(
        db.execute(
            sa.select(PathModule)
            .where(PathModule.learning_path_id == ruta.id)
            .order_by(PathModule.position)
        ).scalars()
    )
    assert [m.position for m in modulos] == list(range(1, len(modulos) + 1))
    assert all(m.content_status is ContentStatus.PENDING for m in modulos)
    # El MVP es lineal: cada módulo apunta al anterior.
    assert modulos[0].prerequisite_module_id is None
    assert modulos[1].prerequisite_module_id == modulos[0].id

    temas = list(
        db.execute(
            sa.select(Topic).where(Topic.module_id.in_([m.id for m in modulos]))
        ).scalars()
    )
    assert temas
    assert all(tema.learning_objectives for tema in temas)
    respaldados = [tema for tema in temas if tema.source_chunk_ids]
    assert respaldados, "algún tema debe citar fragmentos reales del material"

    # Cada módulo termina en su evaluación, todavía sin banco.
    evaluaciones = list(
        db.execute(
            sa.select(Assessment).where(Assessment.module_id.in_([m.id for m in modulos]))
        ).scalars()
    )
    assert len(evaluaciones) == len(modulos)
    assert all(e.question_count == 10 and e.bank_size == 25 for e in evaluaciones)
    assert all(e.pass_score == 70 for e in evaluaciones)

    # Procedencia de cada tema.
    procedencias = list(
        db.execute(
            sa.select(ContentProvenance).where(
                ContentProvenance.content_type == ProvenanceContentType.TOPIC
            )
        ).scalars()
    )
    assert len(procedencias) >= len(temas)
    assert any(p.chunk_id is not None for p in procedencias)

    # Estado de la ruta y del trabajo.
    db.refresh(ruta)
    assert ruta.status is PathStatus.PENDING_REVIEW
    assert ruta.module_count == len(modulos)
    assert ruta.generated_by_job_id is not None

    job = db.get(GenerationJob, resultado.job_id)
    assert job is not None
    assert job.job_type is JobType.PATH_DESIGN
    assert job.status is JobStatus.SUCCEEDED
    assert job.input_tokens > 0 and job.output_tokens > 0
    assert job.progress_pct == 100


def test_no_vuelve_a_disenar_si_ya_hay_estructura(db, cfg, proveedor, ruta) -> None:
    """Una ruta ya diseñada no gasta otra llamada: se devuelve de caché."""
    fase_a.disenar_ruta(db, cfg, proveedor, learning_path_id=ruta.id, usuario_id=ruta.user_id)
    llamadas = proveedor.uso_acumulado.llamadas

    segundo = fase_a.disenar_ruta(
        db, cfg, proveedor, learning_path_id=ruta.id, usuario_id=ruta.user_id
    )
    assert segundo.desde_cache is True
    assert segundo.modules > 0
    assert proveedor.uso_acumulado.llamadas == llamadas


def test_politica_source_only_descarta_lo_no_respaldado(db, cfg, proveedor, ruta) -> None:
    """Con `source_only` un tema sin respaldo se elimina y se avisa al estudiante."""
    ruta.coverage_policy = CoveragePolicy.SOURCE_ONLY
    db.flush()

    resultado = fase_a.disenar_ruta(
        db, cfg, proveedor, learning_path_id=ruta.id, usuario_id=ruta.user_id
    )
    temas = list(
        db.execute(
            sa.select(Topic)
            .join(PathModule, PathModule.id == Topic.module_id)
            .where(PathModule.learning_path_id == ruta.id)
        ).scalars()
    )
    assert temas
    assert all(tema.coverage is not CoverageLevel.INSUFFICIENT for tema in temas)
    assert any("se quitó" in nota for nota in resultado.coverage_notes)


def test_politica_model_knowledge_conserva_y_avisa(db, cfg, proveedor, ruta) -> None:
    """Con `model_knowledge` el hueco se conserva marcado y con su aviso de cobertura."""
    assert ruta.coverage_policy is CoveragePolicy.MODEL_KNOWLEDGE
    resultado = fase_a.disenar_ruta(
        db, cfg, proveedor, learning_path_id=ruta.id, usuario_id=ruta.user_id
    )
    db.refresh(ruta)
    assert resultado.coverage_notes
    assert ruta.coverage_notes == resultado.coverage_notes
    temas = list(
        db.execute(
            sa.select(Topic)
            .join(PathModule, PathModule.id == Topic.module_id)
            .where(PathModule.learning_path_id == ruta.id)
        ).scalars()
    )
    assert any(tema.coverage is CoverageLevel.INSUFFICIENT for tema in temas)


def test_descarta_citas_inventadas(db, cfg, proveedor, ruta) -> None:
    """Un `source_chunk_ids` que no existe entre lo recuperado no respalda nada."""
    fase_a.disenar_ruta(db, cfg, proveedor, learning_path_id=ruta.id, usuario_id=ruta.user_id)
    validos = {
        str(fila[0])
        for fila in db.execute(
            sa.select(ContentProvenance.chunk_id).where(
                ContentProvenance.chunk_id.is_not(None)
            )
        ).all()
    }
    temas = list(
        db.execute(
            sa.select(Topic)
            .join(PathModule, PathModule.id == Topic.module_id)
            .where(PathModule.learning_path_id == ruta.id)
        ).scalars()
    )
    for tema in temas:
        for citado in tema.source_chunk_ids or []:
            assert str(citado) in validos


def test_la_ruta_ajena_no_existe(db, cfg, proveedor, ruta) -> None:
    """§8.7: pedir la ruta de otro usuario devuelve 404, no 403."""
    from app.core.errors import NotFound

    with pytest.raises(NotFound):
        fase_a.disenar_ruta(
            db, cfg, proveedor, learning_path_id=ruta.id, usuario_id=uuid.uuid4()
        )


def test_ruta_inexistente(db, cfg, proveedor) -> None:
    """Un identificador que no existe es un 404 limpio."""
    from app.core.errors import NotFound

    with pytest.raises(NotFound):
        fase_a.disenar_ruta(db, cfg, proveedor, learning_path_id=uuid.uuid4())


def test_la_ruta_del_reino_no_tiene_dueno(db, cfg, proveedor, ruta) -> None:
    """Una Ruta del Reino (`user_id IS NULL`) la puede generar cualquier usuario (D17)."""
    from app.models.identity import User

    otro = User(
        email=f"otro-{uuid.uuid4().hex[:10]}@atenea.test",
        password_hash="x" * 20,
        timezone="America/Santiago",
    )
    db.add(otro)
    ruta.user_id = None
    db.flush()
    resultado = fase_a.disenar_ruta(
        db, cfg, proveedor, learning_path_id=ruta.id, usuario_id=otro.id
    )
    assert resultado.modules > 0
    assert db.get(LearningPath, ruta.id).status is PathStatus.PENDING_REVIEW
