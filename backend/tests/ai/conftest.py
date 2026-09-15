"""Fixtures de la capa de IA.

Todas las pruebas usan el **proveedor simulado** (determinista, sin red y sin coste) y
la base de desarrollo dentro de una transacción que se revierte al terminar: no dejan
rastro ni gastan un céntimo.

Las semillas de `game_configs` reproducen literalmente los valores de CONTRACT.md §5
que la capa de IA necesita (`ai.*`, `content.*`, `ingestion.*`, `mastery.*`).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.content import KnowledgeArea, LearningPath
from app.models.enums import (
    ChunkType,
    CoveragePolicy,
    DeclaredLevel,
    DocumentStatus,
    DocumentType,
    KnowledgeCategory,
    PathOrigin,
    PathSourceMode,
    PathStatus,
)
from app.models.gamification import GameConfig
from app.models.identity import User
from app.models.ingestion import Document, DocumentChunk, DocumentVersion, KnowledgeBase
from app.modules.ai.proveedor import crear_proveedor
from app.modules.ai.simulado import ProveedorSimulado
from app.modules.gamification import servicio_config
from app.modules.gamification.servicio_config import ServicioConfig

URL_BASE_PRUEBAS = "postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea_test"

#: Versión de `game_configs` propia de esta suite. La tabla es única por
#: (key, version): con una versión distinta por módulo, dos suites pueden
#: sembrar la misma clave a la vez sin esperarse una a otra.
VERSION_SEMILLA = 5

#: Semillas de `game_configs` que consume la capa de IA (CONTRACT.md §5.5 y §5.8).
SEMILLAS_CONFIG: dict[str, tuple[Any, str, bool]] = {
    # §5.8 contenido
    "content.lesson.target_minutes": ({"min": 5, "max": 15, "default": 9}, "map", True),
    "content.module.topics": ({"min": 2, "max": 6}, "map", False),
    "content.path.modules": ({"min": 4, "max": 10}, "map", False),
    "content.topic.lessons": ({"min": 1, "max": 3}, "map", False),
    "content.questions_per_topic": (5, "int", False),
    "content.open_questions_per_lesson_max": (1, "int", False),
    "content.challenges_per_module_max": (1, "int", False),
    "content.difficulty_distribution": ({"easy": 0.50, "medium": 0.35, "hard": 0.15}, "map", False),
    "content.mvp_question_types": (
        [
            "multiple_choice",
            "true_false",
            "fill_blank",
            "matching",
            "ordering",
            "open_short",
            "sql_exercise",
        ],
        "list",
        True,
    ),
    # §5.8 ingesta
    "ingestion.min_words_for_path": (300, "int", True),
    "ingestion.max_corpus_tokens": (150000, "int", False),
    # §5.8 IA
    "ai.models": (
        {
            "path_design": "claude-opus-5",
            "lesson": "claude-sonnet-5",
            "questions": "claude-sonnet-5",
            "judge": "claude-haiku-4-5",
            "judge_escalation": "claude-sonnet-5",
            "narrative": "claude-haiku-4-5",
            "groundedness": "claude-haiku-4-5",
        },
        "map",
        False,
    ),
    "ai.embeddings": (
        {"provider": "voyage", "model": "voyage-3-lite", "dimensions": 512, "batch_size": 128},
        "map",
        False,
    ),
    "ai.retrieval": (
        {
            "vector_top_k": 20,
            "lexical_top_k": 20,
            "rrf_k": 60,
            "design_bonus": 0.02,
            "final_top_k": 10,
            "reexplain_top_k": 6,
            "min_score_ratio": 0.4,
        },
        "map",
        False,
    ),
    "ai.judge": (
        {
            "correct_score": 70,
            "partial_score": 40,
            "min_confidence": 0.6,
            "benefit_of_doubt_score": 60,
            "min_words": 3,
        },
        "map",
        False,
    ),
    "ai.quotas_per_day": (
        {
            "path_designs": 2,
            "active_paths": 3,
            "re_explanations": 10,
            "judged_answers": 50,
            "content_reports": 10,
            "upload_mb": 100,
            "module_regenerations": 2,
        },
        "map",
        True,
    ),
    "ai.global_budget_usd_per_day": (30, "int", False),
    "ai.budget_thresholds": ([0.8, 1.0], "list", False),
    "ai.sql_sandbox": (
        {
            "engine": "duckdb",
            "timeout_ms": 2000,
            "memory_limit_mb": 256,
            "max_rows": 10000,
            "max_tables": 5,
            "max_rows_per_table": 200,
        },
        "map",
        False,
    ),
    "ai.generation_targets": ({"skeleton_seconds": 90, "first_module_seconds": 90}, "map", False),
    # §5.5 dominio (lo que usan la evaluación y el adaptativo)
    "mastery.assessment.pass_score": (70, "int", True),
    "mastery.assessment.question_count": (10, "int", True),
    "mastery.assessment.bank_ratio": (2.5, "decimal", False),
    "mastery.assessment.max_attempts_per_day": (2, "int", True),
    "mastery.weakness_rules": (
        {
            "R1_errors_in_last_10": 3,
            "R2_accuracy_lt": 50,
            "R2_min_attempts": 5,
            "R3_assessment_topic_lt": 60,
            "R4_time_multiplier": 2.0,
            "R4_min_questions": 2,
            "R5_objective_zero_of": 3,
        },
        "map",
        False,
    ),
}

#: Corpus sintético: da de sobra para las 300 palabras mínimas de una ruta.
TEXTOS_MATERIAL: list[tuple[str, list[str]]] = [
    (
        "Una consulta SELECT recupera filas de una tabla. La cláusula WHERE filtra esas "
        "filas antes de devolverlas y se evalúa fila a fila. Sin WHERE, la consulta "
        "devuelve la tabla entera, lo que en tablas grandes es un error caro. "
        "El orden de las columnas de la proyección no altera el conjunto de filas.",
        ["Capítulo 1. Consultas básicas", "SELECT y WHERE"],
    ),
    (
        "Un INNER JOIN devuelve solo las filas que casan en ambas tablas. Un LEFT JOIN "
        "devuelve todas las filas de la tabla izquierda y rellena con nulos las columnas "
        "de la derecha cuando no hay coincidencia. Confundir ambos es la causa más "
        "frecuente de informes con filas perdidas.",
        ["Capítulo 2. JOINs", "INNER frente a LEFT"],
    ),
    (
        "Las funciones de agregación resumen un conjunto de filas en un solo valor: "
        "COUNT cuenta filas, SUM suma valores y AVG promedia. GROUP BY define los grupos "
        "sobre los que se calcula la agregación, y HAVING filtra esos grupos ya "
        "calculados, a diferencia de WHERE, que filtra filas antes de agrupar.",
        ["Capítulo 3. Agregación", "GROUP BY y HAVING"],
    ),
    (
        "Los índices aceleran la búsqueda a cambio de encarecer la escritura. Un índice "
        "sobre la columna que filtra una consulta evita recorrer la tabla completa. "
        "Crear índices sin medir es tan perjudicial como no crear ninguno.",
        ["Capítulo 4. Rendimiento", "Índices"],
    ),
    (
        "Una transacción agrupa varias operaciones en una unidad atómica: o se aplican "
        "todas o no se aplica ninguna. COMMIT confirma los cambios y ROLLBACK los "
        "deshace. El aislamiento evita que dos transacciones simultáneas se pisen.",
        ["Capítulo 5. Transacciones", "COMMIT y ROLLBACK"],
    ),
]


@pytest.fixture(scope="session")
def conexion() -> Iterator[sa.Connection]:
    """Conexión única con una transacción externa que se revierte al terminar."""
    motor = sa.create_engine(URL_BASE_PRUEBAS, future=True)
    conn = motor.connect()
    transaccion = conn.begin()
    try:
        yield conn
    finally:
        transaccion.rollback()
        conn.close()
        motor.dispose()


@pytest.fixture(scope="session", autouse=True)
def semillas(conexion: sa.Connection) -> Iterator[None]:
    """Siembra `game_configs` dentro de la transacción de prueba.

    Si la base de desarrollo ya tiene la semilla oficial cargada (las 177 claves de §5),
    no se duplica nada: solo se añaden las claves que falten. Así la suite funciona tanto
    contra una base recién migrada como contra una ya sembrada.
    """
    servicio_config.invalidar_cache()
    sesion = Session(bind=conexion, join_transaction_mode="create_savepoint")
    existentes = {
        fila[0]
        for fila in sesion.execute(
            sa.select(GameConfig.key).where(GameConfig.key.in_(list(SEMILLAS_CONFIG)))
        ).all()
    }
    # Un día atrás a propósito. `valid_from <= now()` se evalúa con
    # `transaction_timestamp()`, que es el instante en que **empezó** la
    # transacción externa de la conexión de pruebas, no el de la consulta. Si esa
    # transacción arrancó antes que esta siembra —y quién la arranca depende de
    # qué fixture toque la conexión primero, o sea del orden de la ejecución—,
    # una marca de «ahora» queda en el futuro y la configuración entera se vuelve
    # invisible para la suite completa. De ahí venían los fallos intermitentes
    # con `ConfiguracionAusente` y respuestas 500 en suites que pasaban solas.
    ahora = utcnow() - timedelta(days=1)
    for clave, (valor, tipo, publico) in SEMILLAS_CONFIG.items():
        if clave in existentes:
            continue
        version = sesion.execute(sa.text("SELECT nextval('game_config_version_seq')")).scalar()
        sesion.add(
            GameConfig(
                key=clave,
                version=VERSION_SEMILLA,
                config_version=int(version or 1),
                value=valor,
                value_type=tipo,
                valid_from=ahora,
                is_public=publico,
            )
        )
    sesion.commit()
    sesion.close()
    yield
    servicio_config.invalidar_cache()


@pytest.fixture
def db(conexion: sa.Connection, semillas: None) -> Iterator[Session]:
    """Sesión de prueba sobre un savepoint: cada prueba se revierte al terminar."""
    sesion = Session(bind=conexion, join_transaction_mode="create_savepoint")
    try:
        yield sesion
    finally:
        sesion.rollback()
        sesion.close()


@pytest.fixture
def cfg(db: Session) -> ServicioConfig:
    """Servicio de configuración apuntando a la sesión de prueba."""
    servicio_config.invalidar_cache()
    return ServicioConfig(db)


@pytest.fixture
def proveedor() -> ProveedorSimulado:
    """Proveedor simulado: determinista, sin red y sin coste."""
    creado = crear_proveedor("mock")
    assert isinstance(creado, ProveedorSimulado)
    return creado


@pytest.fixture
def usuario(db: Session) -> User:
    """Usuario de prueba con zona horaria de Santiago."""
    fila = User(
        email=f"ai-{uuid.uuid4().hex[:12]}@atenea.test",
        password_hash="x" * 20,
        timezone="America/Santiago",
    )
    db.add(fila)
    db.flush()
    return fila


@pytest.fixture
def area(db: Session) -> KnowledgeArea:
    """Conocimiento canónico de prueba."""
    fila = KnowledgeArea(
        slug=f"sql-{uuid.uuid4().hex[:8]}",
        name="SQL",
        short_name="SQL",
        category=KnowledgeCategory.DATA,
        is_canonical=True,
    )
    db.add(fila)
    db.flush()
    return fila


@pytest.fixture
def biblioteca(db: Session, usuario: User) -> KnowledgeBase:
    """Biblioteca con un documento real, su versión vigente y sus fragmentos."""
    base = KnowledgeBase(user_id=usuario.id, name="Material de SQL", is_default=True)
    db.add(base)
    db.flush()

    documento = Document(
        knowledge_base_id=base.id,
        user_id=usuario.id,
        title="Manual de SQL.pdf",
        document_type=DocumentType.PDF,
        status=DocumentStatus.READY,
        version_count=1,
    )
    db.add(documento)
    db.flush()

    palabras = sum(len(texto.split()) for texto, _ in TEXTOS_MATERIAL)
    version = DocumentVersion(
        document_id=documento.id,
        version_number=1,
        content_hash=hashlib.sha256(b"manual-sql").hexdigest(),
        storage_key="local/manual-sql.pdf",
        byte_size=120_000,
        page_count=42,
        word_count=palabras * 4,  # supera con holgura ingestion.min_words_for_path
        token_count=palabras * 6,
        chunk_count=len(TEXTOS_MATERIAL),
        language="es",
        status=DocumentStatus.READY,
        is_current=True,
        processed_at=utcnow(),
    )
    db.add(version)
    db.flush()

    for indice, (texto, encabezados) in enumerate(TEXTOS_MATERIAL):
        db.add(
            DocumentChunk(
                document_version_id=version.id,
                document_id=documento.id,
                knowledge_base_id=base.id,
                user_id=usuario.id,
                chunk_index=indice,
                chunk_type=ChunkType.PROSE,
                heading_path=encabezados,
                text=texto,
                token_count=len(texto.split()) * 2,
                page_start=indice * 8 + 1,
                page_end=indice * 8 + 6,
                language="es",
                content_hash=hashlib.sha256(texto.encode("utf-8")).hexdigest(),
            )
        )
    base.document_count = 1
    base.total_tokens = version.token_count or 0
    db.flush()
    return base


@pytest.fixture
def ruta(db: Session, usuario: User, area: KnowledgeArea, biblioteca: KnowledgeBase) -> LearningPath:
    """Ruta de usuario lista para la Fase A."""
    fila = LearningPath(
        user_id=usuario.id,
        knowledge_area_id=area.id,
        title="Maestro de SQL",
        goal_text="Quiero aprender SQL para analizar datos en el trabajo",
        declared_level=DeclaredLevel.BEGINNER,
        source_mode=PathSourceMode.WITH_SOURCE,
        origin=PathOrigin.USER,
        status=PathStatus.DRAFT,
        language="es",
        knowledge_base_id=biblioteca.id,
        coverage_policy=CoveragePolicy.MODEL_KNOWLEDGE,
    )
    db.add(fila)
    db.flush()
    return fila


@pytest.fixture
def ruta_sin_material(db: Session, usuario: User, area: KnowledgeArea) -> LearningPath:
    """Ruta con una biblioteca vacía: sirve para probar el material insuficiente."""
    base = KnowledgeBase(user_id=usuario.id, name="Biblioteca vacía")
    db.add(base)
    db.flush()
    fila = LearningPath(
        user_id=usuario.id,
        knowledge_area_id=area.id,
        title="Ruta sin material",
        goal_text="Aprender algo",
        declared_level=DeclaredLevel.BEGINNER,
        source_mode=PathSourceMode.WITH_SOURCE,
        origin=PathOrigin.USER,
        status=PathStatus.DRAFT,
        knowledge_base_id=base.id,
    )
    db.add(fila)
    db.flush()
    return fila
