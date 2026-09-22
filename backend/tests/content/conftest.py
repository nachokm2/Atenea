"""Fixtures de las pruebas del módulo `content`.

Dos clases de prueba:

* **Lógica pura** — la corrección determinista y el muestreo no tocan la base. Usan
  `cfg_falso`, que devuelve los valores literales de CONTRACT.md §5. Esos números
  viven aquí, en la prueba, como oráculo: nunca en el código de la app (§8.10 regla 5).
* **Con base de datos** — usan la base real de desarrollo dentro de una transacción
  que **siempre** se revierte, así que no dejan rastro.

Las semillas de `game_configs` y `reward_rules` reproducen la tabla del contrato: son trabajo del agente de semillas, y aquí se replican para poder
ejercitar el motor de gamificación de punta a punta.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import register_exception_handlers
from app.core.time import utcnow
from app.models.content import (
    Assessment,
    AssessmentQuestion,
    KnowledgeArea,
    LearningPath,
    Lesson,
    LessonBlock,
    PathModule,
    Question,
    Territory,
    Topic,
)
from app.models.enums import (
    ContentStatus,
    DifficultyLevel,
    EventType,
    GoldSource,
    KnowledgeCategory,
    LessonBlockType,
    PathOrigin,
    PathStatus,
    QuestionType,
    XPSource,
)
from app.models.gamification import GameConfig, RewardRule
from app.models.identity import User
from app.modules.gamification import servicio_config
from app.modules.gamification.servicio_config import ServicioConfig

#: La base de pruebas la fija `tests/conftest.py`, que corre siempre antes que
#: este archivo y deja la URL definitiva en `DATABASE_URL`. Escribirla a mano
#: aquí era lo que mantenía en rojo la integración continua: el valor de reserva
#: apunta al puerto del Docker de desarrollo, que en el runner no existe.
URL_BASE_PRUEBAS = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea_test"
)
ZONA = "America/Santiago"

#: Versión de las filas de `game_configs` que siembra este paquete de pruebas.
#: `uq_game_configs_key_version` es única: usar una versión propia evita que dos
#: suites que corren en la misma base (y en transacciones abiertas a la vez) se
#: bloqueen entre sí por el mismo índice. `ServicioConfig` toma la mayor versión
#: vigente, así que estas filas son las que mandan dentro de la transacción de prueba.
VERSION_SEMILLA = 2

#: Semilla de `game_configs` con los valores canónicos de CONTRACT.md §5.
SEMILLAS_CONFIG: dict[str, tuple[Any, str, bool]] = {
    # §5.1 XP
    "xp.lesson_completed": (50, "int", True),
    "xp.question_first_try": (10, "int", True),
    "xp.question_second_try": (4, "int", True),
    "xp.question_cap_per_lesson": (60, "int", False),
    "xp.challenge_completed": (200, "int", True),
    "xp.assessment_passed": (300, "int", True),
    "xp.assessment_bonus_90": (100, "int", True),
    "xp.assessment_bonus_100": (200, "int", True),
    "xp.module_completed": (200, "int", True),
    "xp.path_completed": (1000, "int", True),
    "xp.review_completed": (30, "int", True),
    "xp.review_per_correct": (5, "int", False),
    "xp.review_correct_cap": (30, "int", False),
    "xp.review_max_paid_per_day": (3, "int", False),
    "xp.first_activity_of_day": (20, "int", True),
    "xp.daily_goal": (0, "int", True),
    "xp.mission_daily_easy": (40, "int", True),
    "xp.mission_daily_medium": (100, "int", True),
    "xp.mission_daily_hard": (180, "int", True),
    "xp.mission_weekly_medium": (300, "int", True),
    "xp.mission_weekly_hard": (600, "int", True),
    "xp.repeat_multipliers": ([1.0, 0.2, 0.0], "list", False),
    "xp.low_content_multiplier": (0.5, "decimal", False),
    "xp.streak_multiplier": ({"enabled": False}, "map", False),
    "xp.daily_softcap": ([{"limit": 1500, "mult": 0.5}, {"limit": 3000, "mult": 0.1}], "list", False),
    "xp.min_time.lesson": ({"abs_seconds": 60, "ratio": 0.25}, "map", False),
    "xp.min_time.challenge": ({"abs_seconds": 90, "ratio": 0.25}, "map", False),
    "xp.min_time.assessment_per_question": (20, "int", False),
    "xp.min_time.answer_ms": (2000, "int", False),
    "xp.attempt_ttl_hours": (2, "int", False),
    # §5.2 Niveles
    "level.base": (80, "int", True),
    "level.exponent": (2.2, "decimal", True),
    "level.max": (50, "int", True),
    "level.round_to": (10, "int", True),
    "level.rank_titles": (
        {
            "1": "Aprendiz",
            "5": "Iniciado/a",
            "10": "Escriba",
            "15": "Erudito/a",
            "20": "Adepto/a",
            "25": "Guardián/a del Saber",
            "30": "Sabio/a",
            "35": "Maestro/a",
            "40": "Gran Maestro/a",
            "45": "Archimaestro/a",
            "50": "Leyenda del Reino",
        },
        "map",
        True,
    ),
    "knowledge.level.base": (50, "int", True),
    "knowledge.level.exponent": (2.2, "decimal", True),
    "knowledge.rank_titles": (
        {
            "1": "Novato/a en",
            "5": "Practicante de",
            "10": "Competente en",
            "15": "Avanzado/a en",
            "20": "Experto/a en",
            "30": "Maestro/a de",
        },
        "map",
        True,
    ),
    "knowledge.master_title_requires_mastery": (80, "int", True),
    "knowledge.master_title_fallback": ("Veterano/a de", "string", True),
    # §5.3 Oro
    "gold.welcome": (100, "int", True),
    "gold.lesson_completed": (20, "int", True),
    "gold.challenge_completed": (60, "int", True),
    "gold.assessment_passed": (100, "int", True),
    "gold.assessment_bonus_90": (50, "int", True),
    "gold.assessment_bonus_100": (100, "int", True),
    "gold.module_completed": (80, "int", True),
    "gold.path_completed": (500, "int", True),
    "gold.review_completed": (10, "int", True),
    "gold.mission_daily_easy": (10, "int", True),
    "gold.mission_daily_medium": (25, "int", True),
    "gold.mission_daily_hard": (50, "int", True),
    "gold.mission_weekly_medium": (100, "int", True),
    "gold.mission_weekly_hard": (200, "int", True),
    "gold.level_up_bonus": (50, "int", True),
    "gold.rank_up_bonus": (100, "int", True),
    "gold.achievement_tiers": ({"bronze": 20, "silver": 60, "gold": 150, "single": 75}, "map", True),
    "gold.daily_softcap": ([{"limit": 500, "mult": 0.5}, {"limit": 1000, "mult": 0.1}], "list", False),
    # §5.5 Dominio
    "mastery.weight.difficulty": ({"easy": 1.0, "medium": 1.5, "hard": 2.0}, "map", False),
    "mastery.weight.context": (
        {"lesson": 1.0, "practice": 1.0, "review": 1.0, "challenge": 1.5, "assessment": 2.0},
        "map",
        False,
    ),
    "mastery.weight.retake": ([1.0, 0.6, 0.3], "list", False),
    "mastery.correctness_second_try": (0.5, "decimal", False),
    "mastery.recency_half_life_days": (30, "int", False),
    "mastery.prior_m": (3, "decimal", False),
    "mastery.prior_p0": (0.5, "decimal", False),
    "mastery.evidence_window": ({"max_items": 40, "max_days": 180}, "map", False),
    "mastery.coverage_floor": (0.6, "decimal", False),
    "mastery.decay": (
        {
            "grace_days": 7,
            "floor": 0.6,
            "half_life_days": 60,
            "stability_factor": 1.5,
            "half_life_max_days": 365,
        },
        "map",
        False,
    ),
    "mastery.module.weight_topics": (0.70, "decimal", False),
    "mastery.module.weight_assessment": (0.30, "decimal", False),
    "mastery.assessment.pass_score": (70, "int", True),
    "mastery.assessment.distinction_score": (90, "int", True),
    "mastery.assessment.retake_penalty": ({"per_attempt": 0.05, "max": 0.15}, "map", False),
    "mastery.assessment.cooldown_hours": ([4, 24, 48], "list", True),
    "mastery.assessment.max_attempts_per_day": (2, "int", True),
    "mastery.assessment.bank_ratio": (2.5, "decimal", False),
    "mastery.assessment.max_overlap": (0.30, "decimal", False),
    "mastery.assessment.question_count": (10, "int", True),
    "mastery.threshold.mastered": (80, "int", True),
    "mastery.threshold.at_risk": (70, "int", True),
    "mastery.threshold.weak_practice": (50, "int", False),
    "mastery.weak_min_evidence": (5, "int", False),
    "mastery.review.stability_min_score": (70, "int", False),
    "mastery.review.questions": ({"min": 4, "max": 8}, "map", True),
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
    "mastery.area_mastered_requires_completed_path": (True, "bool", True),
    # §5.6 Racha, objetivo diario y tiempo
    "streak.min_daily_educational_xp": (30, "int", True),
    "streak.sync_tolerance_min": (10, "int", False),
    "streak.grace_per_month": (1, "int", True),
    "streak.travel_skip_per_30d": (1, "int", False),
    "streak.milestones": ([7, 14, 30, 60, 100, 365], "list", True),
    "streak.repeat_milestone_every": (50, "int", True),
    "streak.milestone_rewards": (
        {
            "7": {"xp": 50, "gold": 50, "item_code": "antorcha_constancia"},
            "14": {"xp": 100, "gold": 100, "item_code": "botas_caminante"},
            "30": {"xp": 200, "gold": 200, "item_code": "capa_llamas_persistentes"},
            "60": {"xp": 300, "gold": 300, "item_code": None},
            "100": {"xp": 500, "gold": 500, "item_code": "corona_fuego_eterno"},
            "365": {"xp": 1000, "gold": 1000, "item_code": None},
            "repeat": {"xp": 250, "gold": 250, "item_code": None},
        },
        "map",
        True,
    ),
    "goal.default": ({"type": "minutos", "target": 20}, "map", True),
    "goal.minutes.options": ([10, 20, 30, 45], "list", True),
    "goal.activities.options": ([1, 3, 5, 8], "list", True),
    "goal.xp.options": ([50, 100, 200, 350], "list", True),
    "goal.change_effective": ("next_day", "string", True),
    "goal.activity_units": (
        {
            "lesson": 1,
            "questions_block": 1,
            "questions_per_block": 5,
            "review": 1,
            "challenge": 1,
            "assessment": 2,
        },
        "map",
        True,
    ),
    "goal.bonus_gold_base": (10, "int", True),
    "goal.bonus_gold_cap_days": (20, "int", True),
    "time.heartbeat_s": (30, "int", True),
    "time.max_tick_s": (60, "int", False),
    "time.idle_cutoff_s": (120, "int", False),
    "time.max_activity_multiplier": (3, "int", False),
    "time.session_idle_timeout_min": (10, "int", False),
    # §5.7 Misiones y logros
    "missions.daily.count": (3, "int", True),
    "missions.daily.tier_mix": (["easy", "medium", "variety"], "list", False),
    "missions.daily.no_repeat_days": (1, "int", False),
    "missions.claim.auto_on_expiry": (True, "bool", True),
    "missions.path.per_path": (3, "int", True),
    "achievements.reward.bronze": ({"xp": 25, "gold": 20}, "map", True),
    "achievements.reward.silver": ({"xp": 75, "gold": 60}, "map", True),
    "achievements.reward.gold": ({"xp": 200, "gold": 150}, "map", True),
    "achievements.reward.single": ({"xp": 100, "gold": 75}, "map", True),
    # §5.8 Contenido e IA
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
    "content.challenges_per_module_max": (1, "int", False),
    "content.challenge_questions": (5, "int", False),
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
}


# ---------------------------------------------------------------------------
# Configuración de prueba sin base de datos
# ---------------------------------------------------------------------------


class ConfigFalsa:
    """`ServicioConfig` mínimo para las pruebas puras: lee de `SEMILLAS_CONFIG`."""

    def _valor(self, clave: str) -> Any:
        return SEMILLAS_CONFIG[clave][0]

    def obtener(self, clave: str, por_defecto: Any = None) -> Any:
        return self._valor(clave)

    def obtener_int(self, clave: str, por_defecto: Any = None) -> int:
        return int(self._valor(clave))

    def obtener_decimal(self, clave: str, por_defecto: Any = None) -> float:
        return float(self._valor(clave))

    def obtener_bool(self, clave: str, por_defecto: Any = None) -> bool:
        return bool(self._valor(clave))

    def obtener_str(self, clave: str, por_defecto: Any = None) -> str:
        return str(self._valor(clave))

    def obtener_lista(self, clave: str, por_defecto: Any = None) -> list:
        return list(self._valor(clave))

    def obtener_json(self, clave: str, por_defecto: Any = None) -> dict:
        return dict(self._valor(clave))


@pytest.fixture(scope="session")
def cfg_falso() -> ConfigFalsa:
    """Configuración de juego con los valores del contrato, sin tocar la base."""
    return ConfigFalsa()


# ---------------------------------------------------------------------------
# Fixtures con base de datos
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def conexion() -> Iterator[sa.Connection]:
    """Conexión única con una transacción externa que se revierte al terminar."""
    motor = sa.create_engine(URL_BASE_PRUEBAS, future=True)
    try:
        conn = motor.connect()
    except Exception as exc:  # pragma: no cover - depende del entorno local
        motor.dispose()
        pytest.skip(f"La base de datos de desarrollo no está disponible: {exc}")
    transaccion = conn.begin()
    try:
        yield conn
    finally:
        transaccion.rollback()
        conn.close()
        motor.dispose()


@pytest.fixture(scope="session", autouse=True)
def semillas(conexion: sa.Connection) -> Iterator[None]:
    """Siembra `game_configs` y `reward_rules` de §5 y §3.5.

    `level_definitions` **no** se siembra: `niveles.tabla_niveles` cae a la curva
    calculada de §6.1 cuando la tabla está vacía, y su clave única `(scope, level)`
    chocaría con la semilla de otra suite que corriera a la vez.
    """
    servicio_config.invalidar_cache()
    sesion = Session(bind=conexion, join_transaction_mode="create_savepoint")
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
    sesion.flush()

    # Reglas de recompensa del MVP que necesita el ciclo de aprendizaje (§3.5).
    reglas = [
        ("C_LESSON", EventType.LESSON_COMPLETED, "xp.lesson_completed", XPSource.LESSON,
         "gold.lesson_completed", GoldSource.LESSON, {}),
        ("C_CHALLENGE", EventType.CHALLENGE_COMPLETED, "xp.challenge_completed", XPSource.CHALLENGE,
         "gold.challenge_completed", GoldSource.CHALLENGE, {}),
        ("C_MODULE", EventType.MODULE_COMPLETED, "xp.module_completed", XPSource.MODULE,
         "gold.module_completed", GoldSource.MODULE, {}),
        ("C_PATH", EventType.PATH_COMPLETED, "xp.path_completed", XPSource.PATH,
         "gold.path_completed", GoldSource.PATH, {}),
        ("C_ASSESS", EventType.ASSESSMENT_COMPLETED, "xp.assessment_passed", XPSource.ASSESSMENT,
         "gold.assessment_passed", GoldSource.ASSESSMENT, {"passed": True}),
    ]
    for code, evento, xp_key, xp_src, gold_key, gold_src, condicion in reglas:
        sesion.add(
            RewardRule(
                code=code,
                event_type=evento,
                condition=condicion,
                xp_amount=0,
                xp_config_key=xp_key,
                xp_source=xp_src,
                is_educational=True,
                gold_amount=0,
                gold_config_key=gold_key,
                gold_source=gold_src,
                first_time_only=True,
                respects_daily_cap=True,
                respects_repeat_multiplier=True,
                priority=100,
                valid_from=ahora,
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
def usuario(db: Session) -> User:
    """Usuario de prueba con zona horaria de Chile."""
    fila = User(
        email=f"contenido-{uuid.uuid4().hex[:12]}@atenea.test",
        password_hash="x" * 20,
        timezone=ZONA,
    )
    db.add(fila)
    db.flush()
    return fila


class Contenido:
    """Grafo de contenido: conocimiento → ruta → 2 módulos → tema → lecciones."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


def _pregunta(topic_id: uuid.UUID, lesson_id: uuid.UUID | None, tipo: QuestionType, **kwargs: Any):
    """Fábrica corta de preguntas con clave de corrección."""
    base = {
        QuestionType.MULTIPLE_CHOICE: (
            {"options": [{"id": "a", "text": "Sí"}, {"id": "b", "text": "No"}]},
            {"correct_option_id": "a"},
        ),
        QuestionType.TRUE_FALSE: ({}, {"answer": True}),
        QuestionType.FILL_BLANK: (
            {"template": "Un ___ une dos tablas."},
            {"blanks": [{"accepted": ["INNER JOIN", "join interno"]}]},
        ),
        QuestionType.MATCHING: (
            {"left": ["1", "2"], "right": ["a", "b"]},
            {"pairs": {"1": "a", "2": "b"}},
        ),
        QuestionType.ORDERING: ({"items": ["x", "y", "z"]}, {"order": ["x", "y", "z"]}),
    }
    cuerpo, clave = base[tipo]
    return Question(
        topic_id=topic_id,
        lesson_id=lesson_id,
        question_type=tipo,
        difficulty=kwargs.pop("difficulty", DifficultyLevel.MEDIUM),
        stem=kwargs.pop("stem", "¿Qué hace un INNER JOIN?"),
        body=kwargs.pop("body", cuerpo),
        answer_key=kwargs.pop("answer_key", clave),
        explanation=kwargs.pop("explanation", "Combina filas que casan en ambas tablas."),
        content_status=ContentStatus.READY,
        **kwargs,
    )


@pytest.fixture
def contenido(db: Session) -> Contenido:
    """Ruta con dos módulos; el primero con un tema, dos lecciones y su evaluación."""
    sufijo = uuid.uuid4().hex[:8]
    area = KnowledgeArea(
        slug=f"sql-{sufijo}",
        name="SQL",
        short_name="SQL",
        category=KnowledgeCategory.DATA,
        is_canonical=True,
    )
    db.add(area)
    db.flush()
    territorio = Territory(knowledge_area_id=area.id, name="Castillo de las Consultas")
    db.add(territorio)

    ruta = LearningPath(
        user_id=None,
        knowledge_area_id=area.id,
        title="Maestro de SQL",
        origin=PathOrigin.SEED,
        status=PathStatus.ACTIVE,
        is_public=True,
    )
    db.add(ruta)
    db.flush()

    modulo1 = PathModule(learning_path_id=ruta.id, position=1, title="Consultas relacionales")
    modulo2 = PathModule(learning_path_id=ruta.id, position=2, title="Agregaciones")
    db.add_all([modulo1, modulo2])
    db.flush()

    tema = Topic(module_id=modulo1.id, position=1, title="JOINs", lesson_count=2)
    db.add(tema)
    db.flush()

    leccion1 = Lesson(
        topic_id=tema.id,
        position=1,
        title="INNER JOIN",
        estimated_seconds=540,
        content_status=ContentStatus.READY,
    )
    leccion2 = Lesson(
        topic_id=tema.id,
        position=2,
        title="LEFT JOIN",
        estimated_seconds=540,
        content_status=ContentStatus.READY,
    )
    db.add_all([leccion1, leccion2])
    db.flush()

    db.add(
        LessonBlock(
            lesson_id=leccion1.id,
            position=1,
            block_type=LessonBlockType.EXPLANATION,
            body="Un INNER JOIN devuelve las filas que casan en ambas tablas.",
        )
    )

    preguntas_l1 = [
        _pregunta(tema.id, leccion1.id, QuestionType.MULTIPLE_CHOICE),
        _pregunta(tema.id, leccion1.id, QuestionType.TRUE_FALSE),
    ]
    preguntas_l2 = [_pregunta(tema.id, leccion2.id, QuestionType.FILL_BLANK)]
    db.add_all([*preguntas_l1, *preguntas_l2])

    banco = [
        _pregunta(tema.id, None, QuestionType.MULTIPLE_CHOICE, stem=f"Banco {i}")
        for i in range(10)
    ]
    db.add_all(banco)
    db.flush()

    evaluacion = Assessment(
        module_id=modulo1.id,
        title="Prueba del módulo",
        question_count=4,
        bank_size=10,
        content_status=ContentStatus.READY,
    )
    db.add(evaluacion)
    db.flush()
    for indice, pregunta in enumerate(banco, start=1):
        db.add(
            AssessmentQuestion(
                assessment_id=evaluacion.id, question_id=pregunta.id, position=indice
            )
        )
    db.flush()

    return Contenido(
        area=area,
        territorio=territorio,
        ruta=ruta,
        modulo1=modulo1,
        modulo2=modulo2,
        tema=tema,
        leccion1=leccion1,
        leccion2=leccion2,
        preguntas_l1=preguntas_l1,
        preguntas_l2=preguntas_l2,
        evaluacion=evaluacion,
        banco=banco,
    )


@pytest.fixture
def cliente(db: Session, usuario: User) -> Iterator[TestClient]:
    """Cliente HTTP con la sesión de prueba y el usuario ya autenticado.

    Se monta una app mínima con el router de `content`: así se prueba el contrato de
    la API sin depender de `app/main.py` ni del router raíz, que son de otros agentes.
    """
    from app.modules.content.router import router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: usuario
    with TestClient(app) as http:
        yield http


__all__ = ["SEMILLAS_CONFIG", "VERSION_SEMILLA", "ZONA", "ConfigFalsa", "Contenido"]
