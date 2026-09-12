"""Utilidades comunes de las pruebas del módulo `progress`.

Dos clases de prueba, como pide el contrato (§8.10):

* **Lógica pura** — no tocan la base de datos. Usan la fixture `cfg`, que arma un
  `ConfigDominio` con los valores literales de la tabla §5.5 del contrato. Esos
  números viven **aquí** (en la prueba, como oráculo) y nunca en el código de la app.
* **Con base de datos** — usan la base real de desarrollo dentro de una transacción
  que **siempre se revierte**, así que no dejan rastro.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from app.models.content import (
    Assessment,
    KnowledgeArea,
    LearningPath,
    Lesson,
    PathModule,
    Question,
    Topic,
)
from app.models.enums import (
    ActivityContext,
    AttemptResult,
    AttemptStatus,
    DifficultyLevel,
    EvaluationMethod,
    KnowledgeCategory,
    QuestionType,
    StudyActivityType,
)
from app.models.gamification import GameConfig
from app.models.identity import User
from app.models.progress import AssessmentAttempt, QuestionAttempt, StudyActivity
from app.modules.progress.dominio import ConfigDominio, Evidencia
from app.modules.progress.sesiones import ConfigTiempo

URL_BASE_DE_PRUEBAS = "postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea_test"
ZONA = "America/Santiago"
UTC = timezone.utc

# ---------------------------------------------------------------------------
# Valores canónicos de `game_configs` (CONTRACT.md §5.5 y §5.6)
# ---------------------------------------------------------------------------

CONFIG_SEMILLA: dict[str, object] = {
    "goal.activity_units": {
        "lesson": 1,
        "review": 1,
        "challenge": 1,
        "assessment": 2,
        "questions_block": 1,
        "questions_per_block": 5,
    },
    "streak.min_daily_educational_xp": 30,
    "streak.sync_tolerance_min": 10,
    "streak.milestones": [7, 14, 30, 60, 100, 365],
    # mastery.*  (§5.5)
    "mastery.weight.difficulty": {"easy": 1.0, "medium": 1.5, "hard": 2.0},
    "mastery.weight.context": {
        "lesson": 1.0,
        "practice": 1.0,
        "review": 1.0,
        "challenge": 1.5,
        "assessment": 2.0,
    },
    "mastery.weight.retake": [1.0, 0.6, 0.3],
    "mastery.correctness_second_try": 0.5,
    "mastery.recency_half_life_days": 30,
    "mastery.prior_m": 3,
    "mastery.prior_p0": 0.5,
    "mastery.evidence_window": {"max_items": 40, "max_days": 180},
    "mastery.coverage_floor": 0.6,
    "mastery.decay": {
        "grace_days": 7,
        "floor": 0.6,
        "half_life_days": 60,
        "stability_factor": 1.5,
        "half_life_max_days": 365,
    },
    "mastery.module.weight_topics": 0.70,
    "mastery.module.weight_assessment": 0.30,
    "mastery.assessment.pass_score": 70,
    "mastery.assessment.retake_penalty": {"per_attempt": 0.05, "max": 0.15},
    "mastery.threshold.mastered": 80,
    "mastery.threshold.at_risk": 70,
    "mastery.threshold.weak_practice": 50,
    "mastery.weak_min_evidence": 5,
    "mastery.review.stability_min_score": 70,
    "mastery.area_mastered_requires_completed_path": True,
    # time.*  (§5.6)
    "time.heartbeat_s": 30,
    "time.max_tick_s": 60,
    "time.idle_cutoff_s": 120,
    "time.max_activity_multiplier": 3,
    "time.session_idle_timeout_min": 10,
    # goal.* y recompensas que usa el panel (§5.1, §5.3, §5.6)
    "goal.default": {"type": "minutos", "target": 20},
    "goal.bonus_gold_base": 10,
    "goal.bonus_gold_cap_days": 20,
    "streak.grace_per_month": 1,
    "xp.lesson_completed": 50,
    "gold.lesson_completed": 20,
}


# ---------------------------------------------------------------------------
# Fixtures de lógica pura
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def cfg() -> ConfigDominio:
    """`ConfigDominio` con los valores canónicos del contrato §5.5."""
    return ConfigDominio(
        pesos_dificultad=dict(CONFIG_SEMILLA["mastery.weight.difficulty"]),
        pesos_contexto=dict(CONFIG_SEMILLA["mastery.weight.context"]),
        pesos_reintento=tuple(CONFIG_SEMILLA["mastery.weight.retake"]),
        acierto_segundo_intento=0.5,
        media_vida_recencia_dias=30.0,
        prior_m=3.0,
        prior_p0=0.5,
        ventana_max_items=40,
        ventana_max_dias=180,
        piso_cobertura=0.6,
        decaimiento_gracia_dias=7.0,
        decaimiento_piso=0.6,
        decaimiento_media_vida_dias=60.0,
        decaimiento_factor_estabilidad=1.5,
        decaimiento_media_vida_max_dias=365.0,
        peso_modulo_temas=0.70,
        peso_modulo_evaluacion=0.30,
        puntaje_aprobacion=70.0,
        penalizacion_reintento_por_intento=0.05,
        penalizacion_reintento_max=0.15,
        umbral_dominado=80.0,
        umbral_en_riesgo=70.0,
        umbral_practica_debil=50.0,
        evidencias_minimas_debilidad=5,
        repaso_puntaje_min_estabilidad=70.0,
        area_exige_ruta_completa=True,
    )


@pytest.fixture(scope="session")
def cfg_tiempo() -> ConfigTiempo:
    """`ConfigTiempo` con los valores canónicos del contrato §5.6."""
    return ConfigTiempo(
        heartbeat_s=30,
        max_tick_s=60,
        idle_cutoff_s=120,
        max_activity_multiplier=3,
        session_idle_timeout_min=10,
    )


@pytest.fixture(scope="session")
def ahora() -> datetime:
    """Instante fijo de referencia para las pruebas puras."""
    return datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def _crear_evidencia(
    *,
    dias_atras: float = 0.0,
    dificultad: DifficultyLevel = DifficultyLevel.MEDIUM,
    contexto: ActivityContext = ActivityContext.LESSON,
    intento: int = 1,
    acierto: float = 1.0,
    base: datetime | None = None,
) -> Evidencia:
    """Fábrica corta de evidencias para las pruebas puras."""
    referencia = base or datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    return Evidencia(
        answered_at=referencia - timedelta(days=dias_atras),
        difficulty=dificultad,
        context=contexto,
        attempt_no=intento,
        correctness_weight=acierto,
    )


@pytest.fixture
def evidencia():
    """Fábrica de evidencias para las pruebas puras (se usa como función)."""
    return _crear_evidencia


# ---------------------------------------------------------------------------
# Fixtures con base de datos
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def engine():
    """Motor contra la base real de desarrollo; se omite la prueba si no responde."""
    motor = sa.create_engine(URL_BASE_DE_PRUEBAS, future=True)
    try:
        with motor.connect() as conexion:
            conexion.execute(sa.text("select 1"))
    except Exception as exc:  # pragma: no cover - depende del entorno local
        pytest.skip(f"La base de datos de desarrollo no está disponible: {exc}")
    yield motor
    motor.dispose()


@pytest.fixture
def db(engine) -> Session:
    """Sesión dentro de una transacción que **siempre** se revierte al terminar."""
    conexion = engine.connect()
    transaccion = conexion.begin()
    fabrica = sessionmaker(bind=conexion, join_transaction_mode="create_savepoint")
    sesion = fabrica()
    try:
        yield sesion
    finally:
        sesion.close()
        transaccion.rollback()
        conexion.close()


@pytest.fixture
def config_sembrada(db: Session) -> None:
    """Inserta las claves de `game_configs` que necesita el módulo (§5)."""
    # ATENEA_LIMPIEZA_CONFIG: varias suites siembran las mismas claves de
    # `game_configs`, que es única por (key, version). Se borran antes de
    # insertarlas para que el orden de ejecución no importe.
    db.execute(sa.delete(GameConfig))
    db.flush()

    # Base: la configuración canónica completa del juego. Estas pruebas ejercitan
    # el motor de gamificación (los latidos alimentan el objetivo diario), y el
    # motor consulta muchas más claves de las que este módulo declara. Sembrar
    # solo un subconjunto obligaría a perseguir claves una a una cada vez que el
    # motor consulte una nueva.
    from app.seeds.config_juego import PARAMETROS

    claves_propias = set(CONFIG_SEMILLA)
    version_config = 0
    for parametro in PARAMETROS:
        if parametro.key in claves_propias:
            continue  # el valor de esta suite manda: es su oráculo
        version_config += 1
        db.add(
            GameConfig(
                key=parametro.key,
                version=1,
                config_version=version_config,
                value=parametro.value,
                value_type=parametro.value_type,
                is_public=parametro.is_public,
            )
        )

    # Encima, los valores que esta suite fija como oráculo de §5.5 y §5.6.
    for clave, valor in CONFIG_SEMILLA.items():
        version_config += 1
        db.add(
            GameConfig(
                key=clave,
                version=1,
                config_version=version_config,
                value=valor,
                value_type=_tipo_de_valor(valor),
                is_public=False,
            )
        )
    db.flush()
    _sembrar_niveles_minimos(db)
    # La caché del servicio de configuración es de proceso: si otra suite la
    # llenó antes, estas claves recién sembradas serían invisibles.
    from app.modules.gamification import servicio_config

    servicio_config.invalidar_cache()


def _sembrar_niveles_minimos(db: Session) -> None:
    """Tabla de niveles mínima para que el motor pueda resolver un nivel.

    Los latidos de tiempo pasan por el motor de gamificación (alimentan el
    objetivo diario y la racha), y el motor resuelve el nivel del usuario desde
    `level_definitions`. Sin estas filas, cualquier prueba que registre tiempo
    fallaría por una tabla vacía, no por lo que quiere comprobar.
    """
    from app.models.enums import LevelScope
    from app.models.gamification import LevelDefinition

    existe = db.execute(
        sa.select(sa.literal(1))
        .select_from(LevelDefinition)
        .where(LevelDefinition.scope == LevelScope.GLOBAL)
        .limit(1)
    ).scalar_one_or_none()
    if existe:
        return

    acumulado = 0
    for nivel in range(1, 21):
        delta = 0 if nivel == 1 else 100 * nivel
        acumulado += delta
        db.add(
            LevelDefinition(
                scope=LevelScope.GLOBAL,
                level=nivel,
                xp_required=acumulado,
                xp_delta=delta,
                rank_title="Aprendiz" if nivel < 5 else "Escudero",
                is_rank_start=nivel in (1, 5),
                unlocks={},
            )
        )
    db.flush()


def _tipo_de_valor(valor: object) -> str:
    if isinstance(valor, bool):
        return "bool"
    if isinstance(valor, int):
        return "int"
    if isinstance(valor, float):
        return "decimal"
    if isinstance(valor, list):
        return "list"
    if isinstance(valor, dict):
        return "map"
    return "string"


@pytest.fixture
def usuario(db: Session) -> User:
    """Usuario de prueba con zona horaria de Chile."""
    fila = User(
        email=f"prueba-{uuid.uuid4().hex[:12]}@atenea.test",
        password_hash="x" * 20,
        timezone=ZONA,
    )
    db.add(fila)
    db.flush()
    return fila


class Contenido:
    """Grafo mínimo de contenido: conocimiento → ruta → módulo → tema → lecciones."""

    def __init__(
        self,
        area: KnowledgeArea,
        ruta: LearningPath,
        modulo: PathModule,
        modulo2: PathModule,
        tema: Topic,
        lecciones: list[Lesson],
        assessment: Assessment,
        pregunta: Question,
    ) -> None:
        self.area = area
        self.ruta = ruta
        self.modulo = modulo
        self.modulo2 = modulo2
        self.tema = tema
        self.lecciones = lecciones
        self.assessment = assessment
        self.pregunta = pregunta


@pytest.fixture
def contenido(db: Session) -> Contenido:
    """Crea un conocimiento con una ruta de dos módulos, un tema y dos lecciones."""
    sufijo = uuid.uuid4().hex[:8]
    area = KnowledgeArea(
        slug=f"sql-{sufijo}",
        name="SQL",
        short_name="SQL",
        category=KnowledgeCategory.DATA,
    )
    db.add(area)
    db.flush()

    ruta = LearningPath(knowledge_area_id=area.id, title="Dominar SQL")
    db.add(ruta)
    db.flush()

    modulo = PathModule(learning_path_id=ruta.id, position=1, title="Consultas", lesson_count=2)
    modulo2 = PathModule(learning_path_id=ruta.id, position=2, title="Agregaciones", lesson_count=0)
    db.add_all([modulo, modulo2])
    db.flush()

    tema = Topic(module_id=modulo.id, position=1, title="JOINs", lesson_count=2)
    db.add(tema)
    db.flush()

    lecciones = [
        Lesson(topic_id=tema.id, position=1, title="INNER JOIN", estimated_seconds=540),
        Lesson(topic_id=tema.id, position=2, title="LEFT JOIN", estimated_seconds=540),
    ]
    db.add_all(lecciones)

    assessment = Assessment(module_id=modulo.id, title="Prueba del módulo")
    pregunta = Question(
        topic_id=tema.id,
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=DifficultyLevel.HARD,
        stem="¿Qué hace un INNER JOIN?",
        answer_key={"correct": "a"},
    )
    db.add_all([assessment, pregunta])
    db.flush()
    return Contenido(area, ruta, modulo, modulo2, tema, lecciones, assessment, pregunta)


def registrar_respuesta(
    db: Session,
    usuario: User,
    contenido: Contenido,
    *,
    correcta: bool,
    dificultad: DifficultyLevel = DifficultyLevel.HARD,
    contexto: ActivityContext = ActivityContext.LESSON,
    intento: int = 1,
    cuando: datetime | None = None,
) -> QuestionAttempt:
    """Inserta una evidencia real en `question_attempts`."""
    momento = cuando or datetime.now(UTC)
    peso = 1.0 if (correcta and intento == 1) else (0.5 if (correcta and intento == 2) else 0.0)
    fila = QuestionAttempt(
        user_id=usuario.id,
        question_id=contenido.pregunta.id,
        topic_id=contenido.tema.id,
        knowledge_area_id=contenido.area.id,
        context=contexto,
        attempt_no=intento,
        response={"choice": "a"},
        result=AttemptResult.CORRECT if correcta else AttemptResult.INCORRECT,
        is_correct=correcta,
        correctness_weight=peso,
        difficulty=dificultad,
        evaluation_method=EvaluationMethod.DETERMINISTIC,
        response_ms=6400,
        answered_at=momento,
        local_date=momento.date(),
        idempotency_key=str(uuid.uuid4()),
    )
    db.add(fila)
    db.flush()
    return fila


def registrar_evaluacion(
    db: Session,
    usuario: User,
    contenido: Contenido,
    *,
    puntaje: float,
    intento: int = 1,
    cuando: datetime | None = None,
) -> AssessmentAttempt:
    """Inserta un intento de evaluación ya enviado."""
    momento = cuando or datetime.now(UTC)
    fila = AssessmentAttempt(
        user_id=usuario.id,
        assessment_id=contenido.assessment.id,
        module_id=contenido.modulo.id,
        learning_path_id=contenido.ruta.id,
        knowledge_area_id=contenido.area.id,
        attempt_no=intento,
        status=AttemptStatus.SUBMITTED,
        question_count=10,
        correct_count=int(puntaje / 10),
        score=puntaje,
        submitted_at=momento,
        local_date=momento.date(),
        idempotency_key=str(uuid.uuid4()),
    )
    db.add(fila)
    db.flush()
    return fila


def crear_actividad(
    db: Session,
    usuario: User,
    contenido: Contenido,
    *,
    sesion_id: uuid.UUID | None = None,
    cuando: datetime | None = None,
) -> StudyActivity:
    """Abre una `study_activities` de tipo lección."""
    momento = cuando or datetime.now(UTC)
    fila = StudyActivity(
        user_id=usuario.id,
        session_id=sesion_id,
        activity_type=StudyActivityType.LESSON,
        status=AttemptStatus.IN_PROGRESS,
        lesson_id=contenido.lecciones[0].id,
        topic_id=contenido.tema.id,
        module_id=contenido.modulo.id,
        learning_path_id=contenido.ruta.id,
        knowledge_area_id=contenido.area.id,
        started_at=momento,
        local_date=momento.date(),
        idempotency_key=str(uuid.uuid4()),
    )
    db.add(fila)
    db.flush()
    return fila


@pytest.fixture
def responder(db):
    """Registra evidencias reales en `question_attempts` sobre la sesión de prueba."""

    def _responder(usuario, contenido, **kwargs):
        return registrar_respuesta(db, usuario, contenido, **kwargs)

    return _responder


@pytest.fixture
def evaluar(db):
    """Registra intentos de evaluación ya enviados."""

    def _evaluar(usuario, contenido, **kwargs):
        return registrar_evaluacion(db, usuario, contenido, **kwargs)

    return _evaluar


@pytest.fixture
def abrir_actividad(db):
    """Abre una `study_activities` de tipo lección."""

    def _abrir(usuario, contenido, **kwargs):
        return crear_actividad(db, usuario, contenido, **kwargs)

    return _abrir


__all__ = [
    "CONFIG_SEMILLA",
    "Contenido",
    "UTC",
    "ZONA",
    "crear_actividad",
    "_crear_evidencia",
    "registrar_evaluacion",
    "registrar_respuesta",
]
