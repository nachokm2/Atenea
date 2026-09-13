"""Sesiones de estudio y contabilidad del tiempo (⏱ dedicación).

Contrato §3.4 (`learning_sessions`, `study_activities`), §5.6 (`time.*`) y §6.11.

Reglas del tiempo efectivo, literales del contrato:

* El cliente late cada `time.heartbeat_s` (30 s) mientras hay una actividad educativa
  en primer plano y hubo interacción en los últimos `time.idle_cutoff_s` (120 s).
* El servidor acepta **como máximo `time.max_tick_s` (60 s) por latido**.
* Descarta los latidos que **no** caen dentro de una actividad abierta.
* Limita el total por actividad a `time.max_activity_multiplier` (3×) su duración estimada.
* La sesión se cierra tras `time.session_idle_timeout_min` (10 min) de inactividad.

**Descarte de lagunas**: si entre dos latidos aceptados pasó más de `idle_cutoff_s`,
el usuario no estuvo presente en ese hueco. El latido tardío **re-ancla el reloj y no
acredita tiempo**; nunca se rellena la laguna. Además, un latido nunca acredita más
segundos de los que realmente transcurrieron desde el latido anterior.

**El tiempo no otorga dominio.** Este archivo escribe `active_seconds` y
`study_seconds`; jamás toca `mastery`, `practice_score` ni `coverage`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.errors import AteneaError
from app.core.time import ensure_utc, user_local_date, utcnow
from app.models.content import Lesson
from app.models.enums import AttemptStatus, EventType, SessionEndReason
from app.models.gamification import DomainEvent
from app.models.progress import (
    LearningSession,
    StudyActivity,
    UserAreaProgress,
    UserLessonProgress,
)
from app.modules.progress import LectorConfiguracion

#: Claves de `game_configs` que gobiernan el tiempo (§5.6).
CLAVES_TIEMPO: tuple[str, ...] = (
    "time.heartbeat_s",
    "time.max_tick_s",
    "time.idle_cutoff_s",
    "time.max_activity_multiplier",
    "time.session_idle_timeout_min",
)


@dataclass(frozen=True, slots=True)
class ConfigTiempo:
    """Instantánea de las claves `time.*` de `game_configs` (§5.6)."""

    heartbeat_s: int
    max_tick_s: int
    idle_cutoff_s: int
    max_activity_multiplier: int
    session_idle_timeout_min: int

    @classmethod
    def desde_lector(cls, cfg: LectorConfiguracion) -> ConfigTiempo:
        """Carga la configuración de tiempo en una sola consulta a `game_configs`."""
        valores = cfg.muchas(CLAVES_TIEMPO)
        return cls(
            heartbeat_s=int(valores["time.heartbeat_s"]),
            max_tick_s=int(valores["time.max_tick_s"]),
            idle_cutoff_s=int(valores["time.idle_cutoff_s"]),
            max_activity_multiplier=int(valores["time.max_activity_multiplier"]),
            session_idle_timeout_min=int(valores["time.session_idle_timeout_min"]),
        )


@dataclass(frozen=True, slots=True)
class ResultadoLatido:
    """Lo que devuelve un latido: segundos acreditados y acumulados."""

    acreditados: int
    reportados: int
    active_seconds: int
    session_active_seconds: int
    descartado: bool
    motivo: str | None


# ---------------------------------------------------------------------------
# Funciones puras
# ---------------------------------------------------------------------------


def tope_de_actividad(estimated_seconds: int | None, cfg: ConfigTiempo) -> int | None:
    """`max_activity_multiplier × duración estimada`; `None` si no hay estimación."""
    if not estimated_seconds or estimated_seconds <= 0:
        return None
    return int(estimated_seconds) * cfg.max_activity_multiplier


def segundos_de_latido(
    reportados: int,
    segundos_desde_ultimo_latido: float | None,
    cfg: ConfigTiempo,
) -> tuple[int, str | None]:
    """Segundos que el servidor acredita por un latido, y el motivo del recorte.

    Reglas (§6.11): tope de `max_tick_s` por latido, nunca más de lo realmente
    transcurrido y **descarte total de la laguna** si el hueco supera `idle_cutoff_s`.
    """
    reportados = max(0, int(reportados))
    if reportados == 0:
        return 0, "sin_tiempo"

    aceptados = min(reportados, cfg.max_tick_s)
    motivo = "tick_cap" if reportados > cfg.max_tick_s else None

    if segundos_desde_ultimo_latido is not None:
        hueco = max(0.0, float(segundos_desde_ultimo_latido))
        if hueco > cfg.idle_cutoff_s:
            # Laguna: el usuario no estuvo presente. El latido re-ancla el reloj.
            return 0, "idle_gap"
        if hueco < aceptados:
            aceptados = int(hueco)
            motivo = motivo or "gap_cap"

    return max(0, aceptados), motivo


def acreditar_con_tope(
    acumulados: int, candidatos: int, tope: int | None
) -> tuple[int, bool]:
    """Recorta los segundos candidatos al tope de la actividad (3× lo estimado)."""
    if candidatos <= 0:
        return 0, False
    if tope is None:
        return candidatos, False
    restante = max(0, tope - max(0, acumulados))
    if candidatos <= restante:
        return candidatos, False
    return restante, True


# ---------------------------------------------------------------------------
# Servicio
# ---------------------------------------------------------------------------


class ServicioSesiones:
    """Apertura, latidos y cierre de `learning_sessions`, y acumulación de tiempo."""

    def __init__(
        self,
        db: Session,
        cfg: ConfigTiempo | None = None,
        *,
        lector: LectorConfiguracion | None = None,
    ) -> None:
        self.db = db
        self.lector = lector or LectorConfiguracion(db)
        self.cfg = cfg or ConfigTiempo.desde_lector(self.lector)

    # -- apertura y cierre ------------------------------------------------

    def sesion_abierta(
        self, user_id: uuid.UUID, *, ahora: datetime | None = None
    ) -> LearningSession | None:
        """Última sesión sin cerrar del usuario cuyo latido sigue dentro del umbral.

        Índice usado: `ix_learning_sessions_user_id_started_at`.
        """
        momento = ensure_utc(ahora) if ahora else utcnow()
        sesion = self.db.execute(
            sa.select(LearningSession)
            .where(LearningSession.user_id == user_id, LearningSession.ended_at.is_(None))
            .order_by(LearningSession.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if sesion is None:
            return None
        limite = timedelta(minutes=self.cfg.session_idle_timeout_min)
        if momento - ensure_utc(sesion.last_heartbeat_at) > limite:
            self.cerrar_sesion(sesion, SessionEndReason.IDLE_TIMEOUT, ahora=momento)
            return None
        return sesion

    def abrir_sesion(
        self,
        user_id: uuid.UUID,
        timezone_name: str,
        *,
        device: str | None = None,
        ahora: datetime | None = None,
    ) -> LearningSession:
        """Devuelve la sesión abierta o crea una nueva ventana de actividad.

        Cierra por `idle_timeout` la sesión anterior si el usuario estuvo ausente más
        de `time.session_idle_timeout_min`.
        """
        momento = ensure_utc(ahora) if ahora else utcnow()
        existente = self.sesion_abierta(user_id, ahora=momento)
        if existente is not None:
            existente.last_heartbeat_at = momento
            self.db.flush()
            return existente

        sesion = LearningSession(
            user_id=user_id,
            started_at=momento,
            last_heartbeat_at=momento,
            active_seconds=0,
            local_date=user_local_date(momento, timezone_name),
            device=device,
        )
        self.db.add(sesion)
        self.db.flush()
        return sesion

    def cerrar_sesion(
        self,
        sesion: LearningSession,
        motivo: SessionEndReason,
        *,
        ahora: datetime | None = None,
        timezone_name: str | None = None,
    ) -> LearningSession:
        """Cierra la sesión y emite `STUDY_SESSION_ENDED` (§4.2)."""
        if sesion.ended_at is not None:
            return sesion
        momento = ensure_utc(ahora) if ahora else utcnow()
        sesion.ended_at = momento
        sesion.end_reason = motivo
        self.db.flush()
        self._emitir(
            EventType.STUDY_SESSION_ENDED,
            sesion.user_id,
            {
                "session_id": str(sesion.id),
                "active_seconds": int(sesion.active_seconds),
                "end_reason": motivo.value,
            },
            clave=f"study-session-ended:{sesion.user_id}:{sesion.id}:1",
            momento=momento,
            timezone_name=timezone_name,
        )
        return sesion

    def cerrar_sesiones_inactivas(
        self, user_id: uuid.UUID, *, ahora: datetime | None = None
    ) -> int:
        """Cierra por inactividad las sesiones abiertas del usuario. Devuelve cuántas."""
        momento = ensure_utc(ahora) if ahora else utcnow()
        limite = momento - timedelta(minutes=self.cfg.session_idle_timeout_min)
        sesiones = list(
            self.db.execute(
                sa.select(LearningSession).where(
                    LearningSession.user_id == user_id,
                    LearningSession.ended_at.is_(None),
                    LearningSession.last_heartbeat_at < limite,
                )
            ).scalars()
        )
        for sesion in sesiones:
            self.cerrar_sesion(sesion, SessionEndReason.IDLE_TIMEOUT, ahora=momento)
        return len(sesiones)

    # -- latidos ----------------------------------------------------------

    def registrar_latido(
        self,
        actividad: StudyActivity,
        segundos: int,
        *,
        ahora: datetime | None = None,
        timezone_name: str | None = None,
        emitir_evento: bool = True,
    ) -> ResultadoLatido:
        """Acredita el tiempo efectivo de un latido sobre una actividad abierta.

        Lanza `ATTEMPT_NOT_OPEN` (409) si la actividad ya no está en curso: el
        contrato exige descartar los latidos fuera de una actividad abierta.
        """
        momento = ensure_utc(ahora) if ahora else utcnow()
        if actividad.status != AttemptStatus.IN_PROGRESS:
            raise AteneaError(code="ATTEMPT_NOT_OPEN")

        sesion = (
            self.db.get(LearningSession, actividad.session_id)
            if actividad.session_id
            else None
        )
        referencia = (
            ensure_utc(sesion.last_heartbeat_at) if sesion is not None else ensure_utc(actividad.started_at)
        )
        hueco = (momento - referencia).total_seconds()

        candidatos, motivo = segundos_de_latido(segundos, hueco, self.cfg)
        tope = tope_de_actividad(self._estimacion_de_actividad(actividad), self.cfg)
        acreditados, topado = acreditar_con_tope(int(actividad.active_seconds), candidatos, tope)
        if topado:
            motivo = "activity_cap"

        actividad.reported_seconds = int(actividad.reported_seconds) + max(0, int(segundos))
        actividad.active_seconds = int(actividad.active_seconds) + acreditados
        if sesion is not None:
            sesion.active_seconds = int(sesion.active_seconds) + acreditados
            sesion.last_heartbeat_at = momento
        self.db.flush()

        if emitir_evento and acreditados > 0:
            # El tiempo de estudio no solo se registra: alimenta el agregado del
            # día y, con él, el objetivo diario en minutos y la racha. Por eso
            # este evento pasa por el motor de gamificación y no se limita a
            # insertar la fila, como sí hacen los eventos meramente analíticos.
            from app.modules.gamification import (  # noqa: PLC0415 - cruce perezoso entre módulos (§1.3)
                eventos as eventos_gamificacion,
            )

            eventos_gamificacion.registrar_evento(
                self.db,
                usuario_id=actividad.user_id,
                tipo=EventType.STUDY_TIME_TICKED,
                payload={
                    "session_id": str(actividad.session_id) if actividad.session_id else None,
                    "study_activity_id": str(actividad.id),
                    "activity_type": actividad.activity_type.value,
                    "seconds": acreditados,
                },
                idempotency_key=(
                    f"study-time-ticked:{actividad.user_id}:{actividad.id}:"
                    f"{int(momento.timestamp())}"
                ),
                occurred_at=momento,
                source_module="progress",
                timezone=timezone_name,
            )

        return ResultadoLatido(
            acreditados=acreditados,
            reportados=max(0, int(segundos)),
            active_seconds=int(actividad.active_seconds),
            session_active_seconds=int(sesion.active_seconds) if sesion is not None else 0,
            descartado=acreditados == 0,
            motivo=motivo,
        )

    # -- acumulación por tema y por área ----------------------------------

    def acumular_tiempo_de_actividad(self, actividad: StudyActivity) -> None:
        """Reparte `active_seconds` de la actividad a la lección y al conocimiento.

        El tiempo por **tema** y por **módulo** se deriva por consulta desde
        `study_activities` (no hay columna que duplicar); el tiempo por
        **conocimiento** sí se materializa en `user_area_progress.study_seconds`
        porque el perfil (P17) lo pide en cada carga.

        No altera ninguna columna de dominio: el tiempo mide dedicación (§1.1).
        """
        segundos = int(actividad.active_seconds)
        if segundos <= 0:
            return

        if actividad.lesson_id is not None:
            fila = self.db.execute(
                sa.select(UserLessonProgress).where(
                    UserLessonProgress.user_id == actividad.user_id,
                    UserLessonProgress.lesson_id == actividad.lesson_id,
                )
            ).scalar_one_or_none()
            if fila is not None:
                fila.active_seconds = int(fila.active_seconds) + segundos

        if actividad.knowledge_area_id is not None:
            area = self.db.execute(
                sa.select(UserAreaProgress).where(
                    UserAreaProgress.user_id == actividad.user_id,
                    UserAreaProgress.knowledge_area_id == actividad.knowledge_area_id,
                )
            ).scalar_one_or_none()
            if area is None:
                area = UserAreaProgress(
                    user_id=actividad.user_id,
                    knowledge_area_id=actividad.knowledge_area_id,
                )
                self.db.add(area)
                self.db.flush()
            area.study_seconds = int(area.study_seconds) + segundos
            area.last_activity_at = ensure_utc(actividad.completed_at or utcnow())
        self.db.flush()

    def tiempo_por_tema(
        self, user_id: uuid.UUID, *, topic_ids: list[uuid.UUID] | None = None
    ) -> dict[uuid.UUID, int]:
        """Segundos efectivos acumulados por tema (`study_activities.active_seconds`)."""
        stmt = (
            sa.select(StudyActivity.topic_id, sa.func.sum(StudyActivity.active_seconds))
            .where(StudyActivity.user_id == user_id, StudyActivity.topic_id.is_not(None))
            .group_by(StudyActivity.topic_id)
        )
        if topic_ids:
            stmt = stmt.where(StudyActivity.topic_id.in_(topic_ids))
        return {tid: int(total or 0) for tid, total in self.db.execute(stmt)}

    def tiempo_por_area(self, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Segundos efectivos acumulados por conocimiento."""
        stmt = (
            sa.select(
                StudyActivity.knowledge_area_id, sa.func.sum(StudyActivity.active_seconds)
            )
            .where(
                StudyActivity.user_id == user_id,
                StudyActivity.knowledge_area_id.is_not(None),
            )
            .group_by(StudyActivity.knowledge_area_id)
        )
        return {aid: int(total or 0) for aid, total in self.db.execute(stmt)}

    # -- internos ---------------------------------------------------------

    def _estimacion_de_actividad(self, actividad: StudyActivity) -> int | None:
        """Duración estimada de la actividad, base del tope de 3×."""
        if actividad.lesson_id is None:
            return None
        return self.db.execute(
            sa.select(Lesson.estimated_seconds).where(Lesson.id == actividad.lesson_id)
        ).scalar_one_or_none()

    def _emitir(
        self,
        event_type: EventType,
        user_id: uuid.UUID,
        payload: dict,
        *,
        clave: str,
        momento: datetime,
        timezone_name: str | None = None,
    ) -> None:
        """Inserta el evento de dominio si su clave de idempotencia es nueva (§8.3)."""
        existe = self.db.execute(
            sa.select(sa.literal(1))
            .select_from(DomainEvent)
            .where(DomainEvent.idempotency_key == clave)
            .limit(1)
        ).scalar_one_or_none()
        if existe:
            return
        self.db.add(
            DomainEvent(
                event_type=event_type,
                user_id=user_id,
                occurred_at=momento,
                timezone=timezone_name,
                source_module="progress",
                payload=payload,
                idempotency_key=clave,
            )
        )
        self.db.flush()


__all__ = [
    "CLAVES_TIEMPO",
    "ConfigTiempo",
    "ResultadoLatido",
    "ServicioSesiones",
    "acreditar_con_tope",
    "segundos_de_latido",
    "tope_de_actividad",
]
