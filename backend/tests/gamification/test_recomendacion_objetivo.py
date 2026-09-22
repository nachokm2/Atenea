"""La recomendación adaptativa del objetivo diario (§6.11).

Todo lo de alrededor de esto ya estaba construido y sin usar: `GET /daily-goal`
sirve `recommendation`, `POST .../accept` y `POST .../dismiss` la aplican o la
descartan, el DTO del cliente y la tarjeta «El Reino te propone» ya existían.
Lo único que faltaba era que algo escribiera `daily_goals.recommendation`
alguna vez —nacía y moría en `{}`— y estas son las primeras pruebas de todo
`rachas.py`, que no tenía ninguna en el proyecto.
"""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.enums import GoalType
from app.models.gamification import DailyGoal, Streak, StreakDay
from app.models.identity import User
from app.modules.gamification import avisos, planificador, rachas
from app.modules.gamification.servicio_config import ServicioConfig

SANTIAGO = "America/Santiago"
HOY = dt.date(2026, 3, 16)  # un lunes, como llega desde el barrido


def _en(hora: dt.time, dia: dt.date = HOY) -> dt.datetime:
    """«Las `hora` del `dia` en Santiago», en UTC."""
    return avisos.instante_local(dia, hora, SANTIAGO)


def _racha(db: Session, usuario: User, *, inicio_hace_dias: int = 30) -> Streak:
    fila = Streak(
        user_id=usuario.id,
        started_on=HOY - dt.timedelta(days=inicio_hace_dias),
        last_active_date=HOY - dt.timedelta(days=1),
    )
    db.add(fila)
    db.flush()
    return fila


def _objetivo(
    db: Session,
    usuario: User,
    *,
    tipo: GoalType = GoalType.MINUTES,
    meta: int = 20,
    recommendation: dict | None = None,
    rechazada_hace_dias: int | None = None,
) -> DailyGoal:
    fila = DailyGoal(
        user_id=usuario.id,
        goal_type=tipo,
        target=meta,
        effective_from=HOY - dt.timedelta(days=60),
        recommendation=recommendation or {},
        recommendation_rejected_at=(
            None
            if rechazada_hace_dias is None
            # Mediodía UTC: en Santiago (UTC-3 o UTC-4 según horario de verano)
            # sigue siendo la misma fecha local, así que el cómputo de días no
            # se corre por culpa del huso.
            else dt.datetime.combine(
                HOY - dt.timedelta(days=rechazada_hace_dias),
                dt.time(12, 0),
                tzinfo=dt.UTC,
            )
        ),
    )
    db.add(fila)
    db.flush()
    return fila


def _dia(
    db: Session,
    usuario: User,
    fecha: dt.date,
    *,
    tipo: GoalType = GoalType.MINUTES,
    meta: int = 20,
    progreso: int = 0,
    cumplido: bool = False,
    xp: int = 0,
) -> StreakDay:
    fila = StreakDay(
        user_id=usuario.id,
        local_date=fecha,
        goal_type_snapshot=tipo,
        goal_target_snapshot=meta,
        goal_progress=progreso,
        goal_met_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC) if cumplido else None,
        educational_xp=xp,
    )
    db.add(fila)
    db.flush()
    return fila


def _ventana_perfecta(
    db: Session,
    usuario: User,
    *,
    dias_met: int,
    ratio: float,
    tipo: GoalType = GoalType.MINUTES,
    meta: int = 20,
) -> None:
    """Los `dias_met` días más recientes de la ventana, todos cumplidos con `ratio`."""
    for i in range(dias_met):
        fecha = HOY - dt.timedelta(days=1 + i)
        _dia(
            db,
            usuario,
            fecha,
            tipo=tipo,
            meta=meta,
            progreso=round(meta * ratio),
            cumplido=True,
            xp=100,
        )


def _evaluar(db: Session, cfg: ServicioConfig, usuario: User) -> bool:
    return rachas.evaluar_recomendacion_objetivo(db, cfg, usuario.id, HOY, SANTIAGO)


def _recomendacion(db: Session, usuario: User) -> dict:
    objetivo = db.execute(
        sa.select(DailyGoal).where(DailyGoal.user_id == usuario.id)
    ).scalar_one()
    return dict(objetivo.recommendation or {})


# ---------------------------------------------------------------------------
# Las tres direcciones
# ---------------------------------------------------------------------------


def test_sube_cuando_cumple_con_holgura(db: Session, cfg: ServicioConfig, usuario: User) -> None:
    """14 de 14 días cumplidos al 175 % de la meta: sube al siguiente peldaño.

    `goal.minutes.options = [10, 20, 30, 45]`: desde 20, el siguiente es 30.
    """
    _racha(db, usuario)
    _objetivo(db, usuario, tipo=GoalType.MINUTES, meta=20)
    _ventana_perfecta(db, usuario, dias_met=14, ratio=1.75, meta=20)

    assert _evaluar(db, cfg, usuario) is True
    reco = _recomendacion(db, usuario)
    assert reco["direction"] == "up"
    assert reco["suggested_type"] == "minutos"
    assert reco["suggested_target"] == 30
    assert reco["computed_on"] == HOY.isoformat()


def test_baja_cuando_cuesta_pero_sigue_apareciendo(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """3 días cumplidos, 5 más activos sin cumplir: baja al peldaño anterior.

    Ni «casi no aparece» (activos = 8, no < 4) ni «le sobra» (cumplidos = 3):
    la meta le queda grande, no la abandona.
    """
    _racha(db, usuario)
    _objetivo(db, usuario, tipo=GoalType.MINUTES, meta=20)
    for i in range(3):
        _dia(db, usuario, HOY - dt.timedelta(days=1 + i), meta=20, progreso=20, cumplido=True, xp=100)
    for i in range(3, 8):
        _dia(db, usuario, HOY - dt.timedelta(days=1 + i), meta=20, progreso=10, cumplido=False, xp=40)

    assert _evaluar(db, cfg, usuario) is True
    reco = _recomendacion(db, usuario)
    assert reco["direction"] == "down"
    assert reco["suggested_type"] == "minutos"
    assert reco["suggested_target"] == 10


def test_con_muy_poca_actividad_no_sugiere_un_numero_sino_el_suelo(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Menos de 4 días activos en 14: no «un poco menos», el suelo (§6.11).

    Con solo 2 datos de catorce, «bájale un peldaño» sería ruido. Se ofrece
    `actividades = 1`: cualquier cosa que haga ese día ya cuenta.
    """
    _racha(db, usuario)
    _objetivo(db, usuario, tipo=GoalType.MINUTES, meta=20)
    for i in range(2):
        _dia(db, usuario, HOY - dt.timedelta(days=1 + i), meta=20, progreso=5, cumplido=False, xp=10)

    assert _evaluar(db, cfg, usuario) is True
    reco = _recomendacion(db, usuario)
    assert reco["direction"] == "down"
    assert reco["suggested_type"] == "actividades"
    assert reco["suggested_target"] == 1


def test_la_zona_intermedia_no_propone_nada(db: Session, cfg: ServicioConfig, usuario: User) -> None:
    """8 de 14 cumplidos: ni tan pocos como para bajar, ni tantos como para subir."""
    _racha(db, usuario)
    _objetivo(db, usuario, tipo=GoalType.MINUTES, meta=20)
    for i in range(8):
        _dia(db, usuario, HOY - dt.timedelta(days=1 + i), meta=20, progreso=20, cumplido=True, xp=100)

    assert _evaluar(db, cfg, usuario) is False
    assert _recomendacion(db, usuario) == {}


# ---------------------------------------------------------------------------
# Las dos guardas de tiempo
# ---------------------------------------------------------------------------


def test_una_racha_mas_joven_que_la_ventana_no_opina_todavia(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Tres días perfectos no son evidencia de dos semanas.

    Sin esta guarda, un aprendiz de tres días activaría «pocos días activos»
    —3 de 14— y se le rebajaría el objetivo con media semana de datos.
    """
    _racha(db, usuario, inicio_hace_dias=3)
    _objetivo(db, usuario, tipo=GoalType.MINUTES, meta=20)
    _ventana_perfecta(db, usuario, dias_met=3, ratio=1.75, meta=20)

    assert _evaluar(db, cfg, usuario) is False
    assert _recomendacion(db, usuario) == {}


def test_el_enfriamiento_general_no_se_recalcula_cada_barrido(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Una recomendación calculada hace 5 días no se toca: `cooldown_days` es 14.

    Aunque la ventana de hoy pida claramente lo contrario (aquí calificaría
    para bajar), no se pisa la que ya está esperando respuesta.
    """
    _racha(db, usuario)
    _objetivo(
        db,
        usuario,
        tipo=GoalType.MINUTES,
        meta=20,
        recommendation={
            "direction": "up",
            "suggested_type": "minutos",
            "suggested_target": 30,
            "computed_on": (HOY - dt.timedelta(days=5)).isoformat(),
        },
    )
    for i in range(2):
        _dia(db, usuario, HOY - dt.timedelta(days=1 + i), meta=20, progreso=5, cumplido=False, xp=10)

    assert _evaluar(db, cfg, usuario) is False
    reco = _recomendacion(db, usuario)
    assert reco["suggested_target"] == 30, "se sobreescribió una recomendación aún dentro del enfriamiento"


def test_tras_un_rechazo_el_enfriamiento_es_el_doble_y_propio(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Rechazada hace 10 días: `rejected_cooldown_days` (28) sigue vigente.

    Quien acaba de decir que no, no quiere verla otra vez la semana que viene.
    """
    _racha(db, usuario)
    _objetivo(db, usuario, tipo=GoalType.MINUTES, meta=20, rechazada_hace_dias=10)
    _ventana_perfecta(db, usuario, dias_met=14, ratio=1.75, meta=20)

    assert _evaluar(db, cfg, usuario) is False
    assert _recomendacion(db, usuario) == {}


# ---------------------------------------------------------------------------
# Los bordes del cálculo
# ---------------------------------------------------------------------------


def test_los_dias_sin_actividad_cuentan_como_cero_no_se_descartan(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """12 días perfectos y 2 sin ninguna fila: el promedio se divide entre 14.

    12 días a razón 1.5 exacto —justo el umbral— más dos días sin fila. Dividido
    entre los 14 de la ventana, el promedio real es 12*1.5/14 ≈ 1.29, por debajo
    del umbral: no sube. Si se dividiera solo entre las filas que existen
    —12— saldría exactamente 1.5 y subiría por error: es la trampa que un
    aprendiz que casi no aparece explota sin querer.
    """
    _racha(db, usuario)
    _objetivo(db, usuario, tipo=GoalType.MINUTES, meta=20)
    _ventana_perfecta(db, usuario, dias_met=12, ratio=1.5, meta=20)
    # Los otros 2 días de la ventana deliberadamente sin fila.

    assert _evaluar(db, cfg, usuario) is False
    assert _recomendacion(db, usuario) == {}


def test_ya_en_el_peldano_mas_alto_no_hay_nada_que_subir(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """En 45 —el máximo de `goal.minutes.options`— «subir» no tiene a dónde ir."""
    _racha(db, usuario)
    _objetivo(db, usuario, tipo=GoalType.MINUTES, meta=45)
    _ventana_perfecta(db, usuario, dias_met=14, ratio=1.75, meta=45)

    assert _evaluar(db, cfg, usuario) is False
    assert _recomendacion(db, usuario) == {}


def test_si_la_sugerencia_coincide_con_lo_que_ya_tiene_no_hay_cambio_que_ofrecer(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Ya está en `actividades = 1`: el suelo del caso de muy poca actividad
    coincide con su objetivo vigente, y eso no es una propuesta."""
    _racha(db, usuario)
    _objetivo(db, usuario, tipo=GoalType.ACTIVITIES, meta=1)
    for i in range(2):
        _dia(
            db,
            usuario,
            HOY - dt.timedelta(days=1 + i),
            tipo=GoalType.ACTIVITIES,
            meta=1,
            progreso=0,
            cumplido=False,
            xp=5,
        )

    assert _evaluar(db, cfg, usuario) is False
    assert _recomendacion(db, usuario) == {}


# ---------------------------------------------------------------------------
# El barrido de verdad, no solo la función que decide
# ---------------------------------------------------------------------------
#
# Lo que corre en producción es `planificador.planificar()`, no
# `evaluar_recomendacion_objetivo` a pelo: el barrido es quien decide el
# CUÁNDO —solo lunes— y arma al candidato desde la fila real de `streaks`.
# Sin esto, la función podría estar perfecta y no dispararse nunca porque el
# barrido no llega a llamarla, que es exactamente el hueco que este trabajo
# vino a cerrar.


def test_el_barrido_del_lunes_escribe_la_recomendacion(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    _racha(db, usuario)
    _objetivo(db, usuario, tipo=GoalType.MINUTES, meta=20)
    _ventana_perfecta(db, usuario, dias_met=14, ratio=1.75, meta=20)

    cuenta = planificador.planificar(db, cfg, momento=_en(dt.time(19, 30)))

    assert cuenta["objetivos_recomendados"] == 1
    assert _recomendacion(db, usuario)["direction"] == "up"


def test_fuera_de_lunes_el_barrido_no_la_toca(
    db: Session, cfg: ServicioConfig, usuario: User
) -> None:
    """Mismos datos que arriba, un martes: el barrido ni lo intenta."""
    _racha(db, usuario)
    _objetivo(db, usuario, tipo=GoalType.MINUTES, meta=20)
    _ventana_perfecta(db, usuario, dias_met=14, ratio=1.75, meta=20)

    martes = HOY + dt.timedelta(days=1)
    cuenta = planificador.planificar(
        db, cfg, momento=avisos.instante_local(martes, dt.time(19, 30), SANTIAGO)
    )

    assert cuenta["objetivos_recomendados"] == 0
    assert _recomendacion(db, usuario) == {}
