"""Panel principal (pantalla P04): todo lo que la app necesita en **una** llamada.

Contrato §7.8, `GET /api/v1/dashboard` → `DashboardOut`:

```
{greeting_key, character{level, rank_title, xp_total, xp_to_next, progress_pct},
 gold_balance, streak{current, best, status, day_status},
 daily_goal{type, target, progress, met, bonus_gold},
 continue_action{type, path_id, module_id, lesson_id, title, breadcrumb, reward_preview},
 knowledge_summary[], missions_summary[],
 week_stats{active_seconds, lessons, achievements}, generation_banner}
```

## Presupuesto de consultas

El panel es la pantalla más visitada del producto, así que se resuelve con **once
consultas planas**, ninguna en bucle y ninguna dependiente de otra salvo donde el
identificador es necesario:

| # | Datos | Tabla(s) | Índice o clave usada |
|---|---|---|---|
| 1 | Configuración del panel | `game_configs` | `ix_game_configs_key_valid_from` (una sola lectura de 4 claves, cacheada 60 s) |
| 2 | Personaje | `characters` | `uq_characters_user_id` |
| 3 | Curva de nivel | `level_definitions` | `uq_level_definitions_scope_level` |
| 4 | Saldo de oro | `wallets` | `uq_wallets_user_id_currency` |
| 5 | Racha y día de hoy | `streaks` ⟕ `streak_days` | `uq_streaks_user_id`, `uq_streak_days_user_id_local_date` |
| 6 | Objetivo diario | `daily_goals` | `uq_daily_goals_user_id` |
| 7 | Continuar la aventura | `user_path_progress` ⟕ `learning_paths`/`path_modules`/`lessons` | `ix_user_path_progress_user_id_last_activity_at` |
| 8 | Conocimientos | `user_area_progress` ⟕ `knowledge_areas` | `ix_user_area_progress_user_id_status` |
| 9 | Misiones de hoy | `user_missions` | `ix_user_missions_user_id_assigned_for_status` |
| 10 | Semana (tiempo, lecciones) y logros | `streak_days`, `user_achievements` | `uq_streak_days_user_id_local_date`, `ix_user_achievements_user_id_highest_tier` |
| 11 | Aviso de generación | `learning_paths` | `ix_learning_paths_user_id_status` |

`progress` **lee** tablas de `identity`, `economy` y `gamification` para armar este
agregado (el contrato asigna la pantalla a `gamification` + `progress`, §7.8); **no
escribe** ninguna de ellas ni importa servicios de otros módulos.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session, aliased

from app.core.time import ensure_utc, to_zone, user_local_date, utcnow
from app.models.content import KnowledgeArea, LearningPath, Lesson, PathModule
from app.models.economy import Wallet
from app.models.enums import (
    Currency,
    DayStatus,
    GoalType,
    KnowledgeAreaStatus,
    LevelScope,
    MissionStatus,
    PathStatus,
    ProgressState,
)
from app.models.gamification import DailyGoal, LevelDefinition, Streak, StreakDay, UserMission
from app.models.identity import Character
from app.models.progress import UserAreaProgress, UserPathProgress
from app.modules.progress import LectorConfiguracion, a_float
from app.modules.progress.estadisticas import ServicioEstadisticas

#: Claves de `game_configs` que necesita el panel.
CLAVES_PANEL: tuple[str, ...] = (
    "goal.default",
    "goal.bonus_gold_base",
    "goal.bonus_gold_cap_days",
    "streak.grace_per_month",
    "xp.lesson_completed",
    "gold.lesson_completed",
)

#: Estados visibles de la racha (§6.10, «Estado visible»). Son nombres de estado, no
#: valores de balance: viajan tal cual al cliente para que elija el copy.
RACHA_ACTIVA_HOY = "ACTIVA_HOY"
RACHA_PENDIENTE_HOY = "PENDIENTE_HOY"
RACHA_PROTEGIDA_POR_GRACIA = "PROTEGIDA_POR_GRACIA"
RACHA_ROTA = "ROTA"

#: Saludo del panel. El contrato fija el campo (`greeting_key`), no su vocabulario:
#: se usan claves en español que la app traduce a su copy.
SALUDO_MANANA = "buenos_dias"
SALUDO_TARDE = "buenas_tardes"
SALUDO_NOCHE = "buenas_noches"
HORA_TARDE = 12
HORA_NOCHE = 20

#: Tipos de la tarjeta «continuar tu aventura».
CONTINUAR_LECCION = "lesson"
CONTINUAR_EVALUACION = "assessment"
CONTINUAR_CREAR_RUTA = "create_path"
CONTINUAR_RUTA_COMPLETA = "path_completed"

#: Cuántos conocimientos muestra el panel.
MAX_CONOCIMIENTOS_PANEL = 5


# ---------------------------------------------------------------------------
# Estructuras del agregado
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PanelPersonaje:
    """Bloque `character` del panel."""

    level: int
    rank_title: str
    xp_total: int
    xp_to_next: int
    progress_pct: float


@dataclass(slots=True)
class PanelRacha:
    """Bloque `streak` del panel."""

    current: int
    best: int
    status: str
    day_status: DayStatus


@dataclass(slots=True)
class PanelObjetivoDiario:
    """Bloque `daily_goal` del panel."""

    type: GoalType
    target: int
    progress: int
    met: bool
    bonus_gold: int


@dataclass(slots=True)
class PanelContinuar:
    """Bloque `continue_action`: la tarjeta «continuar tu aventura»."""

    type: str
    path_id: uuid.UUID | None
    module_id: uuid.UUID | None
    lesson_id: uuid.UUID | None
    title: str
    breadcrumb: str
    reward_preview: dict[str, int]


@dataclass(slots=True)
class PanelConocimiento:
    """Una tarjeta de `knowledge_summary`."""

    knowledge_area_id: uuid.UUID
    slug: str
    name: str
    short_name: str
    icon_key: str | None
    accent_color: str | None
    level: int
    rank_title: str
    mastery: float
    status: KnowledgeAreaStatus


@dataclass(slots=True)
class PanelMision:
    """Una fila de `missions_summary`."""

    user_mission_id: uuid.UUID
    template_code: str
    title: str
    progress: int
    target: int
    status: MissionStatus
    reward_xp: int
    reward_gold: int


@dataclass(slots=True)
class PanelSemana:
    """Bloque `week_stats`."""

    active_seconds: int
    lessons: int
    achievements: int


@dataclass(slots=True)
class PanelGeneracion:
    """Bloque `generation_banner`: hay una ruta generándose o esperando revisión."""

    path_id: uuid.UUID
    title: str
    status: PathStatus


@dataclass(slots=True)
class Panel:
    """`DashboardOut` completo (§7.8). Todas las secciones existen siempre."""

    greeting_key: str
    character: PanelPersonaje
    gold_balance: int
    streak: PanelRacha
    daily_goal: PanelObjetivoDiario
    continue_action: PanelContinuar
    knowledge_summary: list[PanelConocimiento] = field(default_factory=list)
    missions_summary: list[PanelMision] = field(default_factory=list)
    week_stats: PanelSemana = field(default_factory=lambda: PanelSemana(0, 0, 0))
    generation_banner: PanelGeneracion | None = None


# ---------------------------------------------------------------------------
# Funciones puras
# ---------------------------------------------------------------------------


def clave_de_saludo(momento_local: datetime) -> str:
    """Saludo según la hora **local** del usuario."""
    hora = momento_local.hour
    if hora < HORA_TARDE:
        return SALUDO_MANANA
    if hora < HORA_NOCHE:
        return SALUDO_TARDE
    return SALUDO_NOCHE


def estado_visible_racha(
    last_active_date: date_type | None,
    hoy: date_type,
    *,
    gracia_disponible: bool,
) -> str:
    """Estado visible de la racha (§6.10). **No muta nada**: es solo lectura."""
    if last_active_date is None:
        return RACHA_ROTA
    delta = (hoy - last_active_date).days
    if delta == 0:
        return RACHA_ACTIVA_HOY
    if delta == 1:
        return RACHA_PENDIENTE_HOY
    if delta == 2 and gracia_disponible:
        return RACHA_PROTEGIDA_POR_GRACIA
    return RACHA_ROTA


def progreso_del_objetivo(
    goal_type: GoalType,
    *,
    effective_seconds: int,
    activity_units: int,
    educational_xp: int,
) -> int:
    """`progreso(D)` del objetivo diario según su tipo (§6.11)."""
    if goal_type == GoalType.MINUTES:
        return int(effective_seconds // 60)
    if goal_type == GoalType.ACTIVITIES:
        return int(activity_units)
    return int(educational_xp)


def oro_de_constancia(racha_actual: int, base: int, tope_dias: int) -> int:
    """`goal.bonus_gold_base + min(racha, goal.bonus_gold_cap_days)` (§6.3 y §6.11)."""
    return int(base) + min(max(0, int(racha_actual)), int(tope_dias))


def porcentaje_de_nivel(
    xp_total: int, xp_nivel_actual: int, xp_nivel_siguiente: int | None
) -> tuple[int, float]:
    """`(xp_to_next, progress_pct)` a partir de la curva materializada (§6.1).

    En el nivel máximo no hay siguiente umbral: el progreso es 100 % y falta 0.
    """
    if xp_nivel_siguiente is None or xp_nivel_siguiente <= xp_nivel_actual:
        return 0, 100.0
    faltan = max(0, xp_nivel_siguiente - xp_total)
    tramo = xp_nivel_siguiente - xp_nivel_actual
    avance = 100.0 * (xp_total - xp_nivel_actual) / tramo
    return faltan, round(min(100.0, max(0.0, avance)), 2)


# ---------------------------------------------------------------------------
# Servicio
# ---------------------------------------------------------------------------


class ServicioPanel:
    """Construye el agregado del panel principal en pocas consultas."""

    def __init__(self, db: Session, *, lector: LectorConfiguracion | None = None) -> None:
        self.db = db
        self.lector = lector or LectorConfiguracion(db)
        self.estadisticas = ServicioEstadisticas(db)

    def construir(
        self,
        user_id: uuid.UUID,
        timezone_name: str,
        *,
        ahora: datetime | None = None,
    ) -> Panel:
        """Devuelve el `DashboardOut` completo del usuario."""
        momento = ensure_utc(ahora) if ahora else utcnow()
        hoy = user_local_date(momento, timezone_name)
        cfg = self.lector.muchas(CLAVES_PANEL)  # (1)

        personaje = self.personaje(user_id)  # (2) y (3)
        oro = self._oro(user_id)  # (4)
        racha, dia = self._racha(user_id, hoy)  # (5)
        objetivo = self._objetivo(user_id, hoy, racha, dia, cfg)  # (6)
        continuar = self._continuar(user_id, cfg)  # (7)
        conocimientos = self._conocimientos(user_id)  # (8)
        misiones = self._misiones(user_id, hoy)  # (9)
        semana = self.estadisticas.resumen_semana(user_id, timezone_name)  # (10)
        banner = self._banner_generacion(user_id)  # (11)

        return Panel(
            greeting_key=clave_de_saludo(to_zone(momento, timezone_name)),
            character=personaje,
            gold_balance=oro,
            streak=racha,
            daily_goal=objetivo,
            continue_action=continuar,
            knowledge_summary=conocimientos,
            missions_summary=misiones,
            week_stats=PanelSemana(
                active_seconds=int(semana["active_seconds"]),
                lessons=int(semana["lessons"]),
                achievements=int(semana["achievements"]),
            ),
            generation_banner=banner,
        )

    # -- piezas -----------------------------------------------------------

    def personaje(self, user_id: uuid.UUID) -> PanelPersonaje:
        """(2) Personaje y (3) su tramo de la curva de nivel global."""
        fila = self.db.execute(
            sa.select(
                Character.level, Character.xp_total, Character.rank_title
            ).where(Character.user_id == user_id)
        ).one_or_none()
        if fila is None:
            return PanelPersonaje(level=1, rank_title="", xp_total=0, xp_to_next=0, progress_pct=0.0)
        nivel, xp_total, rango = int(fila[0]), int(fila[1]), str(fila[2])

        umbrales = dict(
            self.db.execute(
                sa.select(LevelDefinition.level, LevelDefinition.xp_required).where(
                    LevelDefinition.scope == LevelScope.GLOBAL,
                    LevelDefinition.level.in_([nivel, nivel + 1]),
                )
            ).all()
        )
        faltan, avance = porcentaje_de_nivel(
            xp_total, int(umbrales.get(nivel, 0)), umbrales.get(nivel + 1)
        )
        return PanelPersonaje(
            level=nivel,
            rank_title=rango,
            xp_total=xp_total,
            xp_to_next=faltan,
            progress_pct=avance,
        )

    def _oro(self, user_id: uuid.UUID) -> int:
        """(4) Saldo de la billetera de oro."""
        saldo = self.db.execute(
            sa.select(Wallet.balance).where(
                Wallet.user_id == user_id, Wallet.currency == Currency.GOLD
            )
        ).scalar_one_or_none()
        return int(saldo or 0)

    def _racha(
        self, user_id: uuid.UUID, hoy: date_type
    ) -> tuple[PanelRacha, StreakDay | None]:
        """(5) Racha y el `streak_days` de hoy, en una sola consulta."""
        fila = self.db.execute(
            sa.select(Streak, StreakDay)
            .outerjoin(
                StreakDay,
                sa.and_(
                    StreakDay.user_id == Streak.user_id,
                    StreakDay.local_date == hoy,
                ),
            )
            .where(Streak.user_id == user_id)
        ).one_or_none()
        if fila is None:
            return (
                PanelRacha(current=0, best=0, status=RACHA_ROTA, day_status=DayStatus.INACTIVE),
                None,
            )
        racha, dia = fila[0], fila[1]
        gracia_disponible = racha.grace_used_for_month != hoy.strftime("%Y-%m")
        return (
            PanelRacha(
                current=int(racha.current_length),
                best=int(racha.best_length),
                status=estado_visible_racha(
                    racha.last_active_date, hoy, gracia_disponible=gracia_disponible
                ),
                day_status=dia.day_status if dia is not None else DayStatus.INACTIVE,
            ),
            dia,
        )

    def racha_visible(
        self, user_id: uuid.UUID, timezone_name: str, *, ahora: datetime | None = None
    ) -> PanelRacha:
        """Racha del usuario tal como la muestra el panel (solo lectura, §6.10)."""
        momento = ensure_utc(ahora) if ahora else utcnow()
        return self._racha(user_id, user_local_date(momento, timezone_name))[0]

    def _objetivo(
        self,
        user_id: uuid.UUID,
        hoy: date_type,
        racha: PanelRacha,
        dia: StreakDay | None,
        cfg: dict,
    ) -> PanelObjetivoDiario:
        """(6) Objetivo vigente y su progreso de hoy (§6.11)."""
        meta = self.db.execute(
            sa.select(DailyGoal).where(DailyGoal.user_id == user_id)
        ).scalar_one_or_none()

        por_defecto = cfg["goal.default"]
        if dia is not None and dia.goal_type_snapshot is not None:
            tipo = dia.goal_type_snapshot
            objetivo = int(dia.goal_target_snapshot or 0)
        elif meta is not None:
            tipo = meta.goal_type
            objetivo = int(meta.target)
        else:
            tipo = GoalType(str(por_defecto["type"]))
            objetivo = int(por_defecto["target"])

        progreso = (
            progreso_del_objetivo(
                tipo,
                effective_seconds=int(dia.effective_seconds),
                activity_units=int(dia.activity_units),
                educational_xp=int(dia.educational_xp),
            )
            if dia is not None
            else 0
        )
        return PanelObjetivoDiario(
            type=tipo,
            target=objetivo,
            progress=progreso,
            met=bool(dia and dia.goal_met_at is not None),
            bonus_gold=oro_de_constancia(
                racha.current,
                int(cfg["goal.bonus_gold_base"]),
                int(cfg["goal.bonus_gold_cap_days"]),
            ),
        )

    def _continuar(self, user_id: uuid.UUID, cfg: dict) -> PanelContinuar:
        """(7) Tarjeta «continuar tu aventura»: dónde quedó el usuario."""
        recompensa = {
            "xp": int(cfg["xp.lesson_completed"]),
            "gold": int(cfg["gold.lesson_completed"]),
        }
        modulo_alias = aliased(PathModule)
        fila = self.db.execute(
            sa.select(
                UserPathProgress.learning_path_id,
                UserPathProgress.current_module_id,
                UserPathProgress.current_lesson_id,
                UserPathProgress.status,
                LearningPath.title,
                modulo_alias.title,
                Lesson.title,
            )
            .select_from(UserPathProgress)
            .join(LearningPath, LearningPath.id == UserPathProgress.learning_path_id)
            .outerjoin(modulo_alias, modulo_alias.id == UserPathProgress.current_module_id)
            .outerjoin(Lesson, Lesson.id == UserPathProgress.current_lesson_id)
            .where(
                UserPathProgress.user_id == user_id,
                UserPathProgress.status != ProgressState.ARCHIVED,
                LearningPath.status != PathStatus.ARCHIVED,
            )
            .order_by(
                UserPathProgress.last_activity_at.desc().nullslast(),
                UserPathProgress.learning_path_id,
            )
            .limit(1)
        ).one_or_none()

        if fila is None:
            return PanelContinuar(
                type=CONTINUAR_CREAR_RUTA,
                path_id=None,
                module_id=None,
                lesson_id=None,
                title="Crea tu primera ruta",
                breadcrumb="",
                reward_preview=recompensa,
            )

        path_id, module_id, lesson_id, estado, titulo_ruta, titulo_modulo, titulo_leccion = fila
        if estado == ProgressState.COMPLETED:
            tipo = CONTINUAR_RUTA_COMPLETA
            titulo = titulo_ruta
        elif lesson_id is not None:
            tipo = CONTINUAR_LECCION
            titulo = titulo_leccion or titulo_ruta
        else:
            tipo = CONTINUAR_EVALUACION
            titulo = titulo_modulo or titulo_ruta

        migas = " · ".join(p for p in (titulo_ruta, titulo_modulo) if p)
        return PanelContinuar(
            type=tipo,
            path_id=path_id,
            module_id=module_id,
            lesson_id=lesson_id,
            title=titulo,
            breadcrumb=migas,
            reward_preview=recompensa,
        )

    def _conocimientos(self, user_id: uuid.UUID) -> list[PanelConocimiento]:
        """(8) Conocimientos del usuario con su dominio, ordenados por dominio."""
        filas = self.db.execute(
            sa.select(
                UserAreaProgress.knowledge_area_id,
                UserAreaProgress.level,
                UserAreaProgress.rank_title,
                UserAreaProgress.mastery,
                UserAreaProgress.status,
                KnowledgeArea.slug,
                KnowledgeArea.name,
                KnowledgeArea.short_name,
                KnowledgeArea.icon_key,
                KnowledgeArea.accent_color,
            )
            .join(KnowledgeArea, KnowledgeArea.id == UserAreaProgress.knowledge_area_id)
            .where(UserAreaProgress.user_id == user_id)
            .order_by(UserAreaProgress.mastery.desc(), KnowledgeArea.name)
            .limit(MAX_CONOCIMIENTOS_PANEL)
        ).all()
        return [
            PanelConocimiento(
                knowledge_area_id=f[0],
                slug=f[5],
                name=f[6],
                short_name=f[7],
                icon_key=f[8],
                accent_color=f[9],
                level=int(f[1]),
                rank_title=f[2],
                mastery=a_float(f[3]),
                status=f[4],
            )
            for f in filas
        ]

    def _misiones(self, user_id: uuid.UUID, hoy: date_type) -> list[PanelMision]:
        """(9) Misiones asignadas para hoy (las genera `gamification`; aquí solo se leen)."""
        filas = self.db.execute(
            sa.select(UserMission)
            .where(
                UserMission.user_id == user_id,
                UserMission.assigned_for == hoy,
                UserMission.status.in_(
                    [MissionStatus.ACTIVE, MissionStatus.COMPLETED, MissionStatus.CLAIMED]
                ),
            )
            .order_by(UserMission.status, UserMission.id)
        ).scalars()
        return [
            PanelMision(
                user_mission_id=m.id,
                template_code=m.template_code,
                title=m.title,
                progress=int(m.progress),
                target=int(m.target),
                status=m.status,
                reward_xp=int(m.reward_xp),
                reward_gold=int(m.reward_gold),
            )
            for m in filas
        ]

    def _banner_generacion(self, user_id: uuid.UUID) -> PanelGeneracion | None:
        """(11) Aviso «tu ruta se está preparando» (P06)."""
        fila = self.db.execute(
            sa.select(LearningPath.id, LearningPath.title, LearningPath.status)
            .where(
                LearningPath.user_id == user_id,
                LearningPath.status.in_(
                    [PathStatus.GENERATING, PathStatus.PENDING_REVIEW, PathStatus.DRAFT]
                ),
            )
            .order_by(LearningPath.created_at.desc())
            .limit(1)
        ).one_or_none()
        if fila is None:
            return None
        return PanelGeneracion(path_id=fila[0], title=fila[1], status=fila[2])


__all__ = [
    "CLAVES_PANEL",
    "CONTINUAR_CREAR_RUTA",
    "CONTINUAR_EVALUACION",
    "CONTINUAR_LECCION",
    "CONTINUAR_RUTA_COMPLETA",
    "MAX_CONOCIMIENTOS_PANEL",
    "RACHA_ACTIVA_HOY",
    "RACHA_PENDIENTE_HOY",
    "RACHA_PROTEGIDA_POR_GRACIA",
    "RACHA_ROTA",
    "Panel",
    "PanelConocimiento",
    "PanelContinuar",
    "PanelGeneracion",
    "PanelMision",
    "PanelObjetivoDiario",
    "PanelPersonaje",
    "PanelRacha",
    "PanelSemana",
    "ServicioPanel",
    "clave_de_saludo",
    "estado_visible_racha",
    "oro_de_constancia",
    "porcentaje_de_nivel",
    "progreso_del_objetivo",
]
