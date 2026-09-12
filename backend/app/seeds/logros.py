"""Semilla de `achievements`: los 32 logros del catálogo inicial.

Fuente normativa (contrato §9): `docs/auditoria/06b-rachas-objetivos-misiones-logros.md`
§5.2 (reglas declarativas) y §5.4 (catálogo inicial). Distribución exacta del documento:
6 de aprendizaje · 7 de dominio · 7 de constancia · 5 de colección · 3 de exploración ·
4 de hitos = **32**.

Forma de la regla (`achievements.rule`), que evalúa `app.modules.gamification.logros`::

    {type, event, where, success_when, reset_when, stat, field, on_events}

`type` reutiliza `MissionMetricType`, de modo que misiones y logros comparten un único
evaluador. Cada `where` solo referencia campos del payload documentado en §4.2 del
contrato, y los objetivos de los niveles son estrictamente crecientes: son las dos
validaciones que exige 06b §5.2 y que comprueban las pruebas de `tests/seeds`.

Recompensas: los niveles dejan `reward` vacío para que caiga el valor por defecto de
`achievements.reward.<tier>` de `game_configs` (§5.7). Solo se escribe `reward` cuando
el documento pide algo distinto: los dos logros de onboarding sin aprendizaje (0 XP y
oro simbólico, principio P1), el primer paso, y los niveles de oro que conceden título.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.enums import AchievementCategory, AchievementTier, AchievementVisibility, EventType
from app.modules.gamification.servicio_config import ServicioConfig
from app.seeds.areas import AREAS

__all__ = ["CODIGOS", "LogroSemilla", "NivelLogro", "catalogo"]

#: Territorios que existen en el mapa semilla; objetivo del nivel oro de Cartógrafo/a.
TERRITORIOS_TOTALES: int = len(AREAS)


@dataclass(frozen=True, slots=True)
class NivelLogro:
    """Un nivel (bronce, plata, oro o único) con su objetivo y su recompensa."""

    tier: AchievementTier
    target: int
    reward: dict[str, Any] = field(default_factory=dict)
    """Vacío = se aplica `achievements.reward.<tier>` de `game_configs`."""

    def as_dict(self) -> dict[str, Any]:
        """Forma serializable que se guarda en `achievements.tiers`."""
        fila: dict[str, Any] = {"tier": self.tier.value, "target": self.target}
        if self.reward:
            fila["reward"] = dict(self.reward)
        return fila


@dataclass(frozen=True, slots=True)
class LogroSemilla:
    """Un logro del catálogo inicial listo para insertarse en `achievements`."""

    code: str
    name: str
    description: str
    category: AchievementCategory
    rule: dict[str, Any]
    tiers: tuple[NivelLogro, ...]
    icon_key: str
    sort_order: int
    visibility: AchievementVisibility = AchievementVisibility.VISIBLE

    def tiers_json(self) -> list[dict[str, Any]]:
        """`achievements.tiers` con los objetivos en orden creciente."""
        return [nivel.as_dict() for nivel in self.tiers]


def _contador(evento: EventType, donde: dict[str, Any] | None = None) -> dict[str, Any]:
    """Regla `counter`: cuenta los eventos que cumplen `where`."""
    regla: dict[str, Any] = {"type": "counter", "event": evento.value}
    if donde:
        regla["where"] = donde
    return regla


def _bandera(evento: EventType, donde: dict[str, Any] | None = None) -> dict[str, Any]:
    """Regla `flag`: ocurre una sola vez, la primera."""
    regla: dict[str, Any] = {"type": "flag", "event": evento.value}
    if donde:
        regla["where"] = donde
    return regla


def _estadistico(stat: str, eventos: tuple[EventType, ...]) -> dict[str, Any]:
    """Regla `stat_threshold`: compara un estadístico del payload con el objetivo."""
    return {
        "type": "stat_threshold",
        "stat": stat,
        "op": ">=",
        "event": eventos[0].value,
        "on_events": [evento.value for evento in eventos],
    }


def _distintos(evento: EventType, campo: str, eventos: tuple[EventType, ...] = ()) -> dict[str, Any]:
    """Regla `distinct_count`: cardinalidad de un campo del payload."""
    regla: dict[str, Any] = {"type": "distinct_count", "event": evento.value, "field": campo}
    if eventos:
        regla["on_events"] = [e.value for e in eventos]
    return regla


def _tres(
    bronce: int, plata: int, oro: int, *, titulo_oro: dict[str, Any] | None = None
) -> tuple[NivelLogro, ...]:
    """Los tres niveles habituales, con objetivos estrictamente crecientes."""
    return (
        NivelLogro(AchievementTier.BRONZE, bronce),
        NivelLogro(AchievementTier.SILVER, plata),
        NivelLogro(AchievementTier.GOLD, oro, reward=dict(titulo_oro or {})),
    )


def _unico(objetivo: int = 1, recompensa: dict[str, Any] | None = None) -> tuple[NivelLogro, ...]:
    """Un logro de un solo nivel, para hechos únicos."""
    return (NivelLogro(AchievementTier.SINGLE, objetivo, reward=dict(recompensa or {})),)


def catalogo(cfg: ServicioConfig) -> tuple[LogroSemilla, ...]:
    """Los 32 logros del MVP.

    Recibe `ServicioConfig` porque dos objetivos y tres recompensas se derivan de
    `game_configs` en lugar de escribirse a mano: el número de ranuras equipables
    (`items.slots_active`) y las recompensas de nivel oro que además conceden título.
    """
    ranuras = len(cfg.obtener_lista("items.slots_active"))
    oro_base = dict(cfg.obtener_json("achievements.reward.gold"))

    def titulo(identificador: str) -> dict[str, Any]:
        """Recompensa de nivel oro con título cosmético (06b §5.3)."""
        return {**oro_base, "title_id": identificador}

    return (
        # -- Aprendizaje (6) -------------------------------------------------
        LogroSemilla(
            code="ACH_TIRELESS_READER",
            name="Lector/a Incansable",
            description="Completa lecciones, una detrás de otra, hasta que el Reino deje de contarlas.",
            category=AchievementCategory.LEARNING,
            rule=_contador(EventType.LESSON_COMPLETED),
            tiers=_tres(10, 50, 200),
            icon_key="ach_tireless_reader",
            sort_order=10,
        ),
        LogroSemilla(
            code="ACH_ORACLE",
            name="Oráculo",
            description="Acierta preguntas suficientes como para que te pregunten a ti.",
            category=AchievementCategory.LEARNING,
            rule=_contador(EventType.QUESTION_ANSWERED, {"is_correct": True}),
            tiers=_tres(100, 500, 2000, titulo_oro=titulo("TITLE_ORACLE")),
            icon_key="ach_oracle",
            sort_order=20,
        ),
        LogroSemilla(
            code="ACH_SHARPSHOOTER",
            name="Puntería",
            description="Encadena aciertos sin fallar ni una vez. El Reino admira la mano firme.",
            category=AchievementCategory.LEARNING,
            rule={
                "type": "consecutive",
                "event": EventType.QUESTION_ANSWERED.value,
                "success_when": {"is_correct": True},
                "reset_when": {"is_correct": False},
            },
            tiers=_tres(10, 25, 50),
            icon_key="ach_sharpshooter",
            sort_order=30,
        ),
        LogroSemilla(
            code="ACH_FLAWLESS_LESSON",
            name="Impecable",
            description="Termina una lección sin un solo error, con al menos tres preguntas de por medio.",
            category=AchievementCategory.LEARNING,
            rule=_contador(EventType.LESSON_COMPLETED, {"accuracy_pct": 100, "questions_total_gte": 3}),
            tiers=_tres(1, 10, 50),
            icon_key="ach_flawless_lesson",
            sort_order=40,
        ),
        LogroSemilla(
            code="ACH_CHALLENGER",
            name="Retador/a",
            description="Supera desafíos: la parte del camino que nadie recorre por accidente.",
            category=AchievementCategory.LEARNING,
            rule=_contador(EventType.CHALLENGE_COMPLETED),
            tiers=_tres(5, 25, 100),
            icon_key="ach_challenger",
            sort_order=50,
        ),
        LogroSemilla(
            code="ACH_REVENGE",
            name="Revancha",
            description="Acierta preguntas que antes te derribaron. Eso, y no el primer intento, es aprender.",
            category=AchievementCategory.LEARNING,
            rule=_contador(EventType.QUESTION_ANSWERED, {"is_correct": True, "is_retry_of_failed": True}),
            tiers=_tres(10, 50, 200),
            icon_key="ach_revenge",
            sort_order=60,
        ),
        # -- Dominio (7) -----------------------------------------------------
        LogroSemilla(
            code="ACH_PASSED",
            name="Aprobado/a",
            description="Aprueba pruebas del Castillo. La primera vale tanto como las cuarenta siguientes.",
            category=AchievementCategory.MASTERY,
            rule=_contador(EventType.ASSESSMENT_COMPLETED, {"passed": True}),
            tiers=_tres(1, 10, 50),
            icon_key="ach_passed",
            sort_order=70,
        ),
        LogroSemilla(
            code="ACH_OUTSTANDING",
            name="Sobresaliente",
            description="Consigue 90 % o más en una prueba del módulo.",
            category=AchievementCategory.MASTERY,
            rule=_contador(EventType.ASSESSMENT_COMPLETED, {"score_pct_gte": 90}),
            tiers=_tres(1, 10, 30),
            icon_key="ach_outstanding",
            sort_order=80,
        ),
        LogroSemilla(
            code="ACH_NO_FLAWS",
            name="Sin Fallas",
            description="Una prueba entera sin un solo error. El Reino no lo olvida.",
            category=AchievementCategory.MASTERY,
            rule=_contador(EventType.ASSESSMENT_COMPLETED, {"score_pct": 100}),
            tiers=_tres(1, 5, 20),
            icon_key="ach_no_flaws",
            sort_order=90,
        ),
        LogroSemilla(
            code="ACH_TOPIC_DOMINATOR",
            name="Dominador/a",
            description="Lleva temas al dominio pleno, no solo a la primera respuesta correcta.",
            category=AchievementCategory.MASTERY,
            rule=_estadistico("topics_mastered", (EventType.MASTERY_UPDATED,)),
            tiers=_tres(1, 5, 15),
            icon_key="ach_topic_dominator",
            sort_order=100,
        ),
        LogroSemilla(
            code="ACH_REALM_MASTER",
            name="Maestro/a del Reino",
            description="Domina territorios enteros. El quinto abre la Corona del Maestro.",
            category=AchievementCategory.MASTERY,
            rule=_estadistico("areas_mastered", (EventType.MASTERY_UPDATED,)),
            tiers=_tres(1, 3, 5),
            icon_key="ach_realm_master",
            sort_order=110,
        ),
        LogroSemilla(
            code="ACH_FULL_TRAIL",
            name="Sendero Completo",
            description="Completa rutas de principio a fin, sin dejar módulos a medias.",
            category=AchievementCategory.MASTERY,
            rule=_contador(EventType.PATH_COMPLETED),
            tiers=_tres(1, 3, 10),
            icon_key="ach_full_trail",
            sort_order=120,
        ),
        LogroSemilla(
            code="ACH_BUILDER",
            name="Constructor/a",
            description="Cierra módulos: cada uno es una zona del territorio que ya no vuelve a la niebla.",
            category=AchievementCategory.MASTERY,
            rule=_contador(EventType.MODULE_COMPLETED),
            tiers=_tres(5, 20, 60),
            icon_key="ach_builder",
            sort_order=130,
        ),
        # -- Constancia (7) --------------------------------------------------
        LogroSemilla(
            code="ACH_FLAME_KEEPER",
            name="Guardián/a de la Llama",
            description="Mantén la racha viva. La llama no pide mucho cada día, pero lo pide todos los días.",
            category=AchievementCategory.CONSISTENCY,
            rule=_estadistico("current_length", (EventType.STREAK_UPDATED,)),
            tiers=_tres(7, 30, 100, titulo_oro=titulo("TITLE_FLAME_KEEPER")),
            icon_key="ach_flame_keeper",
            sort_order=140,
        ),
        LogroSemilla(
            code="ACH_PERPETUAL_FLAME",
            name="Llama Perpetua",
            description="Un año entero sin apagarla. Hay quien lo cuenta y quien lo hace.",
            category=AchievementCategory.CONSISTENCY,
            rule=_estadistico("current_length", (EventType.STREAK_UPDATED,)),
            tiers=_unico(365),
            icon_key="ach_perpetual_flame",
            sort_order=150,
            visibility=AchievementVisibility.HIDDEN,
        ),
        LogroSemilla(
            code="ACH_PILGRIM",
            name="Peregrino/a",
            description="Suma días activos, seguidos o no. El Reino cuenta las jornadas, no las excusas.",
            category=AchievementCategory.CONSISTENCY,
            rule=_estadistico("user.total_active_days", (EventType.STREAK_UPDATED,)),
            tiers=_tres(30, 100, 365),
            icon_key="ach_pilgrim",
            sort_order=160,
        ),
        LogroSemilla(
            code="ACH_ACHIEVER",
            name="Cumplidor/a",
            description="Cumple tu objetivo diario una y otra vez, sea cual sea su tamaño.",
            category=AchievementCategory.CONSISTENCY,
            rule=_contador(EventType.DAILY_GOAL_MET),
            tiers=_tres(10, 50, 200),
            icon_key="ach_achiever",
            sort_order=170,
        ),
        LogroSemilla(
            code="ACH_PERFECT_WEEK",
            name="Semana Perfecta",
            description="Siete de siete objetivos cumplidos, de lunes a domingo.",
            category=AchievementCategory.CONSISTENCY,
            rule=_contador(EventType.WEEK_PERFECT),
            tiers=_tres(1, 5, 20),
            icon_key="ach_perfect_week",
            sort_order=180,
        ),
        LogroSemilla(
            code="ACH_ADVENTURER",
            name="Aventurero/a",
            description="Completa misiones del Game Master. Son la cara jugable de lo que ya deberías repasar.",
            category=AchievementCategory.CONSISTENCY,
            rule=_contador(EventType.MISSION_COMPLETED),
            tiers=_tres(10, 100, 500),
            icon_key="ach_adventurer",
            sort_order=190,
        ),
        LogroSemilla(
            code="ACH_EARLY_BIRD",
            name="Madrugador/a",
            description="Algo despierta a quienes estudian antes de que el Reino abra sus puertas…",
            category=AchievementCategory.CONSISTENCY,
            rule=_contador(EventType.DAILY_GOAL_MET, {"local_hour_lt": 9}),
            tiers=_unico(10),
            icon_key="ach_early_bird",
            sort_order=200,
            visibility=AchievementVisibility.HIDDEN,
        ),
        # -- Colección (5) ---------------------------------------------------
        LogroSemilla(
            code="ACH_FIRST_GEAR",
            name="Primer Ajuar",
            description="Equipa tu primera pieza. El avatar deja de ser un boceto y empieza a contar tu historia.",
            category=AchievementCategory.COLLECTION,
            rule=_bandera(EventType.ITEM_EQUIPPED),
            tiers=_unico(1),
            icon_key="ach_first_gear",
            sort_order=210,
        ),
        LogroSemilla(
            code="ACH_COLLECTOR",
            name="Coleccionista",
            description="Reúne piezas en la mochila. Ninguna se compra con atajos: todas se ganan estudiando.",
            category=AchievementCategory.COLLECTION,
            rule=_estadistico("items_count", (EventType.ITEM_ACQUIRED,)),
            tiers=_tres(5, 20, 50),
            icon_key="ach_collector",
            sort_order=220,
        ),
        LogroSemilla(
            code="ACH_FULL_ARMOR",
            name="Armadura Completa",
            description="Todas las ranuras ocupadas a la vez. Nada de improvisar con el torso al aire.",
            category=AchievementCategory.COLLECTION,
            rule=_estadistico("slots_filled", (EventType.ITEM_EQUIPPED,)),
            tiers=_unico(ranuras),
            icon_key="ach_full_armor",
            sort_order=230,
        ),
        LogroSemilla(
            code="ACH_FORGED_IN_KNOWLEDGE",
            name="Forjado/a con Saber",
            description="Consigue piezas que solo se desbloquean demostrando lo que sabes.",
            category=AchievementCategory.COLLECTION,
            rule=_contador(EventType.ITEM_ACQUIRED, {"knowledge_linked": True}),
            tiers=_tres(1, 5, 10),
            icon_key="ach_forged_in_knowledge",
            sort_order=240,
        ),
        LogroSemilla(
            code="ACH_RARE_TREASURE",
            name="Tesoro Raro",
            description="Algo brilla en el fondo de la mochila y no es de los que se compran barato…",
            category=AchievementCategory.COLLECTION,
            rule=_bandera(EventType.ITEM_ACQUIRED, {"rarity_in": ["epic", "legendary", "mythic"]}),
            tiers=_unico(1),
            icon_key="ach_rare_treasure",
            sort_order=250,
            visibility=AchievementVisibility.HIDDEN,
        ),
        # -- Exploración (3) -------------------------------------------------
        LogroSemilla(
            code="ACH_CARTOGRAPHER",
            name="Cartógrafo/a",
            description="Descubre territorios del mapa. El último borra la niebla del Reino entero.",
            category=AchievementCategory.EXPLORATION,
            rule=_estadistico("territories_unlocked", (EventType.TERRITORY_UNLOCKED,)),
            tiers=_tres(2, 5, TERRITORIOS_TOTALES),
            icon_key="ach_cartographer",
            sort_order=260,
        ),
        LogroSemilla(
            code="ACH_POLYMATH",
            name="Polímata",
            description="Ten rutas vivas en tres conocimientos distintos al mismo tiempo.",
            category=AchievementCategory.EXPLORATION,
            rule=_distintos(
                EventType.PATH_CREATED,
                "knowledge_area_id",
                (EventType.PATH_CREATED, EventType.LESSON_COMPLETED),
            ),
            tiers=_unico(3),
            icon_key="ach_polymath",
            sort_order=270,
        ),
        LogroSemilla(
            code="ACH_CURIOUS",
            name="Curioso/a",
            description="Completa lecciones en conocimientos distintos. La amplitud también es mérito.",
            category=AchievementCategory.EXPLORATION,
            rule=_distintos(EventType.LESSON_COMPLETED, "knowledge_area_id"),
            tiers=_tres(2, 4, 6),
            icon_key="ach_curious",
            sort_order=280,
        ),
        # -- Hitos (4) -------------------------------------------------------
        LogroSemilla(
            code="ACH_WELCOME",
            name="Bienvenido/a al Reino",
            description="Tu personaje existe. El resto lo escribes tú.",
            category=AchievementCategory.MILESTONE,
            rule=_bandera(EventType.CHARACTER_CREATED),
            tiers=_unico(1, {"xp": 0, "gold": 20}),
            icon_key="ach_welcome",
            sort_order=1,
        ),
        LogroSemilla(
            code="ACH_FIRST_QUEST",
            name="Primera Aventura",
            description="Has trazado tu primera ruta. El mapa ya tiene un camino dibujado.",
            category=AchievementCategory.MILESTONE,
            rule=_bandera(EventType.PATH_CREATED),
            tiers=_unico(1, {"xp": 0, "gold": 20}),
            icon_key="ach_first_quest",
            sort_order=2,
        ),
        LogroSemilla(
            code="ACH_FIRST_STEP",
            name="Primer Paso",
            description="Tu primera lección completada. Aquí empieza de verdad la progresión del personaje.",
            category=AchievementCategory.MILESTONE,
            rule=_bandera(EventType.LESSON_COMPLETED),
            tiers=_unico(1, {"xp": 50, "gold": 30}),
            icon_key="ach_first_step",
            sort_order=3,
        ),
        LogroSemilla(
            code="ACH_VETERAN",
            name="Veterano/a",
            description="Sube de nivel hasta que el Reino te salude por el título y no por el nombre.",
            category=AchievementCategory.MILESTONE,
            rule=_estadistico("level_after", (EventType.LEVEL_UP,)),
            tiers=_tres(5, 15, 30),
            icon_key="ach_veteran",
            sort_order=290,
        ),
    )


#: Los 32 códigos del catálogo, en el orden en que se siembran.
CODIGOS: tuple[str, ...] = (
    "ACH_TIRELESS_READER",
    "ACH_ORACLE",
    "ACH_SHARPSHOOTER",
    "ACH_FLAWLESS_LESSON",
    "ACH_CHALLENGER",
    "ACH_REVENGE",
    "ACH_PASSED",
    "ACH_OUTSTANDING",
    "ACH_NO_FLAWS",
    "ACH_TOPIC_DOMINATOR",
    "ACH_REALM_MASTER",
    "ACH_FULL_TRAIL",
    "ACH_BUILDER",
    "ACH_FLAME_KEEPER",
    "ACH_PERPETUAL_FLAME",
    "ACH_PILGRIM",
    "ACH_ACHIEVER",
    "ACH_PERFECT_WEEK",
    "ACH_ADVENTURER",
    "ACH_EARLY_BIRD",
    "ACH_FIRST_GEAR",
    "ACH_COLLECTOR",
    "ACH_FULL_ARMOR",
    "ACH_FORGED_IN_KNOWLEDGE",
    "ACH_RARE_TREASURE",
    "ACH_CARTOGRAPHER",
    "ACH_POLYMATH",
    "ACH_CURIOUS",
    "ACH_WELCOME",
    "ACH_FIRST_QUEST",
    "ACH_FIRST_STEP",
    "ACH_VETERAN",
)
