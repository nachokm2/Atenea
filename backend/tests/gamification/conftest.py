"""Fixtures del módulo `gamification`.

Las pruebas que tocan la base usan la base real de desarrollo dentro de una
transacción que se **revierte** al final: no dejan rastro. Las semillas de
`game_configs` reproducen literalmente la tabla de CONTRACT.md §5 (es el trabajo
del agente de semillas; aquí se replica solo para poder probar el motor).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.enums import LevelScope
from app.models.gamification import GameConfig, LevelDefinition
from app.models.identity import User
from app.modules.gamification import servicio_config
from app.modules.gamification.servicio_config import ServicioConfig

URL_BASE_PRUEBAS = "postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea_test"

#: Versión de `game_configs` propia de esta suite. La tabla es única por
#: (key, version): con una versión distinta por módulo, dos suites pueden
#: sembrar la misma clave a la vez sin esperarse una a otra.
VERSION_SEMILLA = 4

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
    # §5.6 Racha y objetivo diario
    "streak.min_daily_educational_xp": (30, "int", True),
    "streak.sync_tolerance_min": (10, "int", False),
    "streak.grace_per_month": (1, "int", True),
    "streak.travel_skip_per_30d": (1, "int", False),
    "streak.tz_change_min_delta_h": (3, "int", False),
    "streak.tz_changes_max_per_24h": (1, "int", False),
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
    "goal.adapt.window_days": (14, "int", False),
    # §5.7 Avisos
    "notifications.reminder.default_hour": ("19:00", "string", True),
    "notifications.reminder.offset_min": (45, "int", False),
    "notifications.reminder.window": ({"start": "08:00", "end": "21:30"}, "map", False),
    "notifications.last_call.hour": ("21:30", "string", True),
    "notifications.last_call.min_streak": (7, "int", False),
    "notifications.quiet_hours": ({"start": "22:00", "end": "08:00"}, "map", True),
    "notifications.max_per_day.streak_goal": (2, "int", False),
    "notifications.max_per_day.total": (3, "int", False),
    "notifications.reactivation_days": ([3, 7, 30], "list", False),
    "goal.default": ({"type": "minutos", "target": 20}, "map", True),
    "goal.minutes.options": ([10, 20, 30, 45], "list", True),
    "goal.activities.options": ([1, 3, 5, 8], "list", True),
    "goal.xp.options": ([50, 100, 200, 350], "list", True),
    "goal.change_effective": ("next_day", "string", True),
    "goal.activity_units": (
        {"lesson": 1, "questions_block": 1, "questions_per_block": 5, "review": 1, "challenge": 1, "assessment": 2},
        "map",
        True,
    ),
    "goal.bonus_gold_base": (10, "int", True),
    "goal.bonus_gold_cap_days": (20, "int", True),
    "time.heartbeat_s": (30, "int", True),
    "time.max_tick_s": (60, "int", False),
    "time.idle_cutoff_s": (120, "int", False),
    "time.max_activity_multiplier": (3, "int", False),
    # §5.7 Misiones, logros y notificaciones
    "missions.daily.count": (3, "int", True),
    "missions.daily.tier_mix": (["easy", "medium", "variety"], "list", False),
    "missions.daily.no_repeat_days": (1, "int", False),
    "missions.claim.auto_on_expiry": (True, "bool", True),
    "missions.path.per_path": (3, "int", True),
    "missions.path.max_paths_shown": (5, "int", True),
    "missions.weekly.enabled": (False, "bool", True),
    "missions.reroll.per_day": (0, "int", True),
    "achievements.reward.bronze": ({"xp": 25, "gold": 20}, "map", True),
    "achievements.reward.silver": ({"xp": 75, "gold": 60}, "map", True),
    "achievements.reward.gold": ({"xp": 200, "gold": 150}, "map", True),
    "achievements.reward.single": ({"xp": 100, "gold": 75}, "map", True),
    "achievements.near_unlock_pct": (80, "int", True),
}


@pytest.fixture(scope="module")
def conexion() -> Iterator[sa.Connection]:
    """Conexión con una transacción externa que se revierte al terminar el módulo.

    El alcance es de **módulo**, no de sesión: una transacción abierta durante
    toda la ejecución mantendría bloqueadas las filas que esta suite siembra
    en `game_configs` y `level_definitions`, y cualquier otra suite que tocara
    esas mismas claves se quedaría esperando hasta el final.
    """
    motor_bd = sa.create_engine(URL_BASE_PRUEBAS, future=True)
    conn = motor_bd.connect()
    transaccion = conn.begin()
    try:
        yield conn
    finally:
        transaccion.rollback()
        conn.close()
        motor_bd.dispose()


@pytest.fixture(scope="module", autouse=True)
def semillas(conexion: sa.Connection) -> Iterator[None]:
    """Siembra `game_configs` y `level_definitions` dentro de la transacción de prueba."""
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

    # Curva global materializada, calculada con la fórmula de §6.1.
    from app.modules.gamification import niveles

    cfg = ServicioConfig(sesion)
    params = niveles.parametros_curva(cfg, LevelScope.GLOBAL)
    for nivel, requerido, delta in niveles.curva_completa(params):
        sesion.add(
            LevelDefinition(
                scope=LevelScope.GLOBAL,
                level=nivel,
                xp_required=requerido,
                xp_delta=delta,
                rank_title=niveles.titulo_de_rango(nivel, params),
                is_rank_start=niveles.es_inicio_de_rango(nivel, params),
                unlocks={},
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
    """Usuario de prueba con zona horaria de Santiago."""
    fila = User(
        email=f"prueba-{uuid.uuid4().hex[:12]}@atenea.test",
        password_hash="x" * 20,
        timezone="America/Santiago",
    )
    db.add(fila)
    db.flush()
    return fila


@pytest.fixture
def crear_regla(db: Session):
    """Fábrica de filas de `reward_rules` para las pruebas del motor."""
    from app.models.enums import EventType, GoldSource, XPSource
    from app.models.gamification import RewardRule

    def _crear(
        code: str,
        event_type: EventType,
        *,
        xp_config_key: str | None = None,
        xp_amount: int = 0,
        xp_source: XPSource | None = None,
        gold_config_key: str | None = None,
        gold_amount: int = 0,
        gold_source: GoldSource | None = None,
        condition: dict[str, Any] | None = None,
        is_educational: bool = True,
        first_time_only: bool = True,
        respects_daily_cap: bool = True,
        respects_repeat_multiplier: bool = True,
        priority: int = 100,
    ):
        regla = RewardRule(
            code=code,
            event_type=event_type,
            condition=condition or {},
            xp_amount=xp_amount,
            xp_config_key=xp_config_key,
            xp_source=xp_source,
            is_educational=is_educational,
            gold_amount=gold_amount,
            gold_config_key=gold_config_key,
            gold_source=gold_source,
            first_time_only=first_time_only,
            respects_daily_cap=respects_daily_cap,
            respects_repeat_multiplier=respects_repeat_multiplier,
            priority=priority,
            valid_from=utcnow(),
        )
        db.add(regla)
        db.flush()
        return regla

    return _crear


@pytest.fixture
def crear_plantilla_mision(db: Session):
    """Fábrica de filas de `mission_templates`."""
    from app.models.enums import MissionScope
    from app.models.gamification import MissionTemplate

    def _crear(
        code: str,
        *,
        scope: MissionScope = MissionScope.DAILY,
        title_template: str = "Completa {n} lecciones",
        metric: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        reward_profile: str = "daily_default",
        rewards: dict[str, Any] | None = None,
        weight: int = 1,
        is_active: bool = True,
        eligibility: list[Any] | None = None,
    ):
        plantilla = MissionTemplate(
            code=code,
            scope=scope,
            title_template=title_template,
            metric=metric or {"type": "counter", "event": "LESSON_COMPLETED"},
            params=params or {"n": {"easy": 1, "medium": 2, "hard": 3}},
            reward_profile=reward_profile,
            rewards=rewards or {},
            weight=weight,
            is_active=is_active,
            eligibility=eligibility or [],
        )
        db.add(plantilla)
        db.flush()
        return plantilla

    return _crear


@pytest.fixture
def crear_logro(db: Session):
    """Fábrica de filas de `achievements`."""
    from app.models.enums import AchievementCategory
    from app.models.gamification import Achievement

    def _crear(
        code: str,
        *,
        name: str = "Logro de prueba",
        category: AchievementCategory = AchievementCategory.LEARNING,
        rule: dict[str, Any] | None = None,
        tiers: list[dict[str, Any]] | None = None,
    ):
        logro = Achievement(
            code=code,
            name=name,
            category=category,
            rule=rule or {"type": "counter", "event": "LESSON_COMPLETED"},
            tiers=tiers or [{"tier": "single", "target": 1}],
        )
        db.add(logro)
        db.flush()
        return logro

    return _crear
