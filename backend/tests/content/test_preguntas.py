"""Vista pública de una pregunta y muestreo de bancos (§7.6, §7.7, §8.7).

El muestreo es lógica pura sobre una lista de preguntas: no necesita la base.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.content import Question
from app.models.enums import DifficultyLevel, QuestionType
from app.modules.content import preguntas


def _pregunta(indice: int) -> Question:
    """Pregunta en memoria con identidad estable para el muestreo."""
    fila = Question(
        topic_id=uuid.uuid4(),
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=DifficultyLevel.MEDIUM,
        stem=f"Pregunta {indice}",
        body={"options": [{"id": "a"}, {"id": "b"}], "rubric": ["no debe salir"]},
        answer_key={"correct_option_id": "a"},
        explanation="Explicación",
        estimated_seconds=45,
    )
    fila.id = uuid.uuid4()
    return fila


# ---------------------------------------------------------------------------
# Vista pública
# ---------------------------------------------------------------------------


def test_vista_publica_no_incluye_la_clave_ni_la_explicacion():
    """§8.7: `answer_key` nunca se serializa; la explicación llega tras responder."""
    datos = preguntas.vista_publica(_pregunta(1), position=3)

    assert "answer_key" not in datos
    assert "explanation" not in datos
    assert datos["position"] == 3
    assert datos["stem"] == "Pregunta 1"


def test_vista_publica_recorta_las_claves_del_cuerpo_que_revelan_la_solucion():
    """La rúbrica de una abierta no viaja con el enunciado."""
    datos = preguntas.vista_publica(_pregunta(1))

    assert "options" in datos["body"]
    assert "rubric" not in datos["body"]


# ---------------------------------------------------------------------------
# Muestreo del banco de la evaluación
# ---------------------------------------------------------------------------


def test_el_muestreo_prefiere_preguntas_nuevas():
    """Si el banco da para renovar, el intento no repite ninguna pregunta."""
    banco = [_pregunta(i) for i in range(20)]
    previas = [q.id for q in banco[:10]]

    seleccion = preguntas.muestrear_banco(
        banco, cantidad=10, previas=previas, max_overlap=0.30, semilla="s1"
    )

    assert len(seleccion) == 10
    assert preguntas.solapamiento([q.id for q in seleccion], previas) == 0.0


def test_el_muestreo_respeta_el_tope_de_solapamiento():
    """§7.7: con banco escaso se repite como mucho el 30 % del intento anterior."""
    banco = [_pregunta(i) for i in range(12)]
    previas = [q.id for q in banco[:10]]

    seleccion = preguntas.muestrear_banco(
        banco, cantidad=10, previas=previas, max_overlap=0.30, semilla="s2"
    )

    ids = [q.id for q in seleccion]
    repetidas = len([q for q in ids if q in set(previas)])
    # El tope del contrato es sobre el tamaño **pedido** del examen: con un banco
    # escaso el examen sale más corto antes que saltarse el límite de repeticiones.
    assert repetidas <= preguntas.maximo_repetidas(10, 0.30)
    assert len(ids) == len(set(ids)), "el muestreo nunca repite una pregunta dentro del intento"


def test_el_muestreo_es_determinista_para_la_misma_semilla():
    """La misma semilla produce el mismo conjunto: el reintento idempotente lo exige."""
    banco = [_pregunta(i) for i in range(20)]

    primero = preguntas.muestrear_banco(
        banco, cantidad=8, previas=[], max_overlap=0.30, semilla="misma"
    )
    segundo = preguntas.muestrear_banco(
        banco, cantidad=8, previas=[], max_overlap=0.30, semilla="misma"
    )

    assert [q.id for q in primero] == [q.id for q in segundo]


def test_un_banco_mas_pequeno_que_el_examen_devuelve_lo_que_hay():
    """Negar el intento sería peor que servir un examen corto."""
    banco = [_pregunta(i) for i in range(3)]

    seleccion = preguntas.muestrear_banco(
        banco, cantidad=10, previas=[], max_overlap=0.30, semilla="s3"
    )

    assert len(seleccion) == 3


@pytest.mark.parametrize(("cantidad", "esperado"), [(10, 3), (4, 1), (0, 0)])
def test_maximo_repetidas_es_el_30_por_ciento(cantidad, esperado):
    """`maximo_repetidas` traduce el 30 % del contrato a un número entero de preguntas."""
    assert preguntas.maximo_repetidas(cantidad, 0.30) == esperado


def test_tamano_de_repaso_se_ajusta_al_pool(cfg_falso):
    """`mastery.review.questions` fija el máximo; un tema corto da un repaso corto."""
    assert preguntas.tamano_de_repaso(cfg_falso, 20) == 8
    assert preguntas.tamano_de_repaso(cfg_falso, 2) == 2
    assert preguntas.tamano_de_repaso(cfg_falso, 0) == 0
