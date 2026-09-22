"""Idempotencia de la siembra y conformidad de los catálogos con el contrato.

Lo que se comprueba aquí:

- Sembrar dos veces deja **el mismo número de filas** y no crea ni actualiza nada.
- `game_configs` tiene los 178 parámetros de §5, con su tipo y su `is_public`.
- `level_definitions` reproduce **exactamente** los valores de control de §6.1.
- Los catálogos tienen el tamaño que fija §9: 46 ítems, 32 logros, 23 misiones.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.enums import LevelScope
from app.models.gamification import GameConfig, LevelDefinition
from app.modules.gamification.servicio_config import ServicioConfig
from app.seeds.config_juego import PARAMETROS, por_clave
from app.seeds.ejecutar import Resumen, sembrar
from app.seeds.niveles import CONTROL_GLOBAL, CONTROL_KNOWLEDGE

pytestmark = pytest.mark.db

#: Tablas que llena la siembra, con el número de filas que debe dejar.
TOTALES_ESPERADOS: dict[str, int] = {
    "game_configs": 178,
    "level_definitions": 100,
    "knowledge_areas": 7,
    "territories": 7,
    # 46 del catálogo más los 21 derivados de plantilla: tres moldes
    # («Capa del Estudiante de {short_name}» y compañía) por cada uno de los
    # siete conocimientos canónicos. Antes no se derivaba ninguno, y por eso todo
    # cosmético de conocimiento del juego era inalcanzable.
    "items": 67,
    # 18 del catálogo más las 28 condiciones que viajan con esos derivados.
    "item_requirements": 46,
    "shop_listings": 21,
    "achievements": 32,
    "mission_templates": 23,
    "learning_paths": 1,
    "path_modules": 3,
    "topics": 6,
    "lessons": 6,
    "lesson_blocks": 30,
    "questions": 24,
    "assessments": 3,
    "assessment_questions": 22,
}


def _conteos(db: Session) -> dict[str, int]:
    """Filas actuales de cada tabla de catálogo."""
    return {
        tabla: int(db.execute(sa.text(f"SELECT count(*) FROM {tabla}")).scalar_one())
        for tabla in TOTALES_ESPERADOS
    }


def test_la_siembra_deja_el_catalogo_completo(sembrado: Resumen) -> None:
    """La primera pasada escribe exactamente las filas que fija el contrato §9."""
    for tabla, esperado in TOTALES_ESPERADOS.items():
        assert sembrado.total(tabla) == esperado, tabla


def test_sembrar_dos_veces_no_duplica_ninguna_fila(db: Session) -> None:
    """Ejecutar la siembra otra vez deja el mismo número de filas: es idempotente."""
    antes = _conteos(db)
    segunda = sembrar(db)
    despues = _conteos(db)

    assert despues == antes
    assert despues == TOTALES_ESPERADOS
    assert sum(segunda.creadas.values()) == 0
    assert sum(segunda.actualizadas.values()) == 0


def test_game_configs_tiene_los_178_parametros(db: Session) -> None:
    """Los 178 parámetros de §5 están sembrados, vigentes y con su tipo."""
    assert len(PARAMETROS) == 178
    assert len({parametro.key for parametro in PARAMETROS}) == 178

    vigentes = db.execute(
        sa.select(GameConfig.key, GameConfig.value, GameConfig.value_type, GameConfig.is_public).where(
            GameConfig.valid_to.is_(None)
        )
    ).all()
    por_clave_bd = {fila[0]: fila for fila in vigentes}

    assert set(por_clave_bd) == {parametro.key for parametro in PARAMETROS}
    for parametro in PARAMETROS:
        _, valor, tipo, publico = por_clave_bd[parametro.key]
        assert valor == parametro.value, parametro.key
        assert tipo == parametro.value_type, parametro.key
        assert publico is parametro.is_public, parametro.key


def test_las_reglas_anti_abuso_nunca_son_publicas() -> None:
    """§5: los topes y tiempos mínimos no se exponen en `/config/public`."""
    catalogo = por_clave()
    for clave in (
        "xp.daily_softcap",
        "xp.min_time.lesson",
        "xp.min_time.answer_ms",
        "xp.repeat_multipliers",
        "gold.daily_softcap",
        "mastery.weakness_rules",
        "shop.purchase_rate_limit_per_minute",
    ):
        assert catalogo[clave].is_public is False, clave


def test_la_curva_global_reproduce_los_valores_de_control(db: Session) -> None:
    """Los XP acumulados de §6.1 deben salir clavados de `level_definitions`."""
    filas = {
        fila.level: int(fila.xp_required)
        for fila in db.execute(
            sa.select(LevelDefinition).where(LevelDefinition.scope == LevelScope.GLOBAL)
        ).scalars()
    }
    assert len(filas) == 50
    assert filas[1] == 0
    for nivel, esperado in CONTROL_GLOBAL.items():
        assert filas[nivel] == esperado, f"nivel {nivel}"


def test_la_curva_por_conocimiento_reproduce_los_valores_de_control(db: Session) -> None:
    """La segunda curva usa `knowledge.level.base` y también está materializada."""
    filas = {
        fila.level: int(fila.xp_required)
        for fila in db.execute(
            sa.select(LevelDefinition).where(LevelDefinition.scope == LevelScope.KNOWLEDGE_AREA)
        ).scalars()
    }
    assert len(filas) == 50
    for nivel, esperado in CONTROL_KNOWLEDGE.items():
        assert filas[nivel] == esperado, f"nivel {nivel}"


def test_los_rangos_se_estrenan_donde_dice_la_configuracion(db: Session, cfg: ServicioConfig) -> None:
    """`is_rank_start` marca justo los niveles de `level.rank_titles`."""
    titulos = {int(k) for k in cfg.obtener_json("level.rank_titles")}
    inicios = {
        fila.level
        for fila in db.execute(
            sa.select(LevelDefinition).where(
                LevelDefinition.scope == LevelScope.GLOBAL,
                LevelDefinition.is_rank_start.is_(True),
            )
        ).scalars()
    }
    assert inicios == titulos


def test_el_xp_delta_es_coherente_con_el_acumulado(db: Session) -> None:
    """`xp_delta` es siempre la diferencia con el nivel anterior, y nunca negativo."""
    for scope in (LevelScope.GLOBAL, LevelScope.KNOWLEDGE_AREA):
        filas = list(
            db.execute(
                sa.select(LevelDefinition)
                .where(LevelDefinition.scope == scope)
                .order_by(LevelDefinition.level)
            ).scalars()
        )
        anterior = 0
        for fila in filas:
            assert int(fila.xp_delta) == int(fila.xp_required) - anterior
            assert int(fila.xp_delta) >= 0
            anterior = int(fila.xp_required)


# ---------------------------------------------------------------------------
# Las condiciones de las reglas hablan el idioma de los enums
# ---------------------------------------------------------------------------


def test_la_regla_de_evaluacion_reconoce_los_desenlaces_reales() -> None:
    """Aprobar una evaluación tiene que pagar.

    La condición decía `["PASSED", "EXCELLENT", "PERFECT"]` y `AssessmentOutcome`
    vale `passed`, `passed_distinction` y `passed_perfect`. Ni el caso ni dos de
    los tres nombres casaban, así que la regla nunca se aplicaba: el aprendiz
    aprobaba su primera evaluación, la pantalla le prometía XP y oro, y el motor
    no le daba nada.
    """
    from app.models.enums import AssessmentOutcome
    from app.seeds.reglas_recompensa import REGLAS

    regla = next(r for r in REGLAS if r["code"] == "assessment_passed")
    admitidos = set(regla["condition"]["outcome_in"])
    reales = {o.value for o in AssessmentOutcome if o is not AssessmentOutcome.FAILED}

    assert admitidos == reales, "la condición y el enum tienen que decir lo mismo"
    assert AssessmentOutcome.FAILED.value not in admitidos


def test_las_bonificaciones_de_evaluacion_tienen_regla() -> None:
    """Las claves de bonificación existían y ninguna regla las usaba."""
    from app.seeds.reglas_recompensa import REGLAS

    por_codigo = {r["code"]: r for r in REGLAS}

    assert por_codigo["assessment_distinction"]["xp_config_key"] == "xp.assessment_bonus_90"
    assert por_codigo["assessment_perfect"]["xp_config_key"] == "xp.assessment_bonus_100"
    assert por_codigo["assessment_distinction"]["gold_config_key"] == "gold.assessment_bonus_90"
    assert por_codigo["assessment_perfect"]["gold_config_key"] == "gold.assessment_bonus_100"


def test_toda_condicion_de_regla_usa_valores_que_existen() -> None:
    """Una condición que no casa nunca es una recompensa que no se paga jamás.

    Se comprueban todas, no solo la de evaluación, porque el fallo es del tipo
    que no se ve: la regla existe, el evento llega, y simplemente no pasa nada.
    """
    from app.models.enums import AssessmentOutcome, ItemRarity
    from app.seeds.reglas_recompensa import REGLAS

    vocabularios = {
        "outcome": {o.value for o in AssessmentOutcome},
        "rarity": {r.value for r in ItemRarity},
    }

    for regla in REGLAS:
        for clave, esperado in (regla.get("condition") or {}).items():
            campo = clave.rsplit("_", 1)[0] if clave.endswith(("_in", "_gte", "_gt", "_lte", "_lt")) else clave
            vocabulario = vocabularios.get(campo)
            if vocabulario is None:
                continue
            valores = esperado if isinstance(esperado, list) else [esperado]
            fuera = [v for v in valores if v not in vocabulario]
            assert not fuera, f"{regla['code']}: {clave} usa valores que no existen: {fuera}"
