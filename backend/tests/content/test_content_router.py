"""Contrato HTTP del módulo `content` (§7.4, §7.5, §7.6 y §7.7).

Se monta una app mínima con el router de `content` y se sustituyen `get_db` y
`get_current_user`: así se prueba el contrato de la API sin depender de `app/main.py`
ni del router raíz, que pertenecen a otros agentes.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.core.time import user_local_date, utcnow
from app.models.content import Assessment, KnowledgeArea, LearningPath, PathModule, Topic
from app.models.enums import (
    AttemptStatus,
    ContentStatus,
    CoverageLevel,
    CoveragePolicy,
    ModuleStatus,
    PathStatus,
)
from app.models.progress import (
    AssessmentAttempt,
    StudyActivity,
    UserAreaProgress,
    UserModuleProgress,
)
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


def _area_de(db, respuesta) -> KnowledgeArea:
    """El conocimiento al que quedó atada la ruta recién creada."""
    ruta = db.get(LearningPath, uuid.UUID(respuesta.json()["path"]["path_id"]))
    return db.get(KnowledgeArea, ruta.knowledge_area_id)


def test_crear_ruta_solo_con_el_objetivo_funciona(cliente):
    """Es lo único que manda la aplicación, y era imposible.

    P05 pide **un** texto libre —el objetivo— y no tiene ni ha tenido nunca un
    campo de conocimiento: `ControladorAventura` expone `fijarPistaConocimiento`
    y no la llama nadie en todo el cliente. Así que `knowledge_area_hint`
    llegaba siempre vacía, `_area_para_ruta` lanzaba, y **crear una ruta desde
    la aplicación no funcionó jamás**: el aprendiz veía «Indica sobre qué
    conocimiento quieres aprender» sobre un formulario relleno y con los tres
    pasos en verde.

    Ninguna de las pruebas de creación lo vio porque **todas mandaban la
    pista**, que es precisamente lo que la aplicación no manda. Esta manda el
    cuerpo real.
    """
    respuesta = cliente.post(
        "/api/v1/paths",
        json={"goal_text": "Quiero aprender a cocinar al vapor"},
        headers=_cabeceras(),
    )

    assert respuesta.status_code == 201, respuesta.text


def test_el_objetivo_que_nombra_un_conocimiento_cae_en_su_territorio(
    cliente, db, contenido
):
    """«Aprender SQL…» va al Castillo de las Consultas, no a un área paralela.

    Sin esto, cada aprendiz abriría su propia taxonomía privada —«aprender-sql-
    para-analizar-datos»— y el mapa del Reino no se encendería nunca, porque
    los territorios salen solo de las siete áreas canónicas.
    """
    respuesta = cliente.post(
        "/api/v1/paths",
        json={"goal_text": "Aprender SQL para analizar datos en mi trabajo"},
        headers=_cabeceras(),
    )

    assert respuesta.status_code == 201
    area = _area_de(db, respuesta)
    assert area.id == contenido.area.id, "abrió un conocimiento paralelo en vez de reusar el canónico"
    assert area.is_canonical is True


def test_un_objetivo_sin_conocimiento_conocido_abre_uno_del_usuario(cliente, db, usuario):
    """No nombrar ninguno no es un fallo: el diseño quiere áreas propias (§4.2)."""
    respuesta = cliente.post(
        "/api/v1/paths",
        json={"goal_text": "Entender estadística para mi tesis"},
        headers=_cabeceras(),
    )

    assert respuesta.status_code == 201
    area = _area_de(db, respuesta)
    assert area.is_canonical is False
    assert area.created_by_user_id == usuario.id


def test_postgresql_no_se_confunde_con_sql(cliente, db, contenido):
    """El nombre se busca como palabra entera, no como trozo.

    Sin el límite de palabra, «PostgreSQL» arrastraría la ruta al conocimiento
    «SQL» —que es parecido pero no es—, y lo mismo haría cualquier palabra que
    contuviera el nombre de un área por casualidad.
    """
    respuesta = cliente.post(
        "/api/v1/paths",
        json={"goal_text": "Quiero dominar PostgreSQL a fondo"},
        headers=_cabeceras(),
    )

    assert respuesta.status_code == 201
    # La fixture trae «SQL» canónico: sin ella esta prueba pasaría en el vacío.
    assert _area_de(db, respuesta).id != contenido.area.id


def test_la_pista_sigue_mandando_sobre_el_objetivo(cliente, db, contenido):
    """El objetivo es el respaldo, no el sustituto.

    Cuando la pantalla sí sabe el área —crear una ruta desde un territorio—, la
    pista tiene que ganar aunque el objetivo nombre otra cosa distinta.
    """
    respuesta = cliente.post(
        "/api/v1/paths",
        json={"goal_text": "Aprender SQL para analizar datos", "knowledge_area_hint": "Python"},
        headers=_cabeceras(),
    )

    assert respuesta.status_code == 201
    area = _area_de(db, respuesta)
    assert area.name == "Python"
    assert area.id != contenido.area.id, "ganó el objetivo, no la pista"


def test_sin_objetivo_sigue_siendo_un_error_con_su_campo(cliente):
    """Lo que falta ahora es el objetivo, y el sobre tiene que decirlo.

    El cliente pinta el error por campo (`field_errors`), así que señalar
    `knowledge_area_hint` —un campo que la pantalla no tiene— dejaba el aviso
    sin poder apuntar a nada.
    """
    respuesta = cliente.post(
        "/api/v1/paths", json={"goal_text": "   "}, headers=_cabeceras()
    )

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    campos = [
        f.get("field")
        for f in (cuerpo["error"].get("field_errors") or cuerpo["error"]["details"].get("field_errors", []))
    ]
    assert "goal_text" in str(campos) or "goal_text" in respuesta.text


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


def test_el_dominio_del_territorio_viaja_en_la_cabecera_y_en_la_tarjeta(
    db, cliente, usuario, contenido
):
    """«Dominio del territorio» se quedaba en 0 % siempre: nadie mandaba el dato.

    `PathSummaryOut`/`PathDetailOut` no declaraban `mastery`, y `_ruta_out`/
    `_detalle_out` no lo asignaban —aunque sí propagan `mastery` para cada
    módulo y cada tema dentro del mismo sobre—. El dato ni siquiera es de la
    Ruta: es `UserAreaProgress.mastery`, del Conocimiento del que cuelga.
    """
    db.add(
        UserAreaProgress(
            user_id=usuario.id,
            knowledge_area_id=contenido.area.id,
            mastery=Decimal("62.50"),
        )
    )
    db.flush()

    mapa = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()
    assert mapa["mastery"] == 62.5
    assert mapa["path"]["mastery"] == 62.5

    listado = cliente.get("/api/v1/paths", params={"scope": "seed"}).json()
    tarjeta = next(r for r in listado["items"] if r["path_id"] == str(contenido.ruta.id))
    assert tarjeta["mastery"] == 62.5


def test_sin_evidencia_en_el_conocimiento_el_dominio_es_cero(cliente, contenido):
    """Sin fila de `UserAreaProgress` (nadie ha estudiado ese Conocimiento aún),
    el dominio no debe fallar ni inventar un número: es 0 %, de verdad.
    """
    mapa = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()
    assert mapa["mastery"] == 0.0
    assert mapa["path"]["mastery"] == 0.0


def test_cada_leccion_del_mapa_dice_si_esta_lista(cliente, contenido):
    """Sin `content_status` en el nodo, P07 no deja abrir ni una lección.

    No es un campo informativo: el cliente pinta «en construcción» y **se niega
    a navegar** mientras la lección no esté `ready` (`mapa_ruta.dart`). El nodo
    no lo serializaba, el cliente lo leía igual, y al no encontrarlo caía a
    `pending` —así que todas las lecciones de todas las rutas eran inabribles
    desde el mapa, y el aprendiz solo veía «esta lección se está escribiendo
    ahora mismo» para siempre.

    Ninguna prueba lo notó porque ninguna miraba este campo. Esta es la primera,
    y es la razón de que compruebe el valor y no solo la presencia: las
    lecciones de la fixture están `READY`, así que un nodo que dijera `pending`
    estaría mintiendo.
    """
    respuesta = cliente.get(f"/api/v1/paths/{contenido.ruta.id}")

    assert respuesta.status_code == 200
    lecciones = respuesta.json()["modules"][0]["topics"][0]["lessons"]
    assert lecciones
    assert all(leccion["content_status"] == "ready" for leccion in lecciones)


def _intento(
    db, usuario, contenido, *, numero, momento, enfriamiento=None,
    evaluacion=None, modulo=None, fecha=None,
):
    """Un intento ya entregado, fechado como lo fecha producción.

    `local_date` va en la **fecha local del usuario**, no en la UTC, porque es
    así como la escribe `iniciar_intento` (§8.6) y así como la lee el mapa. La
    diferencia no es teórica: el usuario de estas pruebas vive en
    `America/Santiago`, o sea que entre las 00:00 y las 03:00 UTC las dos
    fechas no coinciden. Con la fecha UTC, estas pruebas pasaban veintiuna
    horas al día y se ponían rojas las otras tres, sin que nadie tocara el
    código —y mientras tanto no distinguían la regla local de «las últimas 24
    horas», que es justo lo que dicen comprobar.
    """
    evaluacion = evaluacion or contenido.evaluacion
    fila = AssessmentAttempt(
        user_id=usuario.id,
        assessment_id=evaluacion.id,
        module_id=modulo.id if modulo else contenido.modulo1.id,
        learning_path_id=contenido.ruta.id,
        attempt_no=numero,
        status=AttemptStatus.SUBMITTED,
        question_count=4,
        question_ids=[],
        correct_count=2,
        score=50,
        started_at=momento,
        submitted_at=momento,
        local_date=fecha or user_local_date(momento, usuario.timezone),
        cooldown_until=enfriamiento,
        idempotency_key=str(uuid.uuid4()),
    )
    db.add(fila)
    db.flush()
    return fila


def test_el_mapa_de_la_ruta_trae_el_desafio_de_cada_modulo(cliente, contenido):
    """Sin `assessment` en el nodo, P07 no pinta el desafío: no existe.

    El mapa ya traía `assessment_best_score` y `assessment_passed` sueltos,
    y por eso parecía que el dato estaba. Pero el cliente dibuja el nodo del
    desafío desde el objeto `assessment` —`ModuloRuta.desdeJson` lo lee, y si
    no viene deja `evaluacion` en `null`—, así que el remate del módulo
    simplemente no aparecía en el mapa de ninguna ruta.

    Comprueba los dos casos porque son caminos distintos de dibujo: el módulo
    1 tiene evaluación y el 2 no, y «sin prueba» tiene que llegar como `null`,
    no como un objeto vacío que el cliente pintaría como desafío existente.
    """
    respuesta = cliente.get(f"/api/v1/paths/{contenido.ruta.id}")

    assert respuesta.status_code == 200
    modulos = respuesta.json()["modules"]

    desafio = modulos[0]["assessment"]
    assert desafio is not None
    assert desafio["assessment_id"] == str(contenido.evaluacion.id)
    assert desafio["module_id"] == str(contenido.modulo1.id)
    assert desafio["title"] == "Prueba del módulo"
    assert desafio["question_count"] == 4
    assert desafio["content_status"] == "ready"
    assert desafio["attempts_used"] == 0
    assert desafio["passed"] is False
    assert desafio["best_score"] is None
    assert desafio["can_start"] is True
    assert desafio["cooldown_until"] is None

    assert modulos[1]["assessment"] is None


def test_el_desafio_del_mapa_cuenta_los_intentos_de_hoy(cliente, db, usuario, contenido):
    """El tope diario sale de `game_configs`, no de un número en el cliente.

    `mastery.assessment.max_attempts_per_day` vale 2 en las semillas, así que
    con dos intentos de hoy el mapa tiene que decir que no se puede empezar.
    Y el intento de ayer no cuenta: la regla es por fecha **local** del
    usuario (§8.6), no por las últimas 24 horas.
    """
    ahora = utcnow()
    _intento(db, usuario, contenido, numero=1, momento=ahora - timedelta(days=1))

    primero = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()
    desafio = primero["modules"][0]["assessment"]
    assert desafio["attempts_used"] == 0, "el intento de ayer no gasta el cupo de hoy"
    assert desafio["can_start"] is True

    _intento(db, usuario, contenido, numero=2, momento=ahora)
    _intento(db, usuario, contenido, numero=3, momento=ahora)

    segundo = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()
    desafio = segundo["modules"][0]["assessment"]
    assert desafio["attempts_used"] == 2
    assert desafio["max_attempts_per_day"] == 2
    assert desafio["can_start"] is False


def test_el_desafio_del_mapa_respeta_el_enfriamiento(cliente, db, usuario, contenido):
    """Un enfriamiento vigente cierra el desafío aunque queden intentos.

    Son dos frenos distintos y el mapa tiene que distinguirlos: aquí
    `attempts_used` sigue por debajo del tope y aun así `can_start` es falso.
    Si se hubieran mezclado, el aprendiz vería «te queda un intento» sobre un
    botón que no responde.
    """
    ahora = utcnow()
    _intento(
        db, usuario, contenido, numero=1, momento=ahora,
        enfriamiento=ahora + timedelta(hours=4),
    )

    desafio = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()["modules"][0][
        "assessment"
    ]

    assert desafio["attempts_used"] == 1
    assert desafio["attempts_used"] < desafio["max_attempts_per_day"]
    assert desafio["can_start"] is False
    assert desafio["cooldown_until"] is not None


def test_el_nodo_del_modulo_dice_si_esta_escrito(cliente, db, contenido):
    """Sin `content_status`, el mapa pinta TODOS los módulos «En construcción».

    Es el hermano exacto del fallo que §4.2 arregló para las lecciones
    (`255065e`), un nivel más arriba y con la misma forma: el cliente lee
    `content_status` del nodo (`ModuloRuta.desdeJson`), no lo encontraba, caía
    a `pending`, y `enConstruccion` —que `_estiloModulo` comprueba **antes**
    que «actual» y «disponible»— quedaba en cierto para siempre. Resultado: el
    módulo en el que está el aprendiz sale con icono de llama y la píldora «En
    construcción», y al tocarlo la hoja le dice que el Reino todavía lo está
    escribiendo. Aunque esté listo.

    Los dos módulos tienen estados distintos a propósito: con los dos iguales,
    un nodo que devolviera una constante pasaría igual.
    """
    contenido.modulo1.content_status = ContentStatus.READY
    db.flush()

    modulos = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()["modules"]

    assert modulos[0]["content_status"] == "ready"
    assert modulos[1]["content_status"] == "pending"


def test_el_nodo_del_modulo_trae_lo_que_el_mapa_pinta(cliente, db, contenido):
    """El resumen y la duración: los pinta el nodo y no viajaban.

    `ContenidoModulo` escribe el párrafo de `summary` y una píldora con
    `estimated_minutes` (`nodos_mapa.dart`), y las dos columnas existen en
    `path_modules` desde siempre. Como el nodo no las serializaba, el módulo se
    veía sin decir de qué trata ni cuánto lleva.

    Se comprueban con valores propios, no con los de la fixture por defecto: un
    `None` a cada lado también «coincide».
    """
    contenido.modulo1.summary = "Cómo unir dos tablas sin perder filas"
    contenido.modulo1.estimated_minutes = 35
    db.flush()

    nodo = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()["modules"][0]

    assert nodo["summary"] == "Cómo unir dos tablas sin perder filas"
    assert nodo["estimated_minutes"] == 35


def test_un_modulo_sin_resumen_manda_nulo_y_no_una_cadena_vacia(cliente, contenido):
    """El cliente solo pinta el párrafo si hay algo que decir.

    `if (modulo.resumen != null && modulo.resumen!.trim().isNotEmpty)`: una
    cadena vacía pasaría el primer filtro y dejaría un hueco en la tarjeta.
    """
    nodo = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()["modules"][1]

    assert nodo["summary"] is None
    assert nodo["estimated_minutes"] is None


def test_el_mapa_dice_que_temas_respalda_el_material(cliente, db, contenido):
    """`coverage` es lo único que distingue tu PDF del saber del Reino.

    El cliente lo lee (`Tema.desdeJson`) y de ahí sale `esConocimientoGeneral`,
    que gobierna dos cosas: la píldora «Saber del Reino» del nodo de módulo y
    la franja del mapa que la anuncia. Sin el campo, `NivelCobertura.desdeApi`
    cae a `completa` —etiqueta «Cubierto por tu material»— y las dos quedan
    apagadas para siempre: el mapa afirma en silencio que los documentos del
    aprendiz respaldan **todos** los temas, incluidos los que la Fase A marcó
    como sin respaldo suficiente y que el autor escribió de memoria.

    Es la promesa que el producto repite más veces —«nunca inventamos, citamos
    tu material»— y era exactamente la que no se podía comprobar en pantalla.

    Dos temas con cobertura distinta a propósito: con los dos iguales, un nodo
    que devolviera una constante pasaría igual.
    """
    otro = Topic(
        module_id=contenido.modulo1.id,
        position=2,
        title="Window functions",
        lesson_count=0,
        coverage=CoverageLevel.INSUFFICIENT,
    )
    db.add(otro)
    contenido.tema.coverage = CoverageLevel.FULL
    db.flush()

    temas = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()["modules"][0]["topics"]
    por_titulo = {t["title"]: t["coverage"] for t in temas}

    assert por_titulo["JOINs"] == "full"
    assert por_titulo["Window functions"] == "insufficient"


def test_el_mapa_nombra_los_temas_que_el_material_no_cubre(cliente, db, contenido):
    """`coverage_notes`: sin ellas se pide decidir sobre temas que nadie nombra.

    La pantalla de generación pinta la tarjeta «Tu material no cubre todo el
    objetivo» y debajo la lista de cuáles. La lista sale de aquí, y la Fase A ya
    las calcula y las guarda en `learning_paths.coverage_notes`. Sin servirlas,
    el mensaje cae siempre al genérico y el aprendiz elige la política de
    cobertura a ciegas.
    """
    contenido.ruta.coverage_notes = ["Sin material de window functions"]
    db.flush()

    cuerpo = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()

    assert cuerpo["coverage_notes"] == ["Sin material de window functions"]


def test_una_ruta_sin_notas_manda_la_lista_vacia(cliente, contenido):
    """Vacía, no ausente: el cliente distingue «no hay huecos» de «no llegó»."""
    cuerpo = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()

    assert cuerpo["coverage_notes"] == []


def test_el_cupo_del_desafio_se_cuenta_en_la_fecha_del_aprendiz(
    cliente, db, usuario, contenido, monkeypatch
):
    """La regla es la fecha **local** del usuario (§8.6), no la UTC.

    Esta prueba solo dice algo dentro de la franja en que las dos fechas no
    coinciden, así que la fabrica: congela el reloj a las 01:30 UTC, que en
    Santiago son las 22:30 del día anterior. Sin congelarlo, «hoy» sería el
    mismo día en las dos zonas veintiuna horas de cada veinticuatro y la
    prueba pasaría igual aunque el código usara la fecha UTC.
    """
    from app.modules.progress import progreso as modulo_progreso

    instante = utcnow().replace(hour=1, minute=30, second=0, microsecond=0)
    monkeypatch.setattr(modulo_progreso, "utcnow", lambda: instante)

    hoy_utc = instante.date()
    hoy_del_aprendiz = user_local_date(instante, usuario.timezone)
    assert hoy_utc != hoy_del_aprendiz, "sin desfase la prueba no prueba nada"

    # Dos intentos en el día del aprendiz: gastan su cupo aunque en UTC ya sea
    # otra fecha.
    _intento(db, usuario, contenido, numero=1, momento=instante, fecha=hoy_del_aprendiz)
    _intento(db, usuario, contenido, numero=2, momento=instante, fecha=hoy_del_aprendiz)

    desafio = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()["modules"][0][
        "assessment"
    ]
    assert desafio["attempts_used"] == 2
    assert desafio["can_start"] is False

    # Y un intento fechado en el día UTC —que para el aprendiz es mañana— no
    # puede gastarle el cupo de hoy.
    db.query(AssessmentAttempt).delete()
    db.flush()
    _intento(db, usuario, contenido, numero=1, momento=instante, fecha=hoy_utc)

    desafio = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()["modules"][0][
        "assessment"
    ]
    assert desafio["attempts_used"] == 0
    assert desafio["can_start"] is True


def test_el_desafio_del_mapa_publica_la_marca_y_el_aprobado(
    cliente, db, usuario, contenido
):
    """`best_score` y `passed` salen del avance del módulo, no de cero.

    Las otras pruebas solo miran el caso virgen, donde los dos valores
    coinciden con el valor por defecto del dataclass: cablearlos a `None` y
    `False` las dejaba verdes. En pantalla, eso es un aprendiz que aprobó con
    95 y ve el nodo sin corona, sin su marca y pintado como si no lo hubiera
    intentado nunca.

    Comprueba además que la cifra es **la misma** que el nodo publica suelta en
    `assessment_best_score`: son el mismo número y la respuesta no puede dar
    dos versiones de él.
    """
    db.add(
        UserModuleProgress(
            user_id=usuario.id,
            module_id=contenido.modulo1.id,
            learning_path_id=contenido.ruta.id,
            status=ModuleStatus.COMPLETED,
            assessment_best_score=95,
            assessment_attempts=1,
            assessment_passed_at=utcnow(),
        )
    )
    db.flush()

    nodo = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()["modules"][0]

    assert nodo["assessment"]["best_score"] == 95.0
    assert nodo["assessment"]["passed"] is True
    assert nodo["assessment"]["best_score"] == nodo["assessment_best_score"]
    assert nodo["assessment"]["passed"] == nodo["assessment_passed"]


def test_cada_modulo_lleva_su_propio_desafio_y_sus_propios_intentos(
    cliente, db, usuario, contenido
):
    """Con una sola evaluación en la ruta, el reparto por módulo no se prueba.

    La fixture crea una, en el módulo 1: con N=1 cualquier implementación que
    devolviera siempre el mismo nodo pasaría, y el agrupado de intentos por
    evaluación nunca vería dos claves. Aquí hay dos evaluaciones y los
    intentos están todos en la primera: si el agrupado perdiera la clave
    —acumular todos los intentos en una lista es la forma natural de
    equivocarse en ese bucle—, el desafío del módulo 2 aparecería cerrado sin
    que el aprendiz lo haya tocado.

    De paso fija que el tope sale de `game_configs` y no de la columna: esta
    segunda evaluación pide 5 por día y `mastery.assessment.max_attempts_per_day`
    vale 2, así que el nodo tiene que decir 2. Con la columna cableada diría 5.
    """
    segunda = Assessment(
        module_id=contenido.modulo2.id,
        title="Prueba del segundo módulo",
        question_count=6,
        bank_size=12,
        max_attempts_per_day=5,
        content_status=ContentStatus.READY,
    )
    db.add(segunda)
    db.flush()

    ahora = utcnow()
    _intento(db, usuario, contenido, numero=1, momento=ahora)
    _intento(db, usuario, contenido, numero=2, momento=ahora)

    modulos = cliente.get(f"/api/v1/paths/{contenido.ruta.id}").json()["modules"]

    primero = modulos[0]["assessment"]
    assert primero["assessment_id"] == str(contenido.evaluacion.id)
    assert primero["attempts_used"] == 2
    assert primero["can_start"] is False

    segundo = modulos[1]["assessment"]
    assert segundo["assessment_id"] == str(segunda.id)
    assert segundo["question_count"] == 6
    assert segundo["attempts_used"] == 0, "los intentos del módulo 1 no son suyos"
    assert segundo["can_start"] is True
    assert segundo["max_attempts_per_day"] == 2, "el tope lo manda game_configs, no la columna"


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
    # Histórico de por vida (`UserModuleProgress.assessment_attempts`): viajaba
    # entero por el servicio y se perdía en el sobre HTTP.
    assert cuerpo["assessment_attempts"] == 0


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


def test_el_historico_de_intentos_sube_tras_enviar_por_http(cliente, contenido):
    """Tras un envío real, `GET /modules/{id}/assessment` ya cuenta ese intento.

    Antes de esta corrección `assessment_attempts` no viajaba nunca —el sobre
    HTTP se quedaba en su default `0`—, así que esta prueba no distinguía nada:
    tanto con y sin el campo cableado el primer `assessment_attempts` de la
    otra prueba salía en `0`. Aquí, tras enviar un intento real, solo pasa si
    el campo de verdad refleja el histórico.
    """
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
    cliente.post(f"/api/v1/assessment-attempts/{attempt_id}/submit", headers=_cabeceras())

    respuesta = cliente.get(f"/api/v1/modules/{contenido.modulo1.id}/assessment")

    assert respuesta.json()["assessment_attempts"] == 1


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


# ---------------------------------------------------------------------------
# Promesas de la interfaz que fallaban en silencio
# ---------------------------------------------------------------------------


def test_el_puente_de_reexplicacion_apunta_a_algo_que_existe():
    """`POST /topics/{id}/explain` respondía 503 siempre.

    El router importaba `app.modules.ai.reexplicacion`, que no existe: la función
    vive en `adaptativo` y se llama `reexplicar`. El `except` lo convertía en un
    503 educado, así que "explícamelo de otra forma" decía siempre que el
    servicio no estaba disponible, en un servidor perfectamente sano.

    Es el mismo fallo que el juez y el sandbox, y por eso se comprueba igual: que
    al otro lado del puente haya algo.
    """
    from app.modules.ai import adaptativo

    assert hasattr(adaptativo, "reexplicar")
    assert hasattr(adaptativo, "Decision")


def test_un_campo_desconocido_en_una_entrada_falla_y_dice_cual(cliente, contenido):
    """Descartar una clave mal escrita en silencio esconde el fallo entero.

    Quitar un tema al confirmar no hacía nada porque el cliente mandaba
    `removed` y el esquema declara `remove`. Pydantic tiraba la clave sin decir
    palabra. Ahora las entradas de `content` rechazan lo que no declaran, igual
    que las de `identity`, que siempre lo hicieron.
    """
    respuesta = cliente.post(
        f"/api/v1/paths/{contenido.ruta.id}/confirm",
        json={"topics": [{"topic_id": str(uuid.uuid4()), "removed": True}]},
    )

    assert respuesta.status_code == 422
    campos = [f["field"] for f in respuesta.json()["error"]["field_errors"]]
    assert any("removed" in c for c in campos), campos


def test_confirmar_con_source_only_quita_los_temas_sin_respaldo(cliente, db, usuario, contenido):
    """«Solo con mi material» se guardaba en `coverage_policy` y no cambiaba nada.

    La Fase A resuelve la política por defecto (`MODEL_KNOWLEDGE`) antes de que el
    aprendiz elija; si al confirmar elige `source_only`, los temas que se quedaron
    `INSUFFICIENT` tienen que desaparecer del esquema —si no, la promesa de «será
    más corta, pero toda con fuente» no cambia ni un tema de lo que se genera—.
    """
    ruta = LearningPath(
        user_id=usuario.id,
        knowledge_area_id=contenido.area.id,
        title="Ruta propia para confirmar",
    )
    db.add(ruta)
    db.flush()

    modulo_con_respaldo = PathModule(learning_path_id=ruta.id, position=1, title="Con respaldo")
    modulo_sin_respaldo = PathModule(learning_path_id=ruta.id, position=2, title="Sin respaldo")
    db.add_all([modulo_con_respaldo, modulo_sin_respaldo])
    db.flush()

    tema_con_fuente = Topic(
        module_id=modulo_con_respaldo.id,
        position=1,
        title="Tiene material",
        coverage=CoverageLevel.FULL,
    )
    tema_sin_fuente = Topic(
        module_id=modulo_con_respaldo.id,
        position=2,
        title="No tiene material",
        coverage=CoverageLevel.INSUFFICIENT,
    )
    tema_huerfano = Topic(
        module_id=modulo_sin_respaldo.id,
        position=1,
        title="Único tema, sin material",
        coverage=CoverageLevel.INSUFFICIENT,
    )
    db.add_all([tema_con_fuente, tema_sin_fuente, tema_huerfano])
    db.flush()

    respuesta = cliente.post(
        f"/api/v1/paths/{ruta.id}/confirm",
        json={"coverage_policy": "source_only"},
    )
    assert respuesta.status_code == 200

    db.expire_all()
    ruta_db = db.get(LearningPath, ruta.id)
    assert ruta_db.coverage_policy is CoveragePolicy.SOURCE_ONLY
    assert ruta_db.module_count == 1

    temas_restantes = db.execute(
        sa.select(Topic.title).where(Topic.module_id == modulo_con_respaldo.id)
    ).scalars().all()
    assert temas_restantes == ["Tiene material"]

    assert db.get(PathModule, modulo_sin_respaldo.id) is None

    notas = " ".join(ruta_db.coverage_notes)
    assert "No tiene material" in notas
    assert "Sin respaldo" in notas


def test_confirmar_con_request_more_y_temas_sin_respaldo_no_avanza(cliente, db, usuario, contenido):
    """«Pedirme más material» dejaba el Módulo 1 generarse igual, de inmediato.

    Con `request_more` y algún tema todavía `insufficient`, el confirm no puede
    avanzar a `GENERATING` ni encolar el módulo 1 —eso generaría ese tema con
    saber del modelo, exactamente lo que el aprendiz pidió esperar—. Responde
    `409 MATERIAL_PENDING`, pero la elección de política sí queda guardada: no
    hace falta que el aprendiz la repita al reintentar.
    """
    ruta = LearningPath(
        user_id=usuario.id,
        knowledge_area_id=contenido.area.id,
        title="Ruta que espera material",
    )
    db.add(ruta)
    db.flush()

    modulo = PathModule(learning_path_id=ruta.id, position=1, title="Módulo único")
    db.add(modulo)
    db.flush()

    db.add_all(
        [
            Topic(module_id=modulo.id, position=1, title="Con material", coverage=CoverageLevel.FULL),
            Topic(
                module_id=modulo.id,
                position=2,
                title="Sin material todavía",
                coverage=CoverageLevel.INSUFFICIENT,
            ),
        ]
    )
    db.flush()

    respuesta = cliente.post(
        f"/api/v1/paths/{ruta.id}/confirm",
        json={"coverage_policy": "request_more"},
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["code"] == "MATERIAL_PENDING"

    db.expire_all()
    ruta_db = db.get(LearningPath, ruta.id)
    assert ruta_db.coverage_policy is CoveragePolicy.REQUEST_MORE
    assert ruta_db.status is not PathStatus.GENERATING
    assert ruta_db.confirmed_at is None

    temas = db.execute(sa.select(Topic).where(Topic.module_id == modulo.id)).scalars().all()
    assert len(temas) == 2, "request_more no debe borrar ni un tema"


def test_confirmar_con_request_more_y_todo_cubierto_avanza_normal(cliente, db, usuario, contenido):
    """`request_more` no es un freno general: sin temas `insufficient`, confirma igual."""
    ruta = LearningPath(
        user_id=usuario.id,
        knowledge_area_id=contenido.area.id,
        title="Ruta ya totalmente cubierta",
    )
    db.add(ruta)
    db.flush()

    modulo = PathModule(learning_path_id=ruta.id, position=1, title="Módulo único")
    db.add(modulo)
    db.flush()

    db.add(Topic(module_id=modulo.id, position=1, title="Con material", coverage=CoverageLevel.FULL))
    db.flush()

    respuesta = cliente.post(
        f"/api/v1/paths/{ruta.id}/confirm",
        json={"coverage_policy": "request_more"},
    )

    assert respuesta.status_code == 200
    db.expire_all()
    ruta_db = db.get(LearningPath, ruta.id)
    assert ruta_db.status is PathStatus.GENERATING


def test_todas_las_entradas_de_content_rechazan_lo_que_no_declaran():
    """La red vale poco si solo cubre un esquema de diez."""
    from app.modules.content import schemas

    entradas = [
        getattr(schemas, n)
        for n in dir(schemas)
        if n.endswith("In") and isinstance(getattr(schemas, n), type)
    ]
    assert entradas, "no se encontró ninguna entrada"

    permisivas = [
        e.__name__ for e in entradas if e.model_config.get("extra") != "forbid"
    ]
    assert permisivas == [], f"estas entradas todavía se tragan campos ajenos: {permisivas}"
