"""La Ruta del Reino de SQL: estructura, calidad de las claves y corrección real.

Comprobación exigida por el contrato §9: **cada pregunta tiene una clave de respuesta
bien formada según su tipo**. Aquí no se comprueba «que exista un JSON», se comprueba
que la clave funciona:

- Pasa el validador canónico `SalidaPregunta.clave_completa()` de
  `app.modules.ai.esquemas_salida`, que es el mismo que filtra lo que genera la IA.
- Los cinco tipos deterministas puntúan **100** cuando se responde lo que dice la
  clave, usando los correctores reales de `app.modules.content.correccion`.
- Los seis ejercicios `sql_exercise` se ejecutan de verdad en el sandbox DuckDB de
  `app.modules.ai.sandbox_sql`: el esquema, los datos de ejemplo y la consulta de
  referencia tienen que correr y dar un veredicto correcto.

Además se comprueba que la ruta se puede terminar **sin IA**: ninguna evaluación de
módulo incluye preguntas abiertas, que son las únicas que requieren al juez de Claude.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.content import (
    Assessment,
    AssessmentQuestion,
    LearningPath,
    Lesson,
    LessonBlock,
    PathModule,
    Question,
    Topic,
)
from app.models.enums import (
    ContentStatus,
    LessonBlockType,
    PathOrigin,
    PathStatus,
    QuestionType,
)
from app.modules.ai import sandbox_sql
from app.modules.ai.esquemas_salida import SalidaPregunta
from app.modules.content import correccion
from app.modules.gamification.servicio_config import ServicioConfig
from app.seeds.ruta_semilla_sql import RUTA, banco_de_evaluacion, todas_las_preguntas

pytestmark = pytest.mark.db


def _ruta(db: Session) -> LearningPath:
    """La Ruta del Reino de SQL, leída de la base."""
    return db.execute(sa.select(LearningPath).where(LearningPath.title == RUTA.title)).scalar_one()


def _preguntas(db: Session, ruta: LearningPath) -> list[Question]:
    """Las 24 preguntas de la ruta, en orden estable."""
    return list(
        db.execute(
            sa.select(Question)
            .join(Topic, Topic.id == Question.topic_id)
            .join(PathModule, PathModule.id == Topic.module_id)
            .where(PathModule.learning_path_id == ruta.id)
            .order_by(PathModule.position, Topic.position, Question.created_at, Question.stem)
        ).scalars()
    )


def _respuesta_perfecta(pregunta: Question) -> dict[str, Any]:
    """Construye la respuesta que la clave declara como correcta."""
    clave = dict(pregunta.answer_key)
    match pregunta.question_type:
        case QuestionType.MULTIPLE_CHOICE:
            return {"option_id": clave["correct_option"]}
        case QuestionType.TRUE_FALSE:
            return {"value": clave["correct"]}
        case QuestionType.FILL_BLANK:
            return {"blanks": [hueco["accepted"][0] for hueco in clave["blanks"]]}
        case QuestionType.MATCHING:
            return {"pairs": clave["pairs"]}
        case QuestionType.ORDERING:
            return {"order": clave["order"]}
        case _:  # pragma: no cover - los otros tipos no se corrigen así
            return {}


# ---------------------------------------------------------------------------
# Estructura
# ---------------------------------------------------------------------------


def test_la_ruta_es_del_reino_y_esta_publicada(db: Session) -> None:
    """§5.9 D17: sin dueño, de origen `seed`, pública y activa."""
    ruta = _ruta(db)
    assert ruta.user_id is None
    assert ruta.origin is PathOrigin.SEED
    assert ruta.status is PathStatus.ACTIVE
    assert ruta.is_public is True
    assert ruta.module_count == 3
    assert ruta.summary and ruta.goal_text


def test_la_estructura_tiene_3_modulos_6_temas_y_6_lecciones(db: Session) -> None:
    """La jerarquía completa del contrato §1.1, con una evaluación por módulo."""
    ruta = _ruta(db)
    modulos = list(
        db.execute(
            sa.select(PathModule).where(PathModule.learning_path_id == ruta.id).order_by(PathModule.position)
        ).scalars()
    )
    assert [modulo.position for modulo in modulos] == [1, 2, 3]

    temas_totales = 0
    lecciones_totales = 0
    for modulo in modulos:
        temas = list(
            db.execute(
                sa.select(Topic).where(Topic.module_id == modulo.id).order_by(Topic.position)
            ).scalars()
        )
        assert [tema.position for tema in temas] == [1, 2]
        assert modulo.flavor_name, modulo.title
        temas_totales += len(temas)
        for tema in temas:
            lecciones = list(db.execute(sa.select(Lesson).where(Lesson.topic_id == tema.id)).scalars())
            assert len(lecciones) == 1
            assert tema.learning_objectives
            lecciones_totales += 1
        evaluacion = db.execute(sa.select(Assessment).where(Assessment.module_id == modulo.id)).scalar_one()
        assert evaluacion.content_status is ContentStatus.READY

    assert temas_totales == 6
    assert lecciones_totales == 6


def test_cada_leccion_tiene_explicacion_ejemplo_y_ejercicio(db: Session) -> None:
    """Contrato §9: explicación, ejemplo y ejercicio en las seis lecciones."""
    ruta = _ruta(db)
    lecciones = list(
        db.execute(
            sa.select(Lesson)
            .join(Topic, Topic.id == Lesson.topic_id)
            .join(PathModule, PathModule.id == Topic.module_id)
            .where(PathModule.learning_path_id == ruta.id)
        ).scalars()
    )
    assert len(lecciones) == 6

    for leccion in lecciones:
        bloques = list(
            db.execute(
                sa.select(LessonBlock)
                .where(LessonBlock.lesson_id == leccion.id)
                .order_by(LessonBlock.position)
            ).scalars()
        )
        tipos = {bloque.block_type for bloque in bloques}
        assert LessonBlockType.EXPLANATION in tipos, leccion.title
        assert LessonBlockType.CODE_EXAMPLE in tipos, leccion.title
        assert LessonBlockType.EXAMPLE in tipos, leccion.title
        assert LessonBlockType.SUMMARY in tipos, leccion.title
        assert [bloque.position for bloque in bloques] == list(range(1, len(bloques) + 1))
        assert leccion.block_count == len(bloques)

        intercaladas = [bloque for bloque in bloques if bloque.block_type is LessonBlockType.INLINE_QUESTION]
        assert len(intercaladas) == 1, leccion.title
        referencia = intercaladas[0].payload.get("question_id")
        assert referencia
        assert db.get(Question, referencia) is not None


def test_la_ruta_dura_lo_que_dice_la_configuracion(db: Session, cfg: ServicioConfig) -> None:
    """Cada lección cae dentro de `content.lesson.target_minutes` (§5.8)."""
    limites = cfg.obtener_json("content.lesson.target_minutes")
    ruta = _ruta(db)
    lecciones = list(
        db.execute(
            sa.select(Lesson)
            .join(Topic, Topic.id == Lesson.topic_id)
            .join(PathModule, PathModule.id == Topic.module_id)
            .where(PathModule.learning_path_id == ruta.id)
        ).scalars()
    )
    for leccion in lecciones:
        minutos = leccion.estimated_seconds / 60
        assert int(limites["min"]) <= minutos <= int(limites["max"]), leccion.title


# ---------------------------------------------------------------------------
# Preguntas y claves de respuesta
# ---------------------------------------------------------------------------


def test_hay_24_preguntas_de_los_siete_tipos_del_mvp(db: Session, cfg: ServicioConfig) -> None:
    """Todos los tipos de `content.mvp_question_types` están representados (D13)."""
    ruta = _ruta(db)
    preguntas = _preguntas(db, ruta)
    assert len(preguntas) == 24
    assert len(todas_las_preguntas()) == 24

    admitidos = {str(t) for t in cfg.obtener_lista("content.mvp_question_types")}
    presentes = Counter(pregunta.question_type.value for pregunta in preguntas)
    assert set(presentes) <= admitidos
    assert set(presentes) == admitidos, "la ruta semilla debe ejercitar los siete tipos"


def test_cada_pregunta_tiene_una_clave_bien_formada(db: Session) -> None:
    """El validador canónico de contenido acepta las 24 claves de respuesta."""
    ruta = _ruta(db)
    for pregunta in _preguntas(db, ruta):
        salida = SalidaPregunta(
            question_type=pregunta.question_type,
            difficulty=pregunta.difficulty,
            stem=pregunta.stem,
            body=dict(pregunta.body),
            answer_key=dict(pregunta.answer_key),
            explanation=pregunta.explanation or "",
            learning_objective=pregunta.learning_objective or "",
            estimated_seconds=pregunta.estimated_seconds,
        )
        assert salida.clave_completa() is True, pregunta.stem[:60]


def test_cada_pregunta_explica_la_respuesta(db: Session) -> None:
    """La explicación es lo único que se le sirve al usuario tras responder (§7.6)."""
    ruta = _ruta(db)
    for pregunta in _preguntas(db, ruta):
        assert pregunta.explanation, pregunta.stem[:60]
        assert len(pregunta.explanation) > 80, pregunta.stem[:60]
        assert pregunta.learning_objective, pregunta.stem[:60]


def test_los_correctores_deterministas_dan_100_a_la_clave(db: Session) -> None:
    """Responder lo que dice la clave puntúa 100 en los cinco tipos sin IA."""
    ruta = _ruta(db)
    comprobadas = 0
    for pregunta in _preguntas(db, ruta):
        corrector = correccion.CORRECTORES.get(pregunta.question_type)
        if corrector is None:
            continue
        puntaje, _esperada = corrector(dict(pregunta.answer_key), _respuesta_perfecta(pregunta))
        assert puntaje == 100.0, pregunta.stem[:60]
        comprobadas += 1
    assert comprobadas == 16  # 6 opción múltiple + 4 V/F + 2 huecos + 2 parejas + 2 orden


def test_una_respuesta_equivocada_no_puntua(db: Session) -> None:
    """Las claves discriminan: una opción distinta de la correcta da 0."""
    ruta = _ruta(db)
    for pregunta in _preguntas(db, ruta):
        if pregunta.question_type is not QuestionType.MULTIPLE_CHOICE:
            continue
        correcta = str(dict(pregunta.answer_key)["correct_option"])
        otra = next(opcion["key"] for opcion in pregunta.body["options"] if str(opcion["key"]) != correcta)
        puntaje, _ = correccion.corregir_multiple_choice(dict(pregunta.answer_key), {"option_id": otra})
        assert puntaje == 0.0, pregunta.stem[:60]


def test_los_ejercicios_de_sql_se_ejecutan_de_verdad(db: Session, cfg: ServicioConfig) -> None:
    """El sandbox DuckDB corre esquema, datos y consulta de referencia de cada ejercicio."""
    ruta = _ruta(db)
    ejercicios = [
        pregunta for pregunta in _preguntas(db, ruta) if pregunta.question_type is QuestionType.SQL_EXERCISE
    ]
    assert len(ejercicios) == 6

    for pregunta in ejercicios:
        cuerpo = dict(pregunta.body)
        clave = dict(pregunta.answer_key)
        resultado = sandbox_sql.evaluar_ejercicio(
            cfg,
            body=cuerpo,
            answer_key=clave,
            consulta_usuario=str(clave["reference_sql"]),
        )
        assert resultado.error_code is None, f"{pregunta.stem[:60]} → {resultado.message}"
        assert resultado.is_correct is True, pregunta.stem[:60]
        assert resultado.row_count > 0, pregunta.stem[:60]


def test_una_consulta_incorrecta_falla_en_el_sandbox(db: Session, cfg: ServicioConfig) -> None:
    """El sandbox discrimina: otra consulta sobre el mismo esquema no puntúa."""
    ruta = _ruta(db)
    pregunta = next(p for p in _preguntas(db, ruta) if p.question_type is QuestionType.SQL_EXERCISE)
    resultado = sandbox_sql.evaluar_ejercicio(
        cfg,
        body=dict(pregunta.body),
        answer_key=dict(pregunta.answer_key),
        consulta_usuario="SELECT region FROM reinos",
    )
    assert resultado.is_correct is False


def test_las_preguntas_abiertas_traen_rubrica_y_respuesta_de_referencia(db: Session) -> None:
    """El juez de IA necesita criterios; la semilla además deja una respuesta modelo."""
    ruta = _ruta(db)
    abiertas = [
        pregunta for pregunta in _preguntas(db, ruta) if pregunta.question_type is QuestionType.OPEN_SHORT
    ]
    assert len(abiertas) == 2
    for pregunta in abiertas:
        criterios = pregunta.body["rubric"]["criteria"]
        assert len(criterios) >= 1
        for criterio in criterios:
            assert criterio["key"] and criterio["text"]
        assert dict(pregunta.answer_key)["reference_answer"]
        assert dict(pregunta.answer_key)["key_points"]


# ---------------------------------------------------------------------------
# Evaluaciones de módulo
# ---------------------------------------------------------------------------


def test_las_evaluaciones_se_pueden_aprobar_sin_ia(db: Session) -> None:
    """El banco de cada prueba excluye las preguntas abiertas (contrato §9)."""
    ruta = _ruta(db)
    modulos = list(
        db.execute(
            sa.select(PathModule).where(PathModule.learning_path_id == ruta.id).order_by(PathModule.position)
        ).scalars()
    )
    corregibles = correccion.TIPOS_DETERMINISTAS | {QuestionType.SQL_EXERCISE}

    total_banco = 0
    for modulo, semilla in zip(modulos, RUTA.modulos, strict=True):
        evaluacion = db.execute(sa.select(Assessment).where(Assessment.module_id == modulo.id)).scalar_one()
        banco = list(
            db.execute(
                sa.select(Question)
                .join(AssessmentQuestion, AssessmentQuestion.question_id == Question.id)
                .where(AssessmentQuestion.assessment_id == evaluacion.id)
            ).scalars()
        )
        assert banco, modulo.title
        assert len(banco) == len(banco_de_evaluacion(semilla))
        assert evaluacion.bank_size == len(banco)
        assert evaluacion.question_count <= len(banco)
        for pregunta in banco:
            assert pregunta.question_type in corregibles, pregunta.stem[:60]
        total_banco += len(banco)

    assert total_banco == 22


def test_el_umbral_de_aprobacion_sale_de_la_configuracion(db: Session, cfg: ServicioConfig) -> None:
    """`mastery.assessment.pass_score` manda; no se escribe un 70 en el código."""
    esperado = cfg.obtener_decimal("mastery.assessment.pass_score")
    maximo = cfg.obtener_int("mastery.assessment.max_attempts_per_day")
    ruta = _ruta(db)
    evaluaciones = list(
        db.execute(
            sa.select(Assessment)
            .join(PathModule, PathModule.id == Assessment.module_id)
            .where(PathModule.learning_path_id == ruta.id)
        ).scalars()
    )
    assert len(evaluaciones) == 3
    for evaluacion in evaluaciones:
        assert evaluacion.pass_score == esperado
        assert evaluacion.max_attempts_per_day == maximo
        assert evaluacion.title.startswith("Prueba")
