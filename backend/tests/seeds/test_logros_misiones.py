"""Logros y plantillas de misión: forma declarativa y evaluación real por el motor.

Comprobaciones exigidas:

- Los 32 logros de 06b §5.4 están sembrados, con niveles de objetivo **estrictamente
  creciente** y reglas que solo escuchan eventos del catálogo del contrato §4.2.
- `app.modules.gamification.logros.evaluar_por_evento` procesa todas las reglas
  sembradas **sin lanzar ninguna excepción**, y desbloquea lo que debe desbloquear.
- Las 23 plantillas de misión están sembradas con el reparto de 06b §4.6, las
  semanales desactivadas, y cada `title_template` se interpola sin dejar marcadores
  sueltos.
"""

from __future__ import annotations

from collections import Counter

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.enums import (
    AchievementCategory,
    AchievementTier,
    EventType,
    MissionMetricType,
    MissionScope,
    MissionTier,
)
from app.models.gamification import Achievement, MissionTemplate
from app.models.identity import User
from app.modules.gamification import logros as motor_logros, misiones as motor_misiones, reglas
from app.modules.gamification.servicio_config import ServicioConfig
from app.seeds.logros import CODIGOS
from app.seeds.misiones import PLANTILLAS

pytestmark = pytest.mark.db

#: Reparto por categoría de 06b §5.4.
CATEGORIAS_ESPERADAS: dict[AchievementCategory, int] = {
    AchievementCategory.LEARNING: 6,
    AchievementCategory.MASTERY: 7,
    AchievementCategory.CONSISTENCY: 7,
    AchievementCategory.COLLECTION: 5,
    AchievementCategory.EXPLORATION: 3,
    AchievementCategory.MILESTONE: 4,
}

#: Payload rico con todos los campos que citan las reglas sembradas (§4.2).
PAYLOAD_COMPLETO: dict[str, object] = {
    "counts_for_progress": True,
    "is_correct": True,
    "is_retry_of_failed": True,
    "accuracy_pct": 100,
    "questions_total": 5,
    "questions_correct": 5,
    "passed": True,
    "score_pct": 100,
    "topics_mastered": 3,
    "areas_mastered": 2,
    "current_length": 9,
    "best_length": 9,
    "items_count": 6,
    "knowledge_linked": True,
    "rarity": "legendary",
    "slots_filled": 8,
    "slots_total": 8,
    "territories_unlocked": 3,
    "local_hour": 8,
    "level_after": 7,
    "module_index": 1,
    "knowledge_area_id": "11111111-1111-1111-1111-111111111111",
    "path_id": "22222222-2222-2222-2222-222222222222",
    "amount": 120,
    "is_educational": True,
    "seconds": 60,
    "area_after": 85,
    "topic_was_weak": True,
}


def _logros(db: Session) -> list[Achievement]:
    """Los logros sembrados, leídos de la base."""
    return list(db.execute(sa.select(Achievement).where(Achievement.code.in_(CODIGOS))).scalars())


def test_estan_los_32_logros_con_el_reparto_del_documento(db: Session) -> None:
    """06b §5.4: 6 aprendizaje · 7 dominio · 7 constancia · 5 colección · 3 exploración · 4 hitos."""
    filas = _logros(db)
    assert len(filas) == 32
    assert len(set(CODIGOS)) == 32
    assert Counter(fila.category for fila in filas) == CATEGORIAS_ESPERADAS


def test_los_niveles_tienen_objetivos_estrictamente_crecientes(db: Session) -> None:
    """Validación de catálogo de 06b §5.2: bronce < plata < oro."""
    for fila in _logros(db):
        objetivos = [int(nivel["target"]) for nivel in fila.tiers]
        assert objetivos, fila.code
        assert objetivos == sorted(set(objetivos)), fila.code
        etiquetas = [str(nivel["tier"]) for nivel in fila.tiers]
        assert len(etiquetas) == len(set(etiquetas)), fila.code
        for etiqueta in etiquetas:
            assert AchievementTier(etiqueta)
        if len(etiquetas) == 1:
            assert etiquetas == [AchievementTier.SINGLE.value], fila.code
        else:
            assert etiquetas == [
                AchievementTier.BRONZE.value,
                AchievementTier.SILVER.value,
                AchievementTier.GOLD.value,
            ], fila.code


def test_las_reglas_solo_escuchan_eventos_del_contrato(db: Session) -> None:
    """Todo `rule.event` y todo `on_events` pertenece a `EventType` (§4.2)."""
    nombres = {evento.value for evento in EventType}
    tipos = {metrica.value for metrica in MissionMetricType}
    for fila in _logros(db):
        regla = dict(fila.rule)
        assert str(regla["type"]) in tipos, fila.code
        assert str(regla["event"]) in nombres, fila.code
        for evento in regla.get("on_events", []):
            assert str(evento) in nombres, fila.code


def test_el_motor_evalua_todas_las_reglas_sin_error(db: Session, cfg: ServicioConfig, usuario: User) -> None:
    """El evaluador real procesa cada evento escuchado por la semilla sin reventar."""
    estado = reglas.EstadoUsuario(
        user_id=usuario.id,
        xp_total=5_000,
        level=7,
        streak_current=9,
        streak_best=9,
        total_active_days=40,
    )
    eventos = sorted(
        {str(dict(fila.rule)["event"]) for fila in _logros(db)}
        | {str(evento) for fila in _logros(db) for evento in dict(fila.rule).get("on_events", [])}
    )
    assert eventos, "la semilla debe escuchar al menos un evento"

    desbloqueados: list[str] = []
    for nombre in eventos:
        resultados = motor_logros.evaluar_por_evento(
            db,
            cfg,
            usuario_id=usuario.id,
            event_type=EventType(nombre),
            payload=dict(PAYLOAD_COMPLETO),
            estado_usuario=estado,
        )
        for resultado in resultados:
            for nivel in resultado.desbloqueados:
                desbloqueados.append(resultado.achievement.code)
                assert nivel.reward_xp >= 0
                assert nivel.reward_gold >= 0

    # Con ese payload, los hitos de una sola vez tienen que haberse desbloqueado.
    assert "ACH_WELCOME" in desbloqueados
    assert "ACH_FIRST_STEP" in desbloqueados
    assert "ACH_FIRST_GEAR" in desbloqueados


def test_las_recompensas_por_nivel_caen_en_la_configuracion(db: Session, cfg: ServicioConfig) -> None:
    """Sin `reward` explícito manda `achievements.reward.<tier>` de `game_configs`."""
    for fila in _logros(db):
        for nivel in fila.tiers:
            xp, oro, _titulo = motor_logros.recompensa_de_nivel(cfg, dict(nivel))
            assert xp >= 0 and oro >= 0, fila.code
            if not nivel.get("reward"):
                esperado = cfg.obtener_json(f"achievements.reward.{nivel['tier']}")
                assert xp == int(esperado["xp"]), fila.code
                assert oro == int(esperado["gold"]), fila.code


def test_los_logros_de_onboarding_no_pagan_xp(db: Session, cfg: ServicioConfig) -> None:
    """06b §5.4: Bienvenido/a y Primera Aventura dan 0 XP (principio P1)."""
    for codigo in ("ACH_WELCOME", "ACH_FIRST_QUEST"):
        fila = db.execute(sa.select(Achievement).where(Achievement.code == codigo)).scalar_one()
        xp, oro, _ = motor_logros.recompensa_de_nivel(cfg, dict(fila.tiers[0]))
        assert xp == 0, codigo
        assert oro == 20, codigo


# ---------------------------------------------------------------------------
# Misiones
# ---------------------------------------------------------------------------


def _plantillas(db: Session) -> list[MissionTemplate]:
    """Las plantillas sembradas, leídas de la base."""
    codigos = [plantilla.code for plantilla in PLANTILLAS]
    return list(db.execute(sa.select(MissionTemplate).where(MissionTemplate.code.in_(codigos))).scalars())


def test_estan_las_23_plantillas_con_su_horizonte(db: Session) -> None:
    """13 diarias (D01–D13), 4 especiales (S01–S04) y 6 semanales (W01–W06)."""
    filas = _plantillas(db)
    assert len(filas) == 23
    assert Counter(fila.scope for fila in filas) == {
        MissionScope.DAILY: 13,
        MissionScope.SPECIAL: 4,
        MissionScope.WEEKLY: 6,
    }
    assert {fila.code for fila in filas if fila.scope is MissionScope.DAILY} == {
        f"D{n:02d}" for n in range(1, 14)
    }


def test_las_semanales_nacen_desactivadas(db: Session, cfg: ServicioConfig) -> None:
    """El MVP valida el retorno diario: `missions.weekly.enabled = false` (§5.7)."""
    assert cfg.obtener_bool("missions.weekly.enabled") is False
    for fila in _plantillas(db):
        if fila.scope is MissionScope.WEEKLY:
            assert fila.is_active is False, fila.code
    activas = [fila for fila in _plantillas(db) if fila.is_active]
    assert {fila.code for fila in activas if fila.scope is MissionScope.SPECIAL} == {
        "S01",
        "S02",
        "S03",
    }


def test_las_metricas_referencian_eventos_educativos_del_contrato(db: Session) -> None:
    """06b §4.5: toda plantilla mide un evento educativo o `DAILY_GOAL_MET`."""
    nombres = {evento.value for evento in EventType}
    tipos = {metrica.value for metrica in MissionMetricType}
    for fila in _plantillas(db):
        metrica = dict(fila.metric)
        assert str(metrica["type"]) in tipos, fila.code
        assert str(metrica["event"]) in nombres, fila.code


def test_los_titulos_se_interpolan_sin_dejar_marcadores(db: Session) -> None:
    """Un `{marcador}` sin parámetro llegaría crudo a la pantalla del usuario."""
    for fila in _plantillas(db):
        for tier in (MissionTier.EASY, MissionTier.MEDIUM, MissionTier.HARD, None):
            parametros = motor_misiones.resolver_parametros(fila, tier)
            titulo = motor_misiones.titulo_interpolado(fila, parametros)
            assert "{" not in titulo and "}" not in titulo, f"{fila.code} / {tier}"
            assert motor_misiones.objetivo_de_parametros(parametros) >= 1, fila.code


def test_las_recompensas_diarias_salen_de_la_configuracion(db: Session, cfg: ServicioConfig) -> None:
    """`daily_default` lee `xp.mission_daily_*` y `gold.mission_daily_*` (§5.7)."""
    for fila in _plantillas(db):
        if fila.scope is not MissionScope.DAILY:
            continue
        for tier in (MissionTier.EASY, MissionTier.MEDIUM, MissionTier.HARD):
            xp, oro = motor_misiones.recompensa_de_plantilla(cfg, fila, tier)
            assert xp == cfg.obtener_int(f"xp.mission_daily_{tier.value}"), fila.code
            assert oro == cfg.obtener_int(f"gold.mission_daily_{tier.value}"), fila.code


def test_las_especiales_llevan_recompensa_propia(db: Session, cfg: ServicioConfig) -> None:
    """06b §4.6 asigna importes propios a las misiones de ruta."""
    for fila in _plantillas(db):
        if fila.scope is not MissionScope.SPECIAL:
            continue
        xp, oro = motor_misiones.recompensa_de_plantilla(cfg, fila, None)
        assert xp > 0 and oro > 0, fila.code


def test_el_selector_diario_es_determinista(db: Session, cfg: ServicioConfig, usuario: User) -> None:
    """Dos lecturas del mismo día devuelven el mismo trío (06b §4.3)."""
    import datetime as dt

    hoy = dt.date(2026, 9, 11)
    primera = motor_misiones.asignar_misiones_diarias(
        db, cfg, usuario_id=usuario.id, fecha_local=hoy, timezone=usuario.timezone
    )
    segunda = motor_misiones.asignar_misiones_diarias(
        db, cfg, usuario_id=usuario.id, fecha_local=hoy, timezone=usuario.timezone
    )
    assert len(primera) == cfg.obtener_int("missions.daily.count")
    # Se comparan como conjunto: la segunda lectura relee las mismas filas, cuyo
    # `created_at` es idéntico dentro de la transacción y no fija un orden estable.
    assert {m.id for m in primera} == {m.id for m in segunda}
    assert all(mision.target >= 1 for mision in primera)
    assert all(mision.reward_xp > 0 for mision in primera)
