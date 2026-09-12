"""Pruebas de sesiones de estudio y tiempo efectivo (CONTRACT.md §5.6, §6.11).

El tiempo mide dedicación: se acredita con tope por latido, se descartan las lagunas
de inactividad y **nunca** otorga dominio.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa

from app.core.errors import AteneaError
from app.core.time import utcnow
from app.models.enums import AttemptStatus, EventType, SessionEndReason
from app.models.gamification import DomainEvent
from app.models.progress import LearningSession, UserAreaProgress, UserTopicProgress
from app.modules.progress.dominio import ServicioDominio
from app.modules.progress.sesiones import (
    ServicioSesiones,
    acreditar_con_tope,
    segundos_de_latido,
    tope_de_actividad,
)

ZONA_CHILE = "America/Santiago"


# ---------------------------------------------------------------------------
# Lógica pura del latido
# ---------------------------------------------------------------------------


def test_un_latido_normal_se_acredita_entero(cfg_tiempo):
    assert segundos_de_latido(30, 30.0, cfg_tiempo) == (30, None)


def test_el_servidor_no_acepta_mas_de_max_tick_por_latido(cfg_tiempo):
    acreditados, motivo = segundos_de_latido(300, 60.0, cfg_tiempo)
    assert acreditados == cfg_tiempo.max_tick_s
    assert motivo == "tick_cap"


def test_un_latido_nunca_acredita_mas_de_lo_transcurrido(cfg_tiempo):
    acreditados, motivo = segundos_de_latido(60, 12.0, cfg_tiempo)
    assert acreditados == 12
    assert motivo == "gap_cap"


def test_las_lagunas_de_inactividad_se_descartan(cfg_tiempo):
    """Más de `time.idle_cutoff_s` sin latir significa que el usuario no estaba."""
    acreditados, motivo = segundos_de_latido(60, 3600.0, cfg_tiempo)
    assert acreditados == 0
    assert motivo == "idle_gap"


def test_el_tiempo_por_actividad_se_limita_a_tres_veces_lo_estimado(cfg_tiempo):
    tope = tope_de_actividad(540, cfg_tiempo)
    assert tope == 1620
    acreditados, topado = acreditar_con_tope(1600, 60, tope)
    assert (acreditados, topado) == (20, True)
    acreditados, topado = acreditar_con_tope(1620, 60, tope)
    assert (acreditados, topado) == (0, True)
    assert acreditar_con_tope(100, 30, None) == (30, False)


# ---------------------------------------------------------------------------
# Sesiones en base de datos
# ---------------------------------------------------------------------------


def test_la_sesion_se_reutiliza_mientras_el_usuario_sigue_activo(
    db, config_sembrada, usuario
):
    servicio = ServicioSesiones(db)
    momento = utcnow()
    primera = servicio.abrir_sesion(usuario.id, ZONA_CHILE, device="android", ahora=momento)
    segunda = servicio.abrir_sesion(
        usuario.id, ZONA_CHILE, ahora=momento + timedelta(minutes=5)
    )
    assert primera.id == segunda.id


def test_tras_diez_minutos_de_inactividad_la_sesion_se_cierra_y_se_abre_otra(
    db, config_sembrada, usuario
):
    servicio = ServicioSesiones(db)
    momento = utcnow()
    primera = servicio.abrir_sesion(usuario.id, ZONA_CHILE, ahora=momento)
    segunda = servicio.abrir_sesion(
        usuario.id, ZONA_CHILE, ahora=momento + timedelta(minutes=11)
    )

    assert primera.id != segunda.id
    assert primera.ended_at is not None
    assert primera.end_reason == SessionEndReason.IDLE_TIMEOUT

    eventos = db.execute(
        sa.select(DomainEvent.event_type).where(DomainEvent.user_id == usuario.id)
    ).scalars().all()
    assert EventType.STUDY_SESSION_ENDED in eventos


def test_los_latidos_acumulan_tiempo_en_la_actividad_y_en_la_sesion(
    db, config_sembrada, usuario, contenido, abrir_actividad
):
    servicio = ServicioSesiones(db)
    momento = utcnow()
    sesion = servicio.abrir_sesion(usuario.id, ZONA_CHILE, ahora=momento)
    actividad = abrir_actividad(usuario, contenido, sesion_id=sesion.id, cuando=momento)

    for paso in range(1, 4):
        servicio.registrar_latido(
            actividad, 30, ahora=momento + timedelta(seconds=30 * paso)
        )

    assert actividad.active_seconds == 90
    assert actividad.reported_seconds == 90
    assert db.get(LearningSession, sesion.id).active_seconds == 90


def test_un_latido_fuera_de_una_actividad_abierta_se_rechaza(
    db, config_sembrada, usuario, contenido, abrir_actividad
):
    servicio = ServicioSesiones(db)
    actividad = abrir_actividad(usuario, contenido)
    actividad.status = AttemptStatus.SUBMITTED
    db.flush()

    with pytest.raises(AteneaError) as error:
        servicio.registrar_latido(actividad, 30)
    assert error.value.code == "ATTEMPT_NOT_OPEN"


def test_el_tiempo_de_la_actividad_no_supera_tres_veces_lo_estimado(
    db, config_sembrada, usuario, contenido, abrir_actividad
):
    servicio = ServicioSesiones(db)
    momento = utcnow()
    sesion = servicio.abrir_sesion(usuario.id, ZONA_CHILE, ahora=momento)
    actividad = abrir_actividad(usuario, contenido, sesion_id=sesion.id, cuando=momento)

    # La lección estima 540 s: el tope es 1 620 s aunque el cliente lata una hora.
    for paso in range(1, 60):
        servicio.registrar_latido(
            actividad, 60, ahora=momento + timedelta(seconds=60 * paso)
        )

    assert actividad.active_seconds == 1620
    assert actividad.reported_seconds > actividad.active_seconds


def test_acumular_horas_no_mueve_el_dominio_en_base_de_datos(
    db, config_sembrada, usuario, contenido, abrir_actividad
):
    """Prueba integrada del invariante de §1.1: el tiempo no otorga dominio."""
    sesiones = ServicioSesiones(db)
    dominio = ServicioDominio(db)
    momento = utcnow()

    sesion = sesiones.abrir_sesion(usuario.id, ZONA_CHILE, ahora=momento)
    actividad = abrir_actividad(usuario, contenido, sesion_id=sesion.id, cuando=momento)
    dominio.recalcular_cascada(
        usuario.id, topic_id=contenido.tema.id, ahora=momento, emitir_eventos=False
    )
    fila = db.execute(
        sa.select(UserTopicProgress).where(
            UserTopicProgress.user_id == usuario.id,
            UserTopicProgress.topic_id == contenido.tema.id,
        )
    ).scalar_one()
    antes = float(fila.mastery)
    area = db.execute(
        sa.select(UserAreaProgress).where(
            UserAreaProgress.user_id == usuario.id,
            UserAreaProgress.knowledge_area_id == contenido.area.id,
        )
    ).scalar_one()
    area_antes = float(area.mastery)

    for paso in range(1, 21):
        sesiones.registrar_latido(actividad, 60, ahora=momento + timedelta(seconds=60 * paso))
    actividad.status = AttemptStatus.SUBMITTED
    actividad.completed_at = momento + timedelta(minutes=25)
    sesiones.acumular_tiempo_de_actividad(actividad)
    dominio.recalcular_cascada(
        usuario.id,
        topic_id=contenido.tema.id,
        ahora=momento + timedelta(minutes=25),
        emitir_eventos=False,
    )
    db.refresh(fila)

    db.refresh(area)

    # 20 minutos de dedicación registrados y ni un punto de dominio nuevo.
    assert actividad.active_seconds > 0
    assert float(fila.mastery) == pytest.approx(antes)
    assert float(area.mastery) == pytest.approx(area_antes)
    assert area.study_seconds == actividad.active_seconds


def test_el_tiempo_se_agrega_por_tema_y_por_conocimiento(
    db, config_sembrada, usuario, contenido, abrir_actividad
):
    sesiones = ServicioSesiones(db)
    momento = utcnow()
    sesion = sesiones.abrir_sesion(usuario.id, ZONA_CHILE, ahora=momento)
    actividad = abrir_actividad(usuario, contenido, sesion_id=sesion.id, cuando=momento)
    sesiones.registrar_latido(actividad, 45, ahora=momento + timedelta(seconds=45))

    por_tema = sesiones.tiempo_por_tema(usuario.id)
    por_area = sesiones.tiempo_por_area(usuario.id)
    assert por_tema[contenido.tema.id] == 45
    assert por_area[contenido.area.id] == 45
