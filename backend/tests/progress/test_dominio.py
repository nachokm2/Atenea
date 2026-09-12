"""Pruebas de la fórmula de dominio (CONTRACT.md §6.4–§6.8). Lógica pura, sin base de datos.

Cada prueba comprueba una promesa del contrato:

* el dominio sube con aciertos difíciles y baja con fallos;
* acumular tiempo **no** mueve el dominio;
* el decaimiento erosiona el dominio y el repaso lo recupera;
* reintentar pesa menos, tanto en la evidencia como en la evaluación;
* un tema solo se marca dominado con umbral **y** evaluación aprobada.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.enums import ActivityContext, DifficultyLevel, KnowledgeAreaStatus
from app.modules.progress.dominio import (
    ModuloPonderado,
    TemaPonderado,
    agregar_dominio_area,
    calcular_dominio_modulo,
    calcular_dominio_tema,
    cobertura,
    es_area_dominada,
    es_tema_debil,
    es_tema_dominado,
    estado_dominio,
    factor_cobertura,
    factor_decaimiento,
    media_vida_decaimiento,
    peso_contexto,
    peso_de_acierto,
    peso_dificultad,
    peso_recencia,
    peso_reintento,
    precision_ponderada,
    promedio_ponderado_temas,
    puntaje_efectivo_evaluacion,
    seleccionar_evidencias,
)

DOS_LECCIONES = 2


def dominio(evidencias, cfg, ahora, *, completadas=1, totales=DOS_LECCIONES, s=0):
    """Atajo: `M_t` con la cobertura y la estabilidad indicadas."""
    return calcular_dominio_tema(
        evidencias,
        lecciones_completadas=completadas,
        lecciones_totales=totales,
        stability_s=s,
        cfg=cfg,
        ahora=ahora,
    )


# ---------------------------------------------------------------------------
# Pesos
# ---------------------------------------------------------------------------


def test_los_pesos_salen_de_la_configuracion(cfg):
    assert peso_dificultad(DifficultyLevel.EASY, cfg) == pytest.approx(1.0)
    assert peso_dificultad(DifficultyLevel.MEDIUM, cfg) == pytest.approx(1.5)
    assert peso_dificultad(DifficultyLevel.HARD, cfg) == pytest.approx(2.0)
    assert peso_contexto(ActivityContext.LESSON, cfg) == pytest.approx(1.0)
    assert peso_contexto(ActivityContext.CHALLENGE, cfg) == pytest.approx(1.5)
    assert peso_contexto(ActivityContext.ASSESSMENT, cfg) == pytest.approx(2.0)


def test_peso_de_recencia_es_una_media_vida_de_treinta_dias(cfg):
    assert peso_recencia(0, cfg) == pytest.approx(1.0)
    assert peso_recencia(30, cfg) == pytest.approx(0.5)
    assert peso_recencia(60, cfg) == pytest.approx(0.25)


def test_credito_de_acierto_por_numero_de_intento(cfg):
    assert peso_de_acierto(True, 1, cfg) == pytest.approx(1.0)
    assert peso_de_acierto(True, 2, cfg) == pytest.approx(0.5)
    assert peso_de_acierto(True, 3, cfg) == pytest.approx(0.0)
    assert peso_de_acierto(False, 1, cfg) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# El dominio sube con aciertos difíciles y baja con fallos
# ---------------------------------------------------------------------------


def test_el_dominio_sube_con_respuestas_correctas_dificiles(cfg, ahora, evidencia):
    sin_evidencia = dominio([], cfg, ahora, completadas=0)
    aciertos = [
        evidencia(dificultad=DifficultyLevel.HARD, acierto=1.0, base=ahora) for _ in range(5)
    ]
    con_aciertos = dominio(aciertos, cfg, ahora, completadas=0)

    # Sin evidencias manda el prior bayesiano: P_t = p0 = 50 %.
    assert sin_evidencia.practice_score == pytest.approx(50.0)
    assert con_aciertos.practice_score > sin_evidencia.practice_score
    assert con_aciertos.mastery > sin_evidencia.mastery
    # (10 + 3·0.5) / (10 + 3) = 0.8846…
    assert con_aciertos.practice_score == pytest.approx(88.46, abs=0.01)


def test_el_dominio_baja_con_fallos(cfg, ahora, evidencia):
    aciertos = [
        evidencia(dificultad=DifficultyLevel.HARD, acierto=1.0, base=ahora) for _ in range(5)
    ]
    fallos = [
        evidencia(dificultad=DifficultyLevel.HARD, acierto=0.0, base=ahora) for _ in range(5)
    ]
    antes = dominio(aciertos, cfg, ahora)
    despues = dominio([*aciertos, *fallos], cfg, ahora)

    assert despues.mastery < antes.mastery
    assert despues.practice_score == pytest.approx(50.0, abs=0.01)


def test_una_pregunta_dificil_vale_mas_que_una_facil(cfg, ahora, evidencia):
    dificiles = [
        evidencia(dificultad=DifficultyLevel.HARD, acierto=1.0, base=ahora) for _ in range(4)
    ]
    faciles = [
        evidencia(dificultad=DifficultyLevel.EASY, acierto=1.0, base=ahora) for _ in range(4)
    ]
    assert precision_ponderada(dificiles, cfg) > precision_ponderada(faciles, cfg)


def test_la_evidencia_de_evaluacion_pesa_el_doble_que_la_de_leccion(cfg, ahora, evidencia):
    en_evaluacion = [
        evidencia(contexto=ActivityContext.ASSESSMENT, acierto=1.0, base=ahora) for _ in range(3)
    ]
    en_leccion = [
        evidencia(contexto=ActivityContext.LESSON, acierto=1.0, base=ahora) for _ in range(3)
    ]
    assert precision_ponderada(en_evaluacion, cfg) > precision_ponderada(en_leccion, cfg)


# ---------------------------------------------------------------------------
# El tiempo no otorga dominio
# ---------------------------------------------------------------------------


def test_acumular_horas_sin_acertar_no_sube_el_dominio(cfg, ahora, evidencia):
    """El tiempo no es un argumento de la fórmula: solo cuentan las evidencias.

    Abrir muchas lecciones y no responder nada deja el dominio en el prior; y si se
    responde mal, baja incluso con la cobertura al 100 %.
    """
    sin_responder = dominio([], cfg, ahora, completadas=DOS_LECCIONES, totales=DOS_LECCIONES)
    fallos = [evidencia(acierto=0.0, base=ahora) for _ in range(6)]
    respondiendo_mal = dominio(
        fallos, cfg, ahora, completadas=DOS_LECCIONES, totales=DOS_LECCIONES
    )

    # Cobertura completa: g(C) = 1.0, así que M_t = P_t.
    assert sin_responder.coverage == pytest.approx(100.0)
    assert sin_responder.mastery == pytest.approx(50.0)
    assert respondiendo_mal.mastery < sin_responder.mastery
    assert not es_tema_dominado(sin_responder.mastery, evaluacion_aprobada=True, cfg=cfg)


def test_la_cobertura_solo_modula_entre_el_piso_y_el_uno(cfg):
    assert cobertura(0, 4) == pytest.approx(0.0)
    assert cobertura(2, 4) == pytest.approx(50.0)
    assert cobertura(9, 4) == pytest.approx(100.0)
    assert factor_cobertura(0.0, cfg) == pytest.approx(0.6)
    assert factor_cobertura(50.0, cfg) == pytest.approx(0.8)
    assert factor_cobertura(100.0, cfg) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Decaimiento y recuperación por repaso
# ---------------------------------------------------------------------------


def test_dentro_de_la_gracia_no_hay_decaimiento(cfg):
    assert factor_decaimiento(0, 0, cfg) == pytest.approx(1.0)
    assert factor_decaimiento(7, 0, cfg) == pytest.approx(1.0)
    assert factor_decaimiento(8, 0, cfg) < 1.0


def test_el_decaimiento_reduce_el_dominio_con_el_paso_del_tiempo(cfg, ahora, evidencia):
    aciertos = [
        evidencia(dificultad=DifficultyLevel.HARD, acierto=1.0, base=ahora) for _ in range(6)
    ]
    hoy = dominio(aciertos, cfg, ahora)
    en_un_mes = dominio(aciertos, cfg, ahora + timedelta(days=40))
    en_un_trimestre = dominio(aciertos, cfg, ahora + timedelta(days=120))

    assert hoy.mastery > en_un_mes.mastery > en_un_trimestre.mastery
    # El dominio bruto no cambia: lo que cae es el factor de olvido.
    assert en_un_mes.mastery_raw == pytest.approx(hoy.mastery_raw)
    assert en_un_trimestre.factor_decaimiento >= cfg.decaimiento_piso


def test_el_repaso_recupera_el_dominio(cfg, ahora, evidencia):
    aciertos = [
        evidencia(dificultad=DifficultyLevel.HARD, acierto=1.0, base=ahora) for _ in range(6)
    ]
    olvidado = dominio(aciertos, cfg, ahora + timedelta(days=60))

    # Un repaso acertado hoy vuelve a poner Δ en cero.
    repaso = evidencia(
        dificultad=DifficultyLevel.HARD,
        contexto=ActivityContext.REVIEW,
        acierto=1.0,
        base=ahora + timedelta(days=60),
    )
    repasado = dominio([*aciertos, repaso], cfg, ahora + timedelta(days=60))

    assert repasado.mastery > olvidado.mastery
    assert repasado.factor_decaimiento == pytest.approx(1.0)


def test_la_estabilidad_alarga_la_media_vida_del_olvido(cfg, ahora, evidencia):
    aciertos = [
        evidencia(dificultad=DifficultyLevel.HARD, acierto=1.0, base=ahora) for _ in range(6)
    ]
    sin_repasos = dominio(aciertos, cfg, ahora + timedelta(days=60), s=0)
    con_repasos = dominio(aciertos, cfg, ahora + timedelta(days=60), s=2)

    assert media_vida_decaimiento(0, cfg) == pytest.approx(60.0)
    assert media_vida_decaimiento(1, cfg) == pytest.approx(90.0)
    assert media_vida_decaimiento(2, cfg) == pytest.approx(135.0)
    assert media_vida_decaimiento(30, cfg) == pytest.approx(365.0)  # tope
    assert con_repasos.mastery > sin_repasos.mastery


def test_control_de_la_curva_de_olvido_del_contrato(cfg):
    """§6.5: un tema al 90 % cruza el 80 % a los 36 / 50 / 71 días con s = 0 / 1 / 2."""
    for dias_cruce, estabilidad in ((36, 0), (50, 1), (71, 2)):
        antes = 90.0 * factor_decaimiento(dias_cruce - 1, estabilidad, cfg)
        despues = 90.0 * factor_decaimiento(dias_cruce, estabilidad, cfg)
        assert antes >= 80.0 > despues


# ---------------------------------------------------------------------------
# Protección contra repetir hasta aprobar
# ---------------------------------------------------------------------------


def test_reintentar_una_pregunta_pesa_menos(cfg, ahora, evidencia):
    assert peso_reintento(1, cfg) == pytest.approx(1.0)
    assert peso_reintento(2, cfg) == pytest.approx(0.6)
    assert peso_reintento(3, cfg) == pytest.approx(0.3)
    assert peso_reintento(9, cfg) == pytest.approx(0.3)

    base = [evidencia(acierto=1.0, base=ahora) for _ in range(4)]
    fallo_al_primer_intento = precision_ponderada(
        [*base, evidencia(acierto=0.0, intento=1, base=ahora)], cfg
    )
    fallo_al_tercer_intento = precision_ponderada(
        [*base, evidencia(acierto=0.0, intento=3, base=ahora)], cfg
    )
    assert fallo_al_tercer_intento > fallo_al_primer_intento


def test_reintentar_la_evaluacion_penaliza_el_puntaje_efectivo(cfg):
    assert puntaje_efectivo_evaluacion([], cfg) == pytest.approx(0.0)
    assert puntaje_efectivo_evaluacion([(1, 70.0)], cfg) == pytest.approx(70.0)
    assert puntaje_efectivo_evaluacion([(2, 70.0)], cfg) == pytest.approx(65.0)
    assert puntaje_efectivo_evaluacion([(3, 70.0)], cfg) == pytest.approx(60.0)
    # La penalización tiene tope (max = 0.15 → 15 puntos).
    assert puntaje_efectivo_evaluacion([(9, 90.0)], cfg) == pytest.approx(75.0)
    # Se queda con el mejor intento **ya penalizado**.
    assert puntaje_efectivo_evaluacion([(1, 60.0), (2, 90.0)], cfg) == pytest.approx(85.0)


def test_repetir_la_evaluacion_hasta_aprobar_no_iguala_al_que_aprueba_a_la_primera(cfg):
    temas = [TemaPonderado(topic_id=None, mastery=90.0, lecciones=2)]
    a_la_primera = calcular_dominio_modulo(temas, [(1, 90.0)], cfg)
    tras_cuatro_intentos = calcular_dominio_modulo(
        temas, [(1, 40.0), (2, 55.0), (3, 70.0), (4, 90.0)], cfg
    )
    assert tras_cuatro_intentos.mastery < a_la_primera.mastery
    assert tras_cuatro_intentos.puntaje_efectivo == pytest.approx(75.0)


# ---------------------------------------------------------------------------
# Módulo y conocimiento
# ---------------------------------------------------------------------------


def test_es_imposible_dominar_un_modulo_sin_evaluacion(cfg):
    temas = [TemaPonderado(topic_id=None, mastery=100.0, lecciones=3)]
    sin_evaluacion = calcular_dominio_modulo(temas, [], cfg)
    assert sin_evaluacion.mastery == pytest.approx(70.0)
    assert sin_evaluacion.mastery <= 100.0 * cfg.peso_modulo_temas
    assert not sin_evaluacion.dominado


def test_modulo_dominado_exige_umbral_y_un_intento_aprobado(cfg):
    temas = [TemaPonderado(topic_id=None, mastery=95.0, lecciones=3)]
    aprobado = calcular_dominio_modulo(temas, [(1, 90.0)], cfg)
    assert aprobado.mastery == pytest.approx(0.70 * 95.0 + 0.30 * 90.0)
    assert aprobado.dominado

    reprobado = calcular_dominio_modulo(temas, [(1, 60.0)], cfg)
    assert not reprobado.aprobado
    assert not reprobado.dominado


def test_el_promedio_de_temas_pondera_por_lecciones(cfg):
    temas = [
        TemaPonderado(topic_id=None, mastery=100.0, lecciones=3),
        TemaPonderado(topic_id=None, mastery=50.0, lecciones=1),
    ]
    assert promedio_ponderado_temas(temas) == pytest.approx(87.5)


def test_el_dominio_del_conocimiento_pondera_por_lecciones_del_modulo(cfg):
    modulos = [
        ModuloPonderado(module_id=None, mastery=90.0, lecciones=6),
        ModuloPonderado(module_id=None, mastery=0.0, lecciones=4),  # módulo no iniciado
    ]
    assert agregar_dominio_area(modulos) == pytest.approx(54.0)
    assert agregar_dominio_area([]) == pytest.approx(0.0)


def test_el_conocimiento_dominado_exige_una_ruta_completada(cfg):
    assert not es_area_dominada(85.0, tiene_ruta_completada=False, cfg=cfg)
    assert es_area_dominada(85.0, tiene_ruta_completada=True, cfg=cfg)
    assert not es_area_dominada(79.9, tiene_ruta_completada=True, cfg=cfg)


# ---------------------------------------------------------------------------
# Estados y banderas
# ---------------------------------------------------------------------------


def test_un_tema_se_marca_dominado_solo_con_umbral_y_evaluacion(cfg):
    assert es_tema_dominado(85.0, evaluacion_aprobada=True, cfg=cfg)
    assert not es_tema_dominado(85.0, evaluacion_aprobada=False, cfg=cfg)
    assert not es_tema_dominado(79.99, evaluacion_aprobada=True, cfg=cfg)


def test_estados_de_dominio_del_contrato(cfg):
    assert (
        estado_dominio(
            0.0,
            ever_mastered=False,
            evidencias=0,
            lecciones_completadas=0,
            requisito_cumplido=False,
            cfg=cfg,
        )
        == KnowledgeAreaStatus.NO_EVIDENCE
    )
    assert (
        estado_dominio(
            45.0,
            ever_mastered=False,
            evidencias=5,
            lecciones_completadas=1,
            requisito_cumplido=False,
            cfg=cfg,
        )
        == KnowledgeAreaStatus.IN_PROGRESS
    )
    assert (
        estado_dominio(
            88.0,
            ever_mastered=False,
            evidencias=9,
            lecciones_completadas=2,
            requisito_cumplido=True,
            cfg=cfg,
        )
        == KnowledgeAreaStatus.MASTERED
    )
    assert (
        estado_dominio(
            75.0,
            ever_mastered=True,
            evidencias=9,
            lecciones_completadas=2,
            requisito_cumplido=True,
            cfg=cfg,
        )
        == KnowledgeAreaStatus.AT_RISK
    )
    assert (
        estado_dominio(
            60.0,
            ever_mastered=True,
            evidencias=9,
            lecciones_completadas=2,
            requisito_cumplido=True,
            cfg=cfg,
        )
        == KnowledgeAreaStatus.WEAKENED
    )


def test_bandera_de_tema_debil(cfg):
    assert not es_tema_debil(40.0, 4, cfg)  # faltan evidencias
    assert es_tema_debil(40.0, 5, cfg)
    assert not es_tema_debil(60.0, 20, cfg)


def test_la_ventana_de_evidencias_toma_la_que_da_mas_cobertura(cfg, ahora, evidencia):
    # 45 evidencias en los últimos 10 días: la ventana de 180 días da más cobertura
    # que el tope de 40 por cantidad, así que entran las 45.
    recientes = [evidencia(dias_atras=i / 5, base=ahora) for i in range(45)]
    assert len(seleccionar_evidencias(recientes, cfg)) == 45

    # 60 evidencias repartidas cada 10 días: en 180 días solo caben 19, así que manda
    # el tope de 40 evidencias más recientes.
    dispersas = [evidencia(dias_atras=i * 10, base=ahora) for i in range(60)]
    assert len(seleccionar_evidencias(dispersas, cfg)) == cfg.ventana_max_items


def test_las_evidencias_que_no_cuentan_para_dominio_se_descartan(cfg, ahora, evidencia):
    validas = [evidencia(acierto=1.0, base=ahora) for _ in range(3)]
    descartada = evidencia(acierto=0.0, base=ahora)
    descartada = type(descartada)(
        answered_at=descartada.answered_at,
        difficulty=descartada.difficulty,
        context=descartada.context,
        attempt_no=descartada.attempt_no,
        correctness_weight=descartada.correctness_weight,
        counts_for_mastery=False,
    )
    seleccionadas = seleccionar_evidencias([*validas, descartada], cfg)
    assert len(seleccionadas) == len(validas)
    assert all(e.counts_for_mastery for e in seleccionadas)
