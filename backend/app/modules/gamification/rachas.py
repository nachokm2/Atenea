"""Racha, día activo, calendario y objetivo diario (CONTRACT.md §6.10 y §6.11).

Piezas de este archivo:

- **Agregado diario** (`streak_days`): una fila por usuario y **fecha local**; es
  la fuente de verdad del calendario, del día activo y del objetivo diario.
- **Día activo**: `goal_met_at IS NOT NULL` **o**
  `educational_xp >= streak.min_daily_educational_xp`. El XP de bonificación
  (misiones, hitos, logros) nunca cuenta.
- **Racha** (`streaks`): `activar_dia` es idempotente y replica el pseudocódigo de
  §6.10, con día de gracia (1 por mes calendario, asociado al mes del día
  perdido) y ajuste por viaje (1 cada 30 días).
- **Objetivo diario** (`daily_goals`) en sus tres formas: `minutos`,
  `actividades` y `xp`; las subidas rigen de inmediato y las bajadas al día
  siguiente.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.time import user_local_date, utcnow
from app.models.enums import DayStatus, EventType, GoalType, StreakChange
from app.models.gamification import DailyGoal, Streak, StreakDay
from app.modules.gamification.servicio_config import ServicioConfig

#: Estados visibles de la racha (solo lectura, no mutan nada; §6.10).
ESTADO_ACTIVA_HOY = "ACTIVA_HOY"
ESTADO_PENDIENTE_HOY = "PENDIENTE_HOY"
ESTADO_PROTEGIDA_POR_GRACIA = "PROTEGIDA_POR_GRACIA"
ESTADO_ROTA = "ROTA"


@dataclass(slots=True)
class ResultadoRacha:
    """Lo que produjo una activación de día sobre la racha."""

    current: int
    best: int
    previous: int
    change: StreakChange | None
    day_status: DayStatus
    cambio_efectivo: bool = False
    milestone_length: int | None = None
    milestone_first_time: bool = False
    milestone_reward: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResultadoObjetivo:
    """Estado del objetivo diario tras aplicar un evento."""

    goal_type: GoalType
    target: int
    progress: int
    met: bool
    just_met: bool
    bonus_gold: int = 0


# ---------------------------------------------------------------------------
# Objetivo diario
# ---------------------------------------------------------------------------


def obtener_o_crear_objetivo(db: Session, cfg: ServicioConfig, usuario_id: uuid.UUID, hoy: date_type) -> DailyGoal:
    """Devuelve el objetivo diario del usuario, creándolo con `goal.default` si falta.

    Aplica de paso el cambio programado cuyo `pending_from` ya llegó (§6.11).
    """
    objetivo = db.execute(sa.select(DailyGoal).where(DailyGoal.user_id == usuario_id)).scalar_one_or_none()
    if objetivo is None:
        por_defecto = cfg.obtener_json("goal.default")
        objetivo = DailyGoal(
            user_id=usuario_id,
            goal_type=GoalType(por_defecto["type"]),
            target=int(por_defecto["target"]),
            effective_from=hoy,
        )
        db.add(objetivo)
        db.flush()
        return objetivo

    if objetivo.pending_from is not None and objetivo.pending_from <= hoy:
        if objetivo.pending_type is not None:
            objetivo.goal_type = objetivo.pending_type
        if objetivo.pending_target is not None:
            objetivo.target = int(objetivo.pending_target)
        objetivo.effective_from = objetivo.pending_from
        objetivo.pending_type = None
        objetivo.pending_target = None
        objetivo.pending_from = None
        db.flush()
    return objetivo


def cambiar_objetivo(
    db: Session,
    cfg: ServicioConfig,
    usuario_id: uuid.UUID,
    hoy: date_type,
    *,
    goal_type: GoalType,
    target: int,
) -> DailyGoal:
    """Cambia el objetivo: las subidas rigen ya; las bajadas, al día siguiente (§6.11)."""
    objetivo = obtener_o_crear_objetivo(db, cfg, usuario_id, hoy)
    es_subida = goal_type != objetivo.goal_type or int(target) > int(objetivo.target)
    inmediato = cfg.obtener_str("goal.change_effective") != "next_day" or es_subida
    if inmediato:
        objetivo.goal_type = goal_type
        objetivo.target = int(target)
        objetivo.effective_from = hoy
        objetivo.pending_type = None
        objetivo.pending_target = None
        objetivo.pending_from = None
    else:
        objetivo.pending_type = goal_type
        objetivo.pending_target = int(target)
        objetivo.pending_from = hoy + timedelta(days=1)
    db.flush()
    return objetivo


def progreso_objetivo(dia: StreakDay) -> int:
    """Progreso del día en la unidad de su objetivo (§6.11)."""
    if dia.goal_type_snapshot == GoalType.MINUTES:
        return int(dia.effective_seconds // 60)
    if dia.goal_type_snapshot == GoalType.ACTIVITIES:
        return int(dia.activity_units)
    if dia.goal_type_snapshot == GoalType.XP:
        return int(dia.educational_xp)
    return 0


# ---------------------------------------------------------------------------
# Agregado diario (`streak_days`)
# ---------------------------------------------------------------------------


def obtener_o_crear_dia(
    db: Session, cfg: ServicioConfig, usuario_id: uuid.UUID, local_date: date_type
) -> StreakDay:
    """Fila de `streak_days` del usuario para esa fecha local, con el objetivo del día."""
    dia = db.execute(
        sa.select(StreakDay).where(StreakDay.user_id == usuario_id, StreakDay.local_date == local_date)
    ).scalar_one_or_none()
    if dia is not None:
        return dia

    objetivo = obtener_o_crear_objetivo(db, cfg, usuario_id, local_date)
    dia = StreakDay(
        user_id=usuario_id,
        local_date=local_date,
        goal_type_snapshot=objetivo.goal_type,
        goal_target_snapshot=int(objetivo.target),
        day_status=DayStatus.INACTIVE,
    )
    db.add(dia)
    db.flush()
    return dia


def unidades_de_actividad(
    cfg: ServicioConfig,
    event_type: EventType,
    *,
    preguntas_antes: int = 0,
    preguntas_despues: int = 0,
) -> int:
    """Unidades del objetivo `actividades` que aporta un evento (`goal.activity_units`)."""
    unidades = cfg.obtener_json("goal.activity_units")
    if event_type == EventType.LESSON_COMPLETED:
        return int(unidades.get("lesson", 0))
    if event_type == EventType.CHALLENGE_COMPLETED:
        return int(unidades.get("challenge", 0))
    if event_type == EventType.REVIEW_COMPLETED:
        return int(unidades.get("review", 0))
    if event_type == EventType.ASSESSMENT_COMPLETED:
        return int(unidades.get("assessment", 0))
    if event_type == EventType.QUESTION_ANSWERED:
        por_bloque = int(unidades.get("questions_per_block", 5)) or 5
        valor_bloque = int(unidades.get("questions_block", 0))
        bloques = (int(preguntas_despues) // por_bloque) - (int(preguntas_antes) // por_bloque)
        return max(0, bloques) * valor_bloque
    return 0


def registrar_actividad(
    db: Session,
    cfg: ServicioConfig,
    *,
    usuario_id: uuid.UUID,
    local_date: date_type,
    momento: datetime | None = None,
    educational_xp: int = 0,
    bonus_xp: int = 0,
    effective_seconds: int = 0,
    activity_units: int = 0,
    lessons_completed: int = 0,
    questions_total: int = 0,
    questions_correct: int = 0,
    activities_completed: int = 0,
) -> tuple[StreakDay, bool]:
    """Acumula los hechos del día en `streak_days`.

    Devuelve la fila del día y si esta fue la **primera actividad del día**
    (que paga `xp.first_activity_of_day` y dispara el overlay de racha).
    """
    instante = momento or utcnow()
    dia = obtener_o_crear_dia(db, cfg, usuario_id, local_date)

    es_primera = dia.first_activity_at is None and (
        educational_xp > 0 or effective_seconds > 0 or activities_completed > 0 or questions_total > 0
    )

    dia.educational_xp = int(dia.educational_xp) + int(educational_xp)
    dia.bonus_xp = int(dia.bonus_xp) + int(bonus_xp)
    dia.effective_seconds = int(dia.effective_seconds) + int(effective_seconds)
    dia.activity_units = int(dia.activity_units) + int(activity_units)
    dia.lessons_completed = int(dia.lessons_completed) + int(lessons_completed)
    dia.questions_total = int(dia.questions_total) + int(questions_total)
    dia.questions_correct = int(dia.questions_correct) + int(questions_correct)
    dia.activities_completed = int(dia.activities_completed) + int(activities_completed)

    if es_primera:
        dia.first_activity_at = instante
    if educational_xp or effective_seconds or activities_completed or questions_total:
        dia.last_activity_at = instante

    dia.goal_progress = progreso_objetivo(dia)
    db.flush()
    return dia, es_primera


def dia_activo(cfg: ServicioConfig, dia: StreakDay) -> bool:
    """Definición de día activo del contrato (§6.10)."""
    if dia.goal_met_at is not None:
        return True
    minimo = cfg.obtener_int("streak.min_daily_educational_xp")
    return int(dia.educational_xp) >= minimo


def bono_de_objetivo(cfg: ServicioConfig, racha_actual: int) -> int:
    """Bono de constancia en oro al cumplir el objetivo diario (§6.3 y §6.11).

    `goal.bonus_gold_base + min(racha_actual, goal.bonus_gold_cap_days)`.
    """
    base = cfg.obtener_int("goal.bonus_gold_base")
    tope = cfg.obtener_int("goal.bonus_gold_cap_days")
    return base + min(int(racha_actual), tope)


def evaluar_objetivo(
    db: Session,
    cfg: ServicioConfig,
    dia: StreakDay,
    *,
    racha_actual: int = 0,
    momento: datetime | None = None,
) -> ResultadoObjetivo:
    """Comprueba el objetivo diario y marca su cumplimiento (una vez por fecha)."""
    instante = momento or utcnow()
    objetivo_tipo = dia.goal_type_snapshot or GoalType.MINUTES
    meta = int(dia.goal_target_snapshot or 0)
    progreso = progreso_objetivo(dia)
    dia.goal_progress = progreso

    ya_cumplido = dia.goal_met_at is not None
    cumple_ahora = meta > 0 and progreso >= meta
    just_met = cumple_ahora and not ya_cumplido

    bono = 0
    if just_met:
        dia.goal_met_at = instante
        bono = bono_de_objetivo(cfg, racha_actual)
        db.flush()

    return ResultadoObjetivo(
        goal_type=objetivo_tipo,
        target=meta,
        progress=progreso,
        met=ya_cumplido or cumple_ahora,
        just_met=just_met,
        bonus_gold=bono,
    )


# ---------------------------------------------------------------------------
# Racha (`streaks`)
# ---------------------------------------------------------------------------


def obtener_o_crear_racha(db: Session, usuario_id: uuid.UUID) -> Streak:
    """Fila de `streaks` del usuario, creada vacía si aún no existe."""
    racha = db.execute(sa.select(Streak).where(Streak.user_id == usuario_id)).scalar_one_or_none()
    if racha is None:
        racha = Streak(user_id=usuario_id)
        db.add(racha)
        db.flush()
    return racha


def _mes(fecha: date_type) -> str:
    """Mes calendario en formato `AAAA-MM` (clave de la gracia mensual)."""
    return f"{fecha.year:04d}-{fecha.month:02d}"


def gracia_disponible(cfg: ServicioConfig, racha: Streak, mes_perdido: str) -> bool:
    """Indica si queda día de gracia para el mes del día perdido (§6.10)."""
    if cfg.obtener_int("streak.grace_per_month") < 1:
        return False
    return racha.grace_used_for_month != mes_perdido


def ajuste_viaje_disponible(cfg: ServicioConfig, racha: Streak, hoy: date_type) -> bool:
    """Indica si queda ajuste por viaje (1 cada 30 días, §6.10)."""
    if cfg.obtener_int("streak.travel_skip_per_30d") < 1:
        return False
    if racha.travel_skip_used_on is None:
        return True
    return (hoy - racha.travel_skip_used_on).days >= 30


def _marcar_dia(db: Session, cfg: ServicioConfig, usuario_id: uuid.UUID, fecha: date_type, estado: DayStatus) -> None:
    """Marca una fecha local con un estado del calendario (gracia o viaje)."""
    dia = obtener_o_crear_dia(db, cfg, usuario_id, fecha)
    dia.day_status = estado
    db.flush()


def _cerrar_racha(racha: Streak, momento: datetime) -> None:
    """Cierra la racha en curso guardando su longitud como `previous_length`."""
    if int(racha.current_length) > 0:
        racha.previous_length = int(racha.current_length)
        racha.broken_at = momento


def hito_de_racha(cfg: ServicioConfig, longitud: int) -> int | None:
    """Devuelve el hito alcanzado por esa longitud, o `None` (§6.10)."""
    hitos = [int(h) for h in cfg.obtener_lista("streak.milestones")]
    if longitud in hitos:
        return longitud
    cada = cfg.obtener_int("streak.repeat_milestone_every")
    if cada > 0 and longitud > 100 and longitud % cada == 0:
        return longitud
    return None


def recompensa_de_hito(cfg: ServicioConfig, longitud: int) -> dict[str, Any]:
    """Recompensa del hito (`streak.milestone_rewards`), con la entrada `repeat`."""
    recompensas = cfg.obtener_json("streak.milestone_rewards")
    if str(longitud) in recompensas:
        return dict(recompensas[str(longitud)])
    return dict(recompensas.get("repeat", {}))


def proximo_hito(cfg: ServicioConfig, actual: int) -> dict[str, Any] | None:
    """Próximo hito y lo que falta para alcanzarlo (`GET /api/v1/streak`)."""
    hitos = sorted(int(h) for h in cfg.obtener_lista("streak.milestones"))
    siguientes = [h for h in hitos if h > actual]
    if siguientes:
        objetivo = siguientes[0]
    else:
        cada = cfg.obtener_int("streak.repeat_milestone_every")
        if cada <= 0:
            return None
        objetivo = ((actual // cada) + 1) * cada
    return {
        "days": objetivo,
        "remaining": objetivo - actual,
        "reward": recompensa_de_hito(cfg, objetivo),
    }


def activar_dia(
    db: Session,
    cfg: ServicioConfig,
    usuario_id: uuid.UUID,
    hoy: date_type,
    *,
    momento: datetime | None = None,
    viaje_hacia_el_este: bool = False,
) -> ResultadoRacha:
    """Marca `hoy` como día activo y actualiza la racha (§6.10, idempotente)."""
    instante = momento or utcnow()
    racha = db.execute(
        sa.select(Streak).where(Streak.user_id == usuario_id).with_for_update()
    ).scalar_one_or_none()
    if racha is None:
        racha = obtener_o_crear_racha(db, usuario_id)

    dia = obtener_o_crear_dia(db, cfg, usuario_id, hoy)

    if racha.last_active_date == hoy:
        # Idempotente: el día ya estaba activo, no se toca nada.
        dia.day_status = DayStatus.ACTIVE
        db.flush()
        return ResultadoRacha(
            current=int(racha.current_length),
            best=int(racha.best_length),
            previous=int(racha.previous_length),
            change=racha.last_change,
            day_status=DayStatus.ACTIVE,
            cambio_efectivo=False,
        )

    anterior = int(racha.current_length)
    cambio: StreakChange

    if racha.last_active_date == hoy - timedelta(days=1):
        racha.current_length = anterior + 1
        cambio = StreakChange.EXTENDED
    elif racha.last_active_date == hoy - timedelta(days=2):
        perdido = hoy - timedelta(days=1)
        if viaje_hacia_el_este and ajuste_viaje_disponible(cfg, racha, hoy):
            _marcar_dia(db, cfg, usuario_id, perdido, DayStatus.TRAVEL)
            racha.travel_skip_used_on = perdido
            racha.current_length = anterior + 1
            cambio = StreakChange.TRAVEL_SKIP
        elif gracia_disponible(cfg, racha, _mes(perdido)):
            _marcar_dia(db, cfg, usuario_id, perdido, DayStatus.GRACE)
            racha.grace_used_for_month = _mes(perdido)
            racha.current_length = anterior + 1
            cambio = StreakChange.GRACE_USED
        else:
            _cerrar_racha(racha, instante)
            racha.current_length = 1
            racha.started_on = hoy
            cambio = StreakChange.STARTED
    else:
        _cerrar_racha(racha, instante)
        racha.current_length = 1
        racha.started_on = hoy
        cambio = StreakChange.STARTED

    if racha.started_on is None:
        racha.started_on = hoy
    racha.last_active_date = hoy
    racha.total_active_days = int(racha.total_active_days) + 1
    racha.best_length = max(int(racha.best_length), int(racha.current_length))
    racha.last_change = cambio
    dia.day_status = DayStatus.ACTIVE
    db.flush()

    longitud = int(racha.current_length)
    hito = hito_de_racha(cfg, longitud)
    primera_vez = False
    recompensa: dict[str, Any] = {}
    if hito is not None:
        primera_vez = hito > int(racha.last_milestone_reached)
        recompensa = recompensa_de_hito(cfg, hito)
        racha.last_milestone_reached = max(int(racha.last_milestone_reached), hito)
        db.flush()

    return ResultadoRacha(
        current=longitud,
        best=int(racha.best_length),
        previous=int(racha.previous_length),
        change=cambio,
        day_status=DayStatus.ACTIVE,
        cambio_efectivo=True,
        milestone_length=hito,
        milestone_first_time=primera_vez,
        milestone_reward=recompensa,
    )


def estado_visible(racha: Streak | None, hoy: date_type, cfg: ServicioConfig) -> str:
    """Estado visible de la racha (solo lectura, §6.10)."""
    if racha is None or racha.last_active_date is None:
        return ESTADO_ROTA
    if racha.last_active_date == hoy:
        return ESTADO_ACTIVA_HOY
    if racha.last_active_date == hoy - timedelta(days=1):
        return ESTADO_PENDIENTE_HOY
    if racha.last_active_date == hoy - timedelta(days=2) and gracia_disponible(
        cfg, racha, _mes(hoy - timedelta(days=1))
    ):
        return ESTADO_PROTEGIDA_POR_GRACIA
    return ESTADO_ROTA


# ---------------------------------------------------------------------------
# Calendario
# ---------------------------------------------------------------------------


def calendario_mensual(db: Session, usuario_id: uuid.UUID, anio: int, mes: int) -> list[StreakDay]:
    """Filas de `streak_days` de un mes local, de la más antigua a la más reciente."""
    inicio = date_type(anio, mes, 1)
    fin = date_type(anio + (mes // 12), (mes % 12) + 1, 1)
    return list(
        db.execute(
            sa.select(StreakDay)
            .where(
                StreakDay.user_id == usuario_id,
                StreakDay.local_date >= inicio,
                StreakDay.local_date < fin,
            )
            .order_by(StreakDay.local_date)
        )
        .scalars()
        .all()
    )


def fecha_local_de(usuario_timezone: str | None, momento: datetime | None = None) -> date_type:
    """Fecha local del usuario para un instante (atajo sobre `app.core.time`)."""
    return user_local_date(momento, usuario_timezone)


__all__ = [
    "ESTADO_ACTIVA_HOY",
    "ESTADO_PENDIENTE_HOY",
    "ESTADO_PROTEGIDA_POR_GRACIA",
    "ESTADO_ROTA",
    "ResultadoObjetivo",
    "ResultadoRacha",
    "activar_dia",
    "ajuste_viaje_disponible",
    "bono_de_objetivo",
    "calendario_mensual",
    "cambiar_objetivo",
    "dia_activo",
    "estado_visible",
    "evaluar_objetivo",
    "fecha_local_de",
    "gracia_disponible",
    "hito_de_racha",
    "obtener_o_crear_dia",
    "obtener_o_crear_objetivo",
    "obtener_o_crear_racha",
    "progreso_objetivo",
    "proximo_hito",
    "recompensa_de_hito",
    "registrar_actividad",
    "unidades_de_actividad",
]
