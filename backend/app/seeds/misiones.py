"""Semilla de `mission_templates`: las 23 plantillas de misión del catálogo inicial.

Fuente normativa (contrato §9): `docs/auditoria/06b-rachas-objetivos-misiones-logros.md`
§4.2 (plantillas parametrizadas) y §4.6 (catálogo inicial). Reparto exacto:
**13 diarias (D01–D13) · 4 de ruta o especiales (S01–S04) · 6 semanales (W01–W06)**.

Estado en el MVP:

- Las 13 diarias nacen activas: son el bucle diario del producto.
- S01, S02 y S03 nacen activas; `missions.path.per_path` instancia justamente tres por
  ruta. **S04 nace desactivada** porque 06b §4.6 la marca como fase 2 (depende del
  documento de dominio).
- Las 6 semanales nacen **desactivadas** (`missions.weekly.enabled = false`, §5.7): el
  catálogo nace completo para que activar el horizonte semanal sea configuración y UI,
  no una migración.

Forma de la métrica (`mission_templates.metric`), que evalúa
`app.modules.gamification.misiones`::

    {type, event, where, field}

`type` es un valor de `MissionMetricType`, el mismo evaluador que usan los logros. El
objetivo de la instancia sale del parámetro `n` resuelto para su dificultad, y el
título se interpola con esos mismos parámetros: por eso **ningún `title_template` usa
un marcador que no exista en `params`**.

Recompensas: `daily_default` y `weekly_default` leen `xp.mission_*` y `gold.mission_*`
de `game_configs`; solo las especiales llevan `rewards` explícito, porque 06b §4.6 les
asigna importes propios.

TODO (fase 2): W06 mide el incremento de dominio de un tema y necesita que
`MASTERY_UPDATED` transporte `topic_delta` en su payload. El contrato §4.2 documenta
`topic_before` y `topic_after`, pero no el delta; la plantilla nace desactivada y no se
puede activar hasta que el módulo `progress` publique ese campo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.enums import EventType, GoalType, MissionScope

__all__ = ["PLANTILLAS", "PlantillaMision", "por_codigo"]


@dataclass(frozen=True, slots=True)
class PlantillaMision:
    """Una fila de `mission_templates` lista para insertarse."""

    code: str
    """D01…D13 (diarias), S01…S04 (especiales), W01…W06 (semanales)."""

    scope: MissionScope
    title_template: str
    """Plantilla interpolable con los parámetros resueltos ("Completa {n} lecciones")."""

    narrative_key: str
    metric: dict[str, Any]
    """`{type, event, where, field}`; `type` es un valor de `MissionMetricType`."""

    params: dict[str, Any] = field(default_factory=dict)
    """`{"n": {"easy": 1, "medium": 2, "hard": 3}}`; `n` fija el objetivo."""

    target_scope: str = "any"
    """`any`, `knowledge_area` o `path`."""

    eligibility: tuple[Any, ...] = ()
    """Predicados de contexto: cadena simple o `{"predicate": …, "value": …}`."""

    exclude_if_goal_type: tuple[str, ...] = ()
    """Evita duplicar el objetivo diario vigente."""

    reward_profile: str = "daily_default"
    rewards: dict[str, Any] = field(default_factory=dict)
    """Recompensa explícita; si está vacía manda el perfil."""

    weight: int = 1
    is_active: bool = True


def _metrica(
    tipo: str,
    evento: EventType,
    *,
    donde: dict[str, Any] | None = None,
    campo: str | None = None,
) -> dict[str, Any]:
    """Construye la métrica declarativa de una plantilla."""
    metrica: dict[str, Any] = {"type": tipo, "event": evento.value}
    if donde:
        metrica["where"] = donde
    if campo:
        metrica["field"] = campo
    return metrica


# ---------------------------------------------------------------------------
# Diarias (06b §4.6) — activas en el MVP
# ---------------------------------------------------------------------------

_DIARIAS: tuple[PlantillaMision, ...] = (
    PlantillaMision(
        code="D01",
        scope=MissionScope.DAILY,
        title_template="Completa {n} lecciones",
        narrative_key="mission.d01.narrative",
        metric=_metrica("counter", EventType.LESSON_COMPLETED),
        params={"n": {"easy": 1, "medium": 2, "hard": 3}},
        weight=4,
    ),
    PlantillaMision(
        code="D02",
        scope=MissionScope.DAILY,
        title_template="Responde {n} preguntas correctamente",
        narrative_key="mission.d02.narrative",
        metric=_metrica("counter", EventType.QUESTION_ANSWERED, donde={"is_correct": True}),
        params={"n": {"easy": 5, "medium": 10, "hard": 20}},
        weight=4,
    ),
    PlantillaMision(
        code="D03",
        scope=MissionScope.DAILY,
        title_template="Termina una lección con {n} % de precisión o más",
        narrative_key="mission.d03.narrative",
        metric=_metrica("max", EventType.LESSON_COMPLETED, campo="accuracy_pct"),
        params={"n": {"medium": 80, "hard": 100}},
        weight=3,
    ),
    PlantillaMision(
        code="D04",
        scope=MissionScope.DAILY,
        title_template="Repasa un tema que se te resiste",
        narrative_key="mission.d04.narrative",
        metric=_metrica("counter", EventType.REVIEW_COMPLETED, donde={"topic_was_weak": True}),
        params={"n": {"easy": 1}},
        eligibility=("has_weak_topic",),
        weight=3,
    ),
    PlantillaMision(
        code="D05",
        scope=MissionScope.DAILY,
        title_template="Enfrenta una prueba del Castillo",
        narrative_key="mission.d05.narrative",
        metric=_metrica("counter", EventType.ASSESSMENT_COMPLETED),
        params={"n": {"medium": 1}},
        eligibility=("has_available_assessment",),
        weight=2,
    ),
    PlantillaMision(
        code="D06",
        scope=MissionScope.DAILY,
        title_template="Aprueba una prueba del Castillo",
        narrative_key="mission.d06.narrative",
        metric=_metrica("counter", EventType.ASSESSMENT_COMPLETED, donde={"passed": True}),
        params={"n": {"hard": 1}},
        eligibility=("has_available_assessment",),
        weight=2,
    ),
    PlantillaMision(
        code="D07",
        scope=MissionScope.DAILY,
        title_template="Adéntrate en un tema nuevo",
        narrative_key="mission.d07.narrative",
        metric=_metrica("flag", EventType.TOPIC_STARTED),
        params={"n": {"easy": 1}},
        eligibility=("has_unstarted_topic",),
        weight=3,
    ),
    PlantillaMision(
        code="D08",
        scope=MissionScope.DAILY,
        title_template="Gana {n} XP en tu conocimiento más flojo",
        narrative_key="mission.d08.narrative",
        metric=_metrica("sum", EventType.XP_AWARDED, donde={"is_educational": True}, campo="amount"),
        params={"n": {"medium": 60, "hard": 120}},
        target_scope="knowledge_area",
        eligibility=({"predicate": "active_areas", "value": 2},),
        weight=2,
    ),
    PlantillaMision(
        code="D09",
        scope=MissionScope.DAILY,
        title_template="Racha de aciertos: {n} seguidas",
        narrative_key="mission.d09.narrative",
        metric=_metrica("consecutive", EventType.QUESTION_ANSWERED, donde={"is_correct": True}),
        params={"n": {"medium": 5, "hard": 8}},
        weight=2,
    ),
    PlantillaMision(
        code="D10",
        scope=MissionScope.DAILY,
        title_template="Estudia {m} minutos efectivos",
        narrative_key="mission.d10.narrative",
        metric=_metrica("sum", EventType.STUDY_TIME_TICKED, campo="seconds"),
        params={"n": {"medium": 900, "hard": 1800}, "m": {"medium": 15, "hard": 30}},
        exclude_if_goal_type=(GoalType.MINUTES.value,),
        weight=2,
    ),
    PlantillaMision(
        code="D11",
        scope=MissionScope.DAILY,
        title_template="Supera un desafío",
        narrative_key="mission.d11.narrative",
        metric=_metrica("counter", EventType.CHALLENGE_COMPLETED),
        params={"n": {"hard": 1}},
        eligibility=("has_available_challenge",),
        weight=2,
    ),
    PlantillaMision(
        code="D12",
        scope=MissionScope.DAILY,
        title_template="Revancha: acierta {n} preguntas que fallaste",
        narrative_key="mission.d12.narrative",
        metric=_metrica(
            "counter",
            EventType.QUESTION_ANSWERED,
            donde={"is_correct": True, "is_retry_of_failed": True},
        ),
        params={"n": {"medium": 3, "hard": 5}},
        eligibility=({"predicate": "has_failed_questions", "value": 3},),
        weight=3,
    ),
    PlantillaMision(
        code="D13",
        scope=MissionScope.DAILY,
        title_template="Cumple tu objetivo antes de las {h}:00",
        narrative_key="mission.d13.narrative",
        metric=_metrica("flag", EventType.DAILY_GOAL_MET, donde={"local_hour_lt": 14}),
        params={"n": {"medium": 1}, "h": 14},
        eligibility=({"predicate": "streak", "value": 3},),
        weight=1,
    ),
)


# ---------------------------------------------------------------------------
# De ruta / especiales (06b §4.6) — se instancian al crear la ruta
# ---------------------------------------------------------------------------

_ESPECIALES: tuple[PlantillaMision, ...] = (
    PlantillaMision(
        code="S01",
        scope=MissionScope.SPECIAL,
        title_template="Primer bastión: completa el primer módulo de esta ruta",
        narrative_key="mission.s01.narrative",
        metric=_metrica("flag", EventType.MODULE_COMPLETED, donde={"module_index": 1}),
        params={"n": 1},
        target_scope="path",
        reward_profile="path_special",
        rewards={"xp": 150, "gold": 75},
    ),
    PlantillaMision(
        code="S02",
        scope=MissionScope.SPECIAL,
        title_template="Prueba de maestría: obtén {n} % o más en una evaluación de esta ruta",
        narrative_key="mission.s02.narrative",
        metric=_metrica("max", EventType.ASSESSMENT_COMPLETED, campo="score_pct"),
        params={"n": 90},
        target_scope="path",
        reward_profile="path_special",
        rewards={"xp": 200, "gold": 100},
    ),
    PlantillaMision(
        code="S03",
        scope=MissionScope.SPECIAL,
        title_template="Conquista la ruta: complétala de principio a fin",
        narrative_key="mission.s03.narrative",
        metric=_metrica("flag", EventType.PATH_COMPLETED),
        params={"n": 1},
        target_scope="path",
        reward_profile="path_special",
        rewards={"xp": 300, "gold": 300},
    ),
    PlantillaMision(
        code="S04",
        scope=MissionScope.SPECIAL,
        title_template="Dominio del conocimiento: alcanza {n} % de dominio",
        narrative_key="mission.s04.narrative",
        metric=_metrica("stat_threshold", EventType.MASTERY_UPDATED, campo="area_after"),
        params={"n": 80},
        target_scope="knowledge_area",
        reward_profile="path_special",
        rewards={"xp": 250, "gold": 200},
        is_active=False,  # 06b §4.6 la marca como fase 2 (depende del dominio de área).
    ),
)


# ---------------------------------------------------------------------------
# Semanales (06b §4.6) — creadas y desactivadas en el MVP
# ---------------------------------------------------------------------------

_SEMANALES: tuple[PlantillaMision, ...] = (
    PlantillaMision(
        code="W01",
        scope=MissionScope.WEEKLY,
        title_template="Gana {n} XP educativo esta semana",
        narrative_key="mission.w01.narrative",
        metric=_metrica("sum", EventType.XP_AWARDED, donde={"is_educational": True}, campo="amount"),
        params={"n": {"medium": 500, "hard": 1000}},
        reward_profile="weekly_default",
        weight=2,
        is_active=False,
    ),
    PlantillaMision(
        code="W02",
        scope=MissionScope.WEEKLY,
        title_template="Estudia {h} horas efectivas",
        narrative_key="mission.w02.narrative",
        metric=_metrica("sum", EventType.STUDY_TIME_TICKED, campo="seconds"),
        params={"n": {"medium": 7200, "hard": 14400}, "h": {"medium": 2, "hard": 4}},
        reward_profile="weekly_default",
        exclude_if_goal_type=(GoalType.MINUTES.value,),
        weight=2,
        is_active=False,
    ),
    PlantillaMision(
        code="W03",
        scope=MissionScope.WEEKLY,
        title_template="Completa {n} módulos",
        narrative_key="mission.w03.narrative",
        metric=_metrica("counter", EventType.MODULE_COMPLETED),
        params={"n": {"medium": 1}},
        reward_profile="weekly_default",
        weight=2,
        is_active=False,
    ),
    PlantillaMision(
        code="W04",
        scope=MissionScope.WEEKLY,
        title_template="Cumple tu objetivo diario {n} días de 7",
        narrative_key="mission.w04.narrative",
        metric=_metrica("counter", EventType.DAILY_GOAL_MET),
        params={"n": {"medium": 4, "hard": 6}},
        reward_profile="weekly_default",
        weight=2,
        is_active=False,
    ),
    PlantillaMision(
        code="W05",
        scope=MissionScope.WEEKLY,
        title_template="Aprueba {n} pruebas del Castillo",
        narrative_key="mission.w05.narrative",
        metric=_metrica("counter", EventType.ASSESSMENT_COMPLETED, donde={"passed": True}),
        params={"n": {"medium": 1, "hard": 2}},
        reward_profile="weekly_default",
        weight=2,
        is_active=False,
    ),
    PlantillaMision(
        code="W06",
        scope=MissionScope.WEEKLY,
        title_template="Sube el dominio de un tema en {n} puntos o más",
        narrative_key="mission.w06.narrative",
        # TODO(fase 2): exige `topic_delta` en el payload de MASTERY_UPDATED (§4.2 solo
        # documenta `topic_before` y `topic_after`). Por eso nace desactivada.
        metric=_metrica("sum", EventType.MASTERY_UPDATED, campo="topic_delta"),
        params={"n": {"medium": 10, "hard": 20}},
        reward_profile="weekly_default",
        weight=1,
        is_active=False,
    ),
)


#: Las 23 plantillas del catálogo inicial: 13 diarias, 4 especiales y 6 semanales.
PLANTILLAS: tuple[PlantillaMision, ...] = _DIARIAS + _ESPECIALES + _SEMANALES


def por_codigo() -> dict[str, PlantillaMision]:
    """Índice `code -> plantilla` del catálogo semilla."""
    return {plantilla.code: plantilla for plantilla in PLANTILLAS}
