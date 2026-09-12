"""Reglas de recompensa: qué paga cada evento de aprendizaje.

Es la tabla que convierte un hecho ("terminó una lección") en XP y oro. Sin
estas filas el motor procesa el evento y no otorga nada: el usuario completa una
lección y no recibe nada, que es exactamente lo que el producto no puede
permitirse.

Ninguna regla lleva cifras escritas a mano: cada una apunta a su clave de
`game_configs` (`xp_config_key` / `gold_config_key`), de modo que calibrar la
economía es cambiar un parámetro, nunca tocar el código (brief §7 y §13).

Banderas importantes de cada regla:

- ``is_educational``: si la recompensa cuenta como aprendizaje real. Lo que paga
  la propia gamificación (misiones, hitos, logros) va en ``False`` para que no
  alimente el objetivo diario ni la racha (CONTRACT.md §4.1, regla 3).
- ``first_time_only``: solo la primera vez que se completa esa entidad.
- ``respects_repeat_multiplier``: repetir la misma actividad rinde cada vez
  menos, según ``xp.repeat_multipliers``.
- ``respects_daily_cap``: sujeto al tope blando diario ``xp.daily_softcap``.
"""

from __future__ import annotations

from typing import Any

from app.models.enums import EventType, GoldSource, XPSource

#: ``code`` estable → definición de la regla.
REGLAS: tuple[dict[str, Any], ...] = (
    {
        "code": "welcome_bag",
        "event_type": EventType.CHARACTER_CREATED,
        "gold_config_key": "gold.welcome",
        "gold_source": GoldSource.WELCOME,
        "is_educational": False,
        "first_time_only": True,
        "respects_repeat_multiplier": False,
        "respects_daily_cap": False,
        "priority": 10,
    },
    {
        "code": "lesson_completed",
        "event_type": EventType.LESSON_COMPLETED,
        "xp_config_key": "xp.lesson_completed",
        "xp_source": XPSource.LESSON,
        "gold_config_key": "gold.lesson_completed",
        "gold_source": GoldSource.LESSON,
        "is_educational": True,
        "first_time_only": False,
        "respects_repeat_multiplier": True,
        "respects_daily_cap": True,
        "priority": 100,
    },
    {
        "code": "challenge_completed",
        "event_type": EventType.CHALLENGE_COMPLETED,
        "xp_config_key": "xp.challenge_completed",
        "xp_source": XPSource.CHALLENGE,
        "gold_config_key": "gold.challenge_completed",
        "gold_source": GoldSource.CHALLENGE,
        "is_educational": True,
        "first_time_only": False,
        "respects_repeat_multiplier": True,
        "respects_daily_cap": True,
        "priority": 100,
    },
    {
        "code": "review_completed",
        "event_type": EventType.REVIEW_COMPLETED,
        "xp_config_key": "xp.review_completed",
        "xp_source": XPSource.REVIEW,
        "gold_config_key": "gold.review_completed",
        "gold_source": GoldSource.REVIEW,
        "is_educational": True,
        "first_time_only": False,
        "respects_repeat_multiplier": True,
        "respects_daily_cap": True,
        "priority": 100,
    },
    {
        "code": "assessment_passed",
        "event_type": EventType.ASSESSMENT_COMPLETED,
        "condition": {"outcome_in": ["PASSED", "EXCELLENT", "PERFECT"]},
        "xp_config_key": "xp.assessment_passed",
        "xp_source": XPSource.ASSESSMENT,
        "gold_config_key": "gold.assessment_passed",
        "gold_source": GoldSource.ASSESSMENT,
        "is_educational": True,
        "first_time_only": True,
        "respects_repeat_multiplier": True,
        "respects_daily_cap": True,
        "priority": 90,
    },
    {
        "code": "module_completed",
        "event_type": EventType.MODULE_COMPLETED,
        "xp_config_key": "xp.module_completed",
        "xp_source": XPSource.MODULE,
        "gold_config_key": "gold.module_completed",
        "gold_source": GoldSource.MODULE,
        "is_educational": True,
        "first_time_only": True,
        "respects_repeat_multiplier": False,
        "respects_daily_cap": True,
        "priority": 80,
    },
    {
        "code": "path_completed",
        "event_type": EventType.PATH_COMPLETED,
        "xp_config_key": "xp.path_completed",
        "xp_source": XPSource.PATH,
        "gold_config_key": "gold.path_completed",
        "gold_source": GoldSource.PATH,
        "is_educational": True,
        "first_time_only": True,
        "respects_repeat_multiplier": False,
        "respects_daily_cap": False,
        "priority": 70,
    },
    {
        "code": "daily_goal_met",
        "event_type": EventType.DAILY_GOAL_MET,
        "xp_config_key": "xp.daily_goal",
        "xp_source": XPSource.FIRST_ACTIVITY_OF_DAY,
        "gold_config_key": "goal.bonus_gold_base",
        "gold_source": GoldSource.DAILY_GOAL,
        # Cumplir el objetivo es constancia, no conocimiento nuevo: su premio no
        # vuelve a alimentar el objetivo ni la racha (§4.1 regla 3).
        "is_educational": False,
        "first_time_only": False,
        "respects_repeat_multiplier": False,
        "respects_daily_cap": False,
        "priority": 60,
    },
)


def definiciones() -> tuple[dict[str, Any], ...]:
    """Devuelve las reglas normalizadas, con los valores por omisión aplicados.

    `valid_from` y `valid_to` se dejan fuera a propósito: la columna de vigencia
    no admite nulos y su valor por defecto lo pone la base, de modo que una regla
    recién sembrada rige desde el momento en que se inserta.
    """
    salida: list[dict[str, Any]] = []
    for regla in REGLAS:
        fila: dict[str, Any] = {
            "condition": {},
            "xp_amount": 0,
            "xp_config_key": None,
            "xp_source": None,
            "gold_amount": 0,
            "gold_config_key": None,
            "gold_source": None,
            "item_id": None,
            "is_educational": True,
            "first_time_only": False,
            "respects_daily_cap": True,
            "respects_repeat_multiplier": True,
            "priority": 100,
            "is_active": True,
        }
        fila.update(regla)
        salida.append(fila)
    return tuple(salida)


__all__ = ["REGLAS", "definiciones"]
