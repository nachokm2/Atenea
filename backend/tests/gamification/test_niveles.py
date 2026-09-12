"""Curva de niveles y umbrales (CONTRACT.md §6.1).

Los valores de control son los de la tabla del contrato: si la fórmula cambia,
esta prueba lo detecta antes que la app.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.enums import LevelScope
from app.modules.gamification import niveles

#: Valores de control de la curva global (`level.base = 80`).
CONTROL_GLOBAL = {2: 80, 3: 370, 5: 1690, 10: 10060, 15: 26580, 20: 52040, 30: 131940, 40: 253180, 50: 418330}

#: Valores de control de la curva por conocimiento (`knowledge.level.base = 50`).
CONTROL_CONOCIMIENTO = {2: 50, 5: 1060, 10: 6280, 20: 32530, 30: 82460}

pytestmark = pytest.mark.db


def test_redondeo_a_la_decena_medio_hacia_arriba() -> None:
    """`round_to_10` redondea al múltiplo de 10 más cercano, medio hacia arriba."""
    assert niveles.redondear_a_decena(Decimal("15")) == 20
    assert niveles.redondear_a_decena(Decimal("14.9")) == 10
    assert niveles.redondear_a_decena(Decimal("0")) == 0


def test_curva_global_coincide_con_la_tabla_del_contrato(db, cfg) -> None:
    """Los XP acumulados calculados son exactamente los del contrato §6.1."""
    params = niveles.parametros_curva(cfg, LevelScope.GLOBAL)
    assert niveles.xp_requerido_calculado(1, params) == 0
    for nivel, esperado in CONTROL_GLOBAL.items():
        assert niveles.xp_requerido_calculado(nivel, params) == esperado, nivel


def test_curva_de_conocimiento_coincide_con_la_tabla_del_contrato(db, cfg) -> None:
    """La curva por conocimiento usa base 50 y da los valores del contrato."""
    params = niveles.parametros_curva(cfg, LevelScope.KNOWLEDGE_AREA)
    for nivel, esperado in CONTROL_CONOCIMIENTO.items():
        assert niveles.xp_requerido_calculado(nivel, params) == esperado, nivel


def test_nivel_para_xp_usa_level_definitions(db, cfg) -> None:
    """`nivel_para_xp` lee la tabla materializada y respeta los umbrales."""
    assert niveles.nivel_para_xp(db, cfg, 0) == 1
    assert niveles.nivel_para_xp(db, cfg, 79) == 1
    assert niveles.nivel_para_xp(db, cfg, 80) == 2
    assert niveles.nivel_para_xp(db, cfg, 369) == 2
    assert niveles.nivel_para_xp(db, cfg, 370) == 3
    assert niveles.nivel_para_xp(db, cfg, 10_060) == 10
    assert niveles.nivel_para_xp(db, cfg, 999_999) == 50


def test_xp_para_nivel_es_la_inversa(db, cfg) -> None:
    """`xp_para_nivel` devuelve el umbral materializado de cada nivel."""
    for nivel, esperado in CONTROL_GLOBAL.items():
        assert niveles.xp_para_nivel(db, cfg, nivel) == esperado


def test_estado_nivel_calcula_progreso_y_rango(db, cfg) -> None:
    """El estado de nivel trae rango, XP restante y porcentaje de avance."""
    estado = niveles.estado_nivel(db, cfg, 1_690)
    assert estado.nivel == 5
    assert estado.rank_title == "Iniciado/a"
    assert estado.is_rank_start is True
    assert estado.progress_pct == Decimal("0.00")
    assert estado.xp_to_next == niveles.xp_para_nivel(db, cfg, 6) - 1_690

    medio = niveles.estado_nivel(db, cfg, 100)
    assert medio.nivel == 2
    assert medio.rank_title == "Aprendiz"
    assert Decimal("0") < medio.progress_pct < Decimal("100")


def test_titulo_de_conocimiento_exige_dominio_para_maestro(db, cfg) -> None:
    """"Maestro/a de" exige `knowledge.master_title_requires_mastery` (§6.1)."""
    assert niveles.titulo_de_conocimiento(30, 85, cfg) == "Maestro/a de"
    assert niveles.titulo_de_conocimiento(30, 40, cfg) == "Veterano/a de"
    assert niveles.titulo_de_conocimiento(10, 10, cfg) == "Competente en"
