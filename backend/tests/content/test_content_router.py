"""Contrato HTTP del módulo `content` (§7.4, §7.5, §7.6 y §7.7).

Se monta una app mínima con el router de `content` y se sustituyen `get_db` y
`get_current_user`: así se prueba el contrato de la API sin depender de `app/main.py`
ni del router raíz, que pertenecen a otros agentes.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa

from app.core.time import utcnow
from app.models.content import LearningPath
from app.models.progress import StudyActivity
from app.modules.progress.progreso import ServicioProgreso

pytestmark = pytest.mark.db


def _cabeceras() -> dict[str, str]:
    """Cabecera `Idempotency-Key` con un UUID v4 nuevo (§8.3)."""
    return {"Idempotency-Key": str(uuid.uuid4())}


# ---------------------------------------------------------------------------
# La garantía estructural: `answer_key` nunca sale por la API (§8.7)
# ---------------------------------------------------------------------------


def test_answer_key_nunca_sale_por_ninguna_ruta(cliente, db, contenido):
    """Ni la lección, ni la actividad, ni la evaluación, ni la revisión la exponen."""
    cuerpos: list[str] = []

    leccion = cliente.get(f"/api/v1/lessons/{contenido.leccion1.id}")
    assert leccion.status_code == 200
    cuerpos.append(leccion.text)

    actividad = cliente.post(
        f"/api/v1/lessons/{contenido.leccion1.id}/start", headers=_cabeceras()
    )
    assert actividad.status_code == 201
    cuerpos.append(actividad.text)

    intento = cliente.post(
        f"/api/v1/assessments/{contenido.evaluacion.id}/start", headers=_cabeceras()
    )
    assert intento.status_code == 201
    cuerpos.append(intento.text)

    attempt_id = intento.json()["attempt_id"]
    for pregunta in intento.json()["questions"]:
        cliente.post(
            f"/api/v1/assessment-attempts/{attempt_id}/answers",
            json={"question_id": pregunta["question_id"], "response": {"option_id": "a"}},
            headers=_cabeceras(),
        )
    envio = cliente.post(
        f"/api/v1/assessment-attempts/{attempt_id}/submit", headers=_cabeceras()
    )
    assert envio.status_code == 200
    cuerpos.append(envio.text)

    revision = cliente.get(f"/api/v1/assessment-attempts/{attempt_id}")
    assert revision.status_code == 200
    cuerpos.append(revision.text)

    for cuerpo in cuerpos:
        assert "answer_key" not in cuerpo
        assert "correct_option_id" not in cuerpo


def test_la_leccion_no_trae_la_explicacion_antes_de_responder(cliente, contenido):
    """La explicación llega **después** de responder, en `AnswerResultOut` (§7.6)."""
    respuesta = cliente.get(f"/api/v1/lessons/{contenido.leccion1.id}")

    cuerpo = respuesta.json()
    assert cuerpo["lesson_id"] == str(contenido.leccion1.id)
    assert cuerpo["blocks"][0]["block_type"] == "explanation"
    for pregunta in cuerpo["questions_preview"]:
        assert "explanation" not in pregunta


# ---------------------------------------------------------------------------
# §7.6 · Ciclo completo por HTTP
# ---------------------------------------------------------------------------


def test_ciclo_de_leccion_por_http_devuelve_el_recibo(cliente, db, contenido):
    """Abrir, responder y cerrar por HTTP entrega el `RewardsReceipt` de §7.10."""
    inicio = cliente.post(f"/api/v1/lessons/{contenido.leccion1.id}/start", headers=_cabeceras())
    actividad_id = inicio.json()["activity_id"]

    # El tiempo mínimo plausible de una lección es `max(60 s, 0.25 x estimated_seconds)`
    # (§6.9 A4). La prueba no puede esperar 135 s reales: se atrasa el reloj del
    # servidor de la actividad, que es de donde sale `elapsed_seconds`.
    actividad = db.get(StudyActivity, uuid.UUID(actividad_id))
    actividad.started_at = utcnow() - timedelta(seconds=200)
    db.flush()

    for pregunta in inicio.json()["questions"]:
        respuesta = (
            {"option_id": "a"}
            if pregunta["question_type"] == "multiple_choice"
            else {"value": True}
        )
        resultado = cliente.post(
            f"/api/v1/activities/{actividad_id}/answers",
            json={
                "question_id": pregunta["question_id"],
                "response": respuesta,
                "response_ms": 6400,
            },
            headers=_cabeceras(),
        )
        assert resultado.status_code == 200
        cuerpo = resultado.json()
        assert cuerpo["is_correct"] is True
        assert cuerpo["evaluation_method"] == "deterministic"
        assert cuerpo["explanation"]

    cliente.post(
        f"/api/v1/activities/{actividad_id}/heartbeat",
        json={"seconds": 60},
        headers=_cabeceras(),
    )

    cierre = cliente.post(f"/api/v1/activities/{actividad_id}/complete", headers=_cabeceras())

    assert cierre.status_code == 200
    recibo = cierre.json()
    assert recibo["event_type"] == "LESSON_COMPLETED"
    assert recibo["xp"]["amount"] > 0
    assert "xp" in recibo["presentation_order"]
    assert recibo["assessment_result"] is None


def test_sin_idempotency_key_la_apertura_responde_400(cliente, contenido):
    """§8.3: falta la cabecera → `400 IDEMPOTENCY_KEY_REQUIRED`."""
    respuesta = cliente.post(f"/api/v1/lessons/{contenido.leccion1.id}/start")

    assert respuesta.status_code == 400
    assert respuesta.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_la_leccion_ajena_responde_404(cliente):
    """§8.7: un id que no existe (o no es visible) responde `404`, nunca `403`."""
    respuesta = cliente.get(f"/api/v1/lessons/{uuid.uuid4()}")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "NOT_FOUND"


def _reportar(cliente, pregunta):
    """Envía un reporte de esa pregunta con el cliente dado."""
    return cliente.post(
        "/api/v1/content/report",
        json={
            "content_type": "question",
            "content_id": str(pregunta.id),
            "reason": "incorrect",
            "comment": "La opción correcta no lo es.",
        },
    )


def test_reportar_contenido_ajeno_responde_404(cliente, contenido):
    """No se puede reportar contenido al que no se tiene acceso.

    La Ruta del Reino del fixture no está adoptada. Sin esta guarda, cualquier
    cuenta recién registrada podía enumerar sus preguntas y marcarlas una a una:
    el filtro de exclusión es global, así que el Reino entero se quedaba sin
    preguntas. Se responde 404 y no 403 porque decir "no puedes" confirma que
    existe.
    """
    respuesta = _reportar(cliente, contenido.preguntas_l1[0])

    assert respuesta.status_code == 404


def test_un_solo_reporte_no_retira_contenido_compartido(cliente, db, usuario, contenido):
    """En una Ruta del Reino hacen falta varios reportes de personas distintas.

    Retirar una pregunta compartida se la quita a todos, así que un reporte
    suelto la anota pero no la saca del pool.
    """
    ServicioProgreso(db).asegurar_progreso_ruta(usuario.id, contenido.ruta.id)
    db.flush()
    pregunta = contenido.preguntas_l1[0]

    assert _reportar(cliente, pregunta).status_code == 204

    db.refresh(pregunta)
    assert pregunta.is_flagged is True
    assert pregunta.flag_reason == "incorrect"
    assert pregunta.flag_count == 1
    assert pregunta.content_status.value != "flagged", "un solo reporte no retira nada"


def test_reportar_dos_veces_lo_mismo_cuenta_una(cliente, db, usuario, contenido):
    """El umbral mide personas distintas, no insistencia.

    La clave de idempotencia llevaba la hora, así que el mismo aprendiz podía
    contar tantas veces como quisiera. Ya no.
    """
    ServicioProgreso(db).asegurar_progreso_ruta(usuario.id, contenido.ruta.id)
    db.flush()
    pregunta = contenido.preguntas_l1[0]

    assert _reportar(cliente, pregunta).status_code == 204
    assert _reportar(cliente, pregunta).status_code == 204

    db.refresh(pregunta)
    assert pregunta.flag_count == 1


# ---------------------------------------------------------------------------
# §7.4 · Conocimientos y mundo
# ---------------------------------------------------------------------------


def test_listado_de_conocimientos_incluye_el_dominio(cliente, contenido):
    """`GET /knowledge-areas` devuelve el catálogo canónico con el dominio del usuario."""
    respuesta = cliente.get("/api/v1/knowledge-areas")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    slugs = {item["slug"] for item in cuerpo["items"]}
    assert contenido.area.slug in slugs
    assert cuerpo["page"]["limit"] == 20


def test_detalle_de_conocimiento_explica_el_dominio(cliente, contenido):
    """§6.7: el detalle trae la explicación obligatoria del porcentaje."""
    respuesta = cliente.get(f"/api/v1/knowledge-areas/{contenido.area.id}")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo["explain"]) >= {
        "practice_pct",
        "assessment_pct",
        "modules_mastered",
        "modules_total",
        "weak_topics",
    }
    assert cuerpo["territory"]["name"] == "Castillo de las Consultas"


def test_territorios_devuelven_el_estado_del_mapa(cliente, contenido):
    """`GET /territories` trae el estado y las zonas de cada territorio (P22)."""
    respuesta = cliente.get("/api/v1/territories")

    assert respuesta.status_code == 200
    territorios = respuesta.json()["items"]
    assert territorios
    assert territorios[0]["status"] in {"fogged", "discovered", "completed"}


# ---------------------------------------------------------------------------
# §7.5 · Rutas
# ---------------------------------------------------------------------------


def test_crear_ruta_es_idempotente_por_cabecera(cliente):
    """§8.3: la misma clave devuelve la misma ruta con `200` en vez de `201`."""
    cabeceras = _cabeceras()
    cuerpo = {"goal_text": "Quiero dominar SQL", "knowledge_area_hint": "SQL analítico"}

    primera = cliente.post("/api/v1/paths", json=cuerpo, headers=cabeceras)
    segunda = cliente.post("/api/v1/paths", json=cuerpo, headers=cabeceras)

    assert primera.status_code == 201
    assert segunda.status_code == 200
    assert segunda.json()["path"]["path_id"] == primera.json()["path"]["path_id"]


def test_adoptar_una_ruta_del_reino_crea_el_progreso_sin_duplicar_contenido(
    cliente, db, contenido
):
    """§5.9 D17: adoptar no clona contenido, solo crea el progreso del usuario."""
    antes = db.execute(sa.select(sa.func.count(LearningPath.id))).scalar_one()

    respuesta = cliente.post(f"/api/v1/paths/{contenido.ruta.id}/adopt")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["path"]["path_id"] == str(contenido.ruta.id)
    assert cuerpo["path"]["is_seed"] is True
    assert cuerpo["modules"][0]["status"] in {"available", "in_progress"}
    assert cuerpo["modules"][1]["status"] == "locked"

    despues = db.execute(sa.select(sa.func.count(LearningPath.id))).scalar_one()
    assert despues == antes


def test_el_mapa_de_la_ruta_trae_modulos_temas_y_lecciones(cliente, contenido):
    """`GET /paths/{id}` es el mapa de P07 con el bloqueo de cada zona."""
    respuesta = cliente.get(f"/api/v1/paths/{contenido.ruta.id}")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["modules_total"] == 2
    primer_modulo = cuerpo["modules"][0]
    assert primer_modulo["topics"][0]["title"] == "JOINs"
    assert len(primer_modulo["topics"][0]["lessons"]) == 2


def test_listar_rutas_filtra_por_ambito(cliente, contenido):
    """`GET /paths?scope=seed` solo trae Rutas del Reino (§7.5)."""
    respuesta = cliente.get("/api/v1/paths", params={"scope": "seed"})

    assert respuesta.status_code == 200
    items = respuesta.json()["items"]
    assert items
    assert all(item["is_seed"] for item in items)


def test_ambito_invalido_responde_422(cliente):
    """Un `scope` fuera del catálogo es un error de validación (§8.1)."""
    respuesta = cliente.get("/api/v1/paths", params={"scope": "otro"})

    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["code"] == "VALIDATION_ERROR"


def test_archivar_y_borrar_una_ruta_propia(cliente):
    """`PATCH` archiva y `DELETE` elimina la ruta del usuario (§7.5)."""
    creada = cliente.post(
        "/api/v1/paths",
        json={"goal_text": "Aprender dbt", "knowledge_area_hint": "dbt"},
        headers=_cabeceras(),
    )
    path_id = creada.json()["path"]["path_id"]

    archivada = cliente.patch(f"/api/v1/paths/{path_id}", json={"archived": True})
    assert archivada.status_code == 200
    assert archivada.json()["path"]["archived_at"] is not None

    borrada = cliente.delete(f"/api/v1/paths/{path_id}")
    assert borrada.status_code == 204
    assert cliente.get(f"/api/v1/paths/{path_id}").status_code == 404


# ---------------------------------------------------------------------------
# §7.7 · Evaluación por HTTP
# ---------------------------------------------------------------------------


def test_entrada_de_la_prueba_por_http(cliente, contenido):
    """`GET /modules/{id}/assessment` es la pantalla P11."""
    respuesta = cliente.get(f"/api/v1/modules/{contenido.modulo1.id}/assessment")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["can_start"] is True
    assert cuerpo["assessment"]["title"] == "Prueba del módulo"
    assert cuerpo["reward_preview"]["xp"] > 0


def test_el_recibo_de_la_evaluacion_es_json_serializable(cliente, contenido):
    """El `RewardsReceipt` viaja tal cual: `assessment_result` incluido (§7.10 regla 6)."""
    intento = cliente.post(
        f"/api/v1/assessments/{contenido.evaluacion.id}/start", headers=_cabeceras()
    )
    attempt_id = intento.json()["attempt_id"]
    for pregunta in intento.json()["questions"]:
        cliente.post(
            f"/api/v1/assessment-attempts/{attempt_id}/answers",
            json={"question_id": pregunta["question_id"], "response": {"option_id": "a"}},
            headers=_cabeceras(),
        )

    envio = cliente.post(
        f"/api/v1/assessment-attempts/{attempt_id}/submit", headers=_cabeceras()
    )

    recibo = json.loads(envio.text)
    assert recibo["assessment_result"]["passed"] is True
    assert recibo["assessment_result"]["per_topic"]
    assert recibo["presentation_order"]


def test_adoptar_la_ruta_del_reino_emite_su_evento(cliente, db, contenido):
    """Adoptar es empezar una Ruta, y el motor solo se entera por eventos.

    Es el camino del día uno: la app propone la Ruta del Reino, no crear una
    propia. Sin este evento el primer logro no se desbloqueaba y ninguna misión
    avanzaba: el aprendiz hacía justo lo que se le pedía y el juego no
    reaccionaba.
    """
    from app.models.enums import EventType
    from app.models.gamification import DomainEvent

    respuesta = cliente.post(f"/api/v1/paths/{contenido.ruta.id}/adopt")
    assert respuesta.status_code == 200, respuesta.text

    eventos = db.execute(
        sa.select(DomainEvent).where(DomainEvent.event_type == EventType.PATH_CREATED)
    ).scalars().all()

    assert len(eventos) == 1
    assert eventos[0].payload["path_id"] == str(contenido.ruta.id)
    assert eventos[0].payload["adopted"] is True


def test_adoptar_dos_veces_no_emite_dos_eventos(cliente, db, contenido):
    """La idempotencia del §4.1: adoptar de nuevo no vuelve a pagar."""
    from app.models.enums import EventType
    from app.models.gamification import DomainEvent

    cliente.post(f"/api/v1/paths/{contenido.ruta.id}/adopt")
    cliente.post(f"/api/v1/paths/{contenido.ruta.id}/adopt")

    cuantos = db.execute(
        sa.select(sa.func.count())
        .select_from(DomainEvent)
        .where(DomainEvent.event_type == EventType.PATH_CREATED)
    ).scalar_one()

    assert cuantos == 1
