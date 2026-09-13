"""Catálogo de eventos de dominio, payloads tipados y punto de entrada del bus.

Contrato §4: `domain_events` es el bus del MVP. Toda recompensa nace aquí:

    registrar_evento(db, usuario_id=…, tipo=…, payload=…, idempotency_key=…)

- **Idempotencia global** (§4.1 regla 1): `idempotency_key` es única. Si la clave
  ya existe, no se otorga nada y se devuelve el recibo reconstruido del evento
  original (§7.10 regla 4).
- El servidor calcula `occurred_at` (con la tolerancia de sincronización) y
  `local_date` con la zona horaria del usuario; ambos viajan con el evento para
  que todos los consumidores usen la misma fecha (§8.6).
- El catálogo de tipos es `EventType` (`app/models/enums.py`): aquí se reexporta
  y se añaden los modelos Pydantic de payload de los eventos que consume el motor.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type, datetime
from typing import Any

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import DEFAULT_TIMEZONE, resolve_occurred_at, user_local_date, utcnow
from app.models.enums import EventStatus, EventType
from app.models.gamification import (
    DomainEvent,
    Streak,
    StreakDay,
    UserAchievement,
    UserMission,
    XPTransaction,
)
from app.modules.gamification.recompensas import (
    AgregadorRecibo,
    MisionRecibo,
    ObjetivoDiarioRecibo,
    RachaRecibo,
    ReciboRecompensas,
)
from app.modules.gamification.servicio_config import ServicioConfig

#: Reexportado por comodidad: el catálogo cerrado de eventos vive en `enums.py`.
TipoEvento = EventType

#: Módulos productores admitidos en `domain_events.source_module` (§3.5).
MODULOS_PRODUCTORES: frozenset[str] = frozenset(
    {"identity", "content", "ingestion", "ai", "progress", "gamification", "economy", "client"}
)


# ---------------------------------------------------------------------------
# Payloads tipados (§4.2). `extra="allow"`: el contrato permite campos añadidos.
# ---------------------------------------------------------------------------


class PayloadEvento(BaseModel):
    """Base de todos los payloads: admite campos adicionales documentados en §4.2."""

    model_config = ConfigDict(extra="allow")

    counts_for_progress: bool = True


class PayloadLessonCompleted(PayloadEvento):
    """`LESSON_COMPLETED` (§4.2 · Aprendizaje)."""

    lesson_id: uuid.UUID | None = None
    study_activity_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None
    module_id: uuid.UUID | None = None
    path_id: uuid.UUID | None = None
    knowledge_area_id: uuid.UUID | None = None
    questions_total: int = 0
    questions_correct: int = 0
    accuracy_pct: float | None = None
    duration_s: int | None = None
    estimated_seconds: int | None = None
    completion_index: int = 1
    is_first_completion: bool = True
    is_low_content: bool = False


class PayloadQuestionAnswered(PayloadEvento):
    """`QUESTION_ANSWERED` (§4.2 · Aprendizaje)."""

    question_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None
    knowledge_area_id: uuid.UUID | None = None
    lesson_id: uuid.UUID | None = None
    study_activity_id: uuid.UUID | None = None
    assessment_attempt_id: uuid.UUID | None = None
    context: str | None = None
    attempt_no: int = 1
    is_correct: bool = False
    partial_score: float | None = None
    difficulty: str | None = None
    evaluation_method: str | None = None
    response_ms: int | None = None
    is_retry_of_failed: bool = False


class PayloadChallengeCompleted(PayloadEvento):
    """`CHALLENGE_COMPLETED` (§4.2 · Aprendizaje)."""

    study_activity_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None
    path_id: uuid.UUID | None = None
    knowledge_area_id: uuid.UUID | None = None
    passed: bool = False
    accuracy_pct: float | None = None
    duration_s: int | None = None
    estimated_seconds: int | None = None
    completion_index: int = 1


class PayloadReviewCompleted(PayloadEvento):
    """`REVIEW_COMPLETED` (§4.2 · Aprendizaje)."""

    study_activity_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None
    knowledge_area_id: uuid.UUID | None = None
    questions_total: int = 0
    questions_correct: int = 0
    accuracy_pct: float | None = None
    topic_was_weak: bool = False
    paid_reviews_today: int = 0


class PayloadAssessmentCompleted(PayloadEvento):
    """`ASSESSMENT_COMPLETED` (§4.2 · Aprendizaje)."""

    assessment_id: uuid.UUID | None = None
    attempt_id: uuid.UUID | None = None
    module_id: uuid.UUID | None = None
    path_id: uuid.UUID | None = None
    knowledge_area_id: uuid.UUID | None = None
    attempt_no: int = 1
    score_pct: float = 0.0
    effective_score_pct: float | None = None
    passed: bool = False
    outcome: str | None = None
    question_count: int | None = None
    duration_s: int | None = None


class PayloadModuleCompleted(PayloadEvento):
    """`MODULE_COMPLETED` (§4.2 · Aprendizaje)."""

    module_id: uuid.UUID | None = None
    module_index: int | None = None
    path_id: uuid.UUID | None = None
    knowledge_area_id: uuid.UUID | None = None


class PayloadPathCompleted(PayloadEvento):
    """`PATH_COMPLETED` (§4.2 · Aprendizaje)."""

    path_id: uuid.UUID | None = None
    knowledge_area_id: uuid.UUID | None = None
    modules: int | None = None
    days_elapsed: int | None = None


class PayloadStudyTimeTicked(PayloadEvento):
    """`STUDY_TIME_TICKED` (§4.2 · Aprendizaje)."""

    session_id: uuid.UUID | None = None
    study_activity_id: uuid.UUID | None = None
    activity_type: str | None = None
    seconds: int = 0


class PayloadCharacterCreated(PayloadEvento):
    """`CHARACTER_CREATED` (§4.2 · Identidad)."""

    character_id: uuid.UUID | None = None
    archetype: str | None = None
    name: str | None = None


class PayloadMissionClaimed(PayloadEvento):
    """`MISSION_CLAIMED` (§4.2 · Gamificación)."""

    user_mission_id: uuid.UUID
    auto: bool = False
    reward: dict[str, Any] = Field(default_factory=dict)


#: Modelo de payload por evento; los que no están aquí usan `PayloadEvento`.
PAYLOADS_POR_EVENTO: dict[EventType, type[PayloadEvento]] = {
    EventType.LESSON_COMPLETED: PayloadLessonCompleted,
    EventType.QUESTION_ANSWERED: PayloadQuestionAnswered,
    EventType.CHALLENGE_COMPLETED: PayloadChallengeCompleted,
    EventType.REVIEW_COMPLETED: PayloadReviewCompleted,
    EventType.ASSESSMENT_COMPLETED: PayloadAssessmentCompleted,
    EventType.MODULE_COMPLETED: PayloadModuleCompleted,
    EventType.PATH_COMPLETED: PayloadPathCompleted,
    EventType.STUDY_TIME_TICKED: PayloadStudyTimeTicked,
    EventType.CHARACTER_CREATED: PayloadCharacterCreated,
    EventType.MISSION_CLAIMED: PayloadMissionClaimed,
}


def validar_payload(tipo: EventType, payload: dict[str, Any] | None) -> dict[str, Any]:
    """Valida el payload con el modelo del evento y lo devuelve serializable a JSONB."""
    modelo = PAYLOADS_POR_EVENTO.get(tipo, PayloadEvento)
    validado = modelo.model_validate(dict(payload or {}))
    return validado.model_dump(mode="json", exclude_none=False)


# ---------------------------------------------------------------------------
# Persistencia del evento
# ---------------------------------------------------------------------------


def zona_horaria_de_usuario(db: Session, usuario_id: uuid.UUID | None) -> str:
    """Zona IANA del usuario (`users.timezone`), con importación perezosa (§8.6)."""
    if usuario_id is None:
        return DEFAULT_TIMEZONE
    from app.models.identity import User  # noqa: PLC0415 - evita el ciclo con app.models

    zona = db.execute(sa.select(User.timezone).where(User.id == usuario_id)).scalar()
    return str(zona or DEFAULT_TIMEZONE)


def buscar_por_clave(db: Session, idempotency_key: str) -> DomainEvent | None:
    """Devuelve el evento ya registrado con esa clave de idempotencia, si existe."""
    return db.execute(
        sa.select(DomainEvent).where(DomainEvent.idempotency_key == idempotency_key)
    ).scalar_one_or_none()


def crear_evento_dominio(
    db: Session,
    *,
    usuario_id: uuid.UUID | None,
    tipo: EventType,
    payload: dict[str, Any],
    idempotency_key: str,
    occurred_at: datetime | None = None,
    local_date: date_type | None = None,
    timezone: str | None = None,
    source_module: str = "gamification",
    correlation_id: uuid.UUID | None = None,
    causation_id: uuid.UUID | None = None,
    version: int = 1,
) -> DomainEvent | None:
    """Inserta una fila de `domain_events`. Devuelve `None` si la clave ya existía.

    No dispara el motor: es la primitiva que usan tanto `registrar_evento` como la
    emisión de eventos derivados de la cascada.
    """
    if source_module not in MODULOS_PRODUCTORES:
        source_module = "gamification"

    identificador = uuid.uuid4()
    evento = DomainEvent(
        id=identificador,
        event_type=tipo,
        user_id=usuario_id,
        occurred_at=occurred_at or utcnow(),
        local_date=local_date,
        timezone=timezone,
        version=version,
        source_module=source_module,
        payload=payload,
        correlation_id=correlation_id or identificador,
        causation_id=causation_id,
        processing_status=EventStatus.PENDING,
        idempotency_key=idempotency_key,
    )
    savepoint = db.begin_nested()
    try:
        db.add(evento)
        db.flush()
    except IntegrityError:
        savepoint.rollback()
        return None
    savepoint.commit()
    return evento


# ---------------------------------------------------------------------------
# Reconstrucción del recibo (idempotencia, §7.10 regla 4)
# ---------------------------------------------------------------------------


def _ids_de_la_cascada(db: Session, evento: DomainEvent) -> list[uuid.UUID]:
    """Ids del evento raíz y de todos los eventos derivados de su cascada."""
    raiz = evento.correlation_id or evento.id
    ids = list(
        db.execute(sa.select(DomainEvent.id).where(DomainEvent.correlation_id == raiz)).scalars().all()
    )
    if evento.id not in ids:
        ids.append(evento.id)
    return ids


def reconstruir_recibo(db: Session, evento: DomainEvent, cfg: ServicioConfig | None = None) -> ReciboRecompensas:
    """Reconstruye el recibo de un evento ya procesado, sin otorgar nada nuevo.

    Se apoya en los efectos persistidos (ledger de XP, ledger de oro de `economy`,
    misiones y logros tocados por la cascada), de modo que un reintento con la
    misma `Idempotency-Key` devuelve el mismo `receipt_id` y los mismos importes.
    """
    configuracion = cfg or ServicioConfig(db)
    agregador = AgregadorRecibo(
        receipt_id=evento.id,
        event_type=evento.event_type.value,
        occurred_at=evento.occurred_at,
    )
    agregador.config_version = configuracion.config_version()
    ids = _ids_de_la_cascada(db, evento)

    transacciones = list(
        db.execute(
            sa.select(XPTransaction)
            .where(XPTransaction.event_id.in_(ids))
            .order_by(XPTransaction.created_at)
        )
        .scalars()
        .all()
    )
    for transaccion in transacciones:
        agregador.sumar_xp(
            amount=int(transaccion.amount),
            base_amount=int(transaccion.base_amount),
            multiplier=transaccion.multiplier,
            reason_code=transaccion.reason_code,
            is_educational=bool(transaccion.is_educational),
            total_after=int(transaccion.balance_after),
            es_pregunta=transaccion.source.value == "question",
        )

    for fila in _transacciones_de_oro(db, ids):
        agregador.sumar_oro(
            amount=int(fila["amount"]), balance_after=fila.get("balance_after"), reason_code=fila["reason_code"]
        )

    if evento.user_id is not None:
        _reconstruir_estado(db, agregador, evento)

    return agregador.construir()


def _transacciones_de_oro(db: Session, ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    """Créditos de oro de la cascada (tabla de `economy`, lectura perezosa)."""
    try:
        from app.models.economy import GoldTransaction  # noqa: PLC0415
    except ImportError:  # pragma: no cover - `economy` siempre existe en el monolito
        return []
    filas = (
        db.execute(
            sa.select(GoldTransaction)
            .where(GoldTransaction.event_id.in_(ids))
            .order_by(GoldTransaction.created_at)
        )
        .scalars()
        .all()
    )
    return [
        {
            "amount": int(fila.amount),
            "balance_after": int(fila.balance_after),
            "reason_code": fila.reason_code,
        }
        for fila in filas
    ]


def _reconstruir_estado(db: Session, agregador: AgregadorRecibo, evento: DomainEvent) -> None:
    """Rellena racha, objetivo diario y misiones del recibo reconstruido."""
    ids = _ids_de_la_cascada(db, evento)

    racha = db.execute(sa.select(Streak).where(Streak.user_id == evento.user_id)).scalar_one_or_none()
    dia = None
    if evento.local_date is not None:
        dia = db.execute(
            sa.select(StreakDay).where(
                StreakDay.user_id == evento.user_id, StreakDay.local_date == evento.local_date
            )
        ).scalar_one_or_none()

    if racha is not None:
        agregador.streak = RachaRecibo(
            current=int(racha.current_length),
            best=int(racha.best_length),
            change=racha.last_change.value if racha.last_change else None,
            day_status=dia.day_status.value if dia else None,
            is_first_activity_of_day=False,
            milestone=None,
        )
    if dia is not None and dia.goal_type_snapshot is not None:
        agregador.daily_goal = ObjetivoDiarioRecibo(
            type=dia.goal_type_snapshot.value,
            target=int(dia.goal_target_snapshot or 0),
            progress=int(dia.goal_progress),
            met=dia.goal_met_at is not None,
            just_met=False,
        )

    for mision in (
        db.execute(sa.select(UserMission).where(UserMission.last_event_id.in_(ids))).scalars().all()
    ):
        agregador.agregar_mision(
            MisionRecibo(
                user_mission_id=mision.id,
                template_code=mision.template_code,
                title=mision.title,
                progress=int(mision.progress),
                target=int(mision.target),
                status=mision.status.value,
                reward={"xp": int(mision.reward_xp), "gold": int(mision.reward_gold)},
            )
        )

    logros_tocados = (
        db.execute(sa.select(UserAchievement).where(UserAchievement.last_event_id.in_(ids))).scalars().all()
    )
    for progreso in logros_tocados:
        for nivel in list(progreso.unlocked_tiers or []):
            agregador.agregar_logro(
                _logro_desde_registro(db, progreso.achievement_id, nivel)
            )


def _logro_desde_registro(db: Session, achievement_id: uuid.UUID, nivel: dict[str, Any]):
    """Construye la entrada de logro del recibo desde `unlocked_tiers`."""
    from app.models.gamification import Achievement  # noqa: PLC0415
    from app.modules.gamification.recompensas import LogroRecibo  # noqa: PLC0415

    logro = db.execute(sa.select(Achievement).where(Achievement.id == achievement_id)).scalar_one()
    return LogroRecibo(
        code=logro.code,
        name=logro.name,
        tier=str(nivel.get("tier", "single")),
        reward={
            "xp": int(nivel.get("reward_xp", 0) or 0),
            "gold": int(nivel.get("reward_gold", 0) or 0),
            "title_id": nivel.get("title_id"),
        },
    )


# ---------------------------------------------------------------------------
# Punto de entrada del bus
# ---------------------------------------------------------------------------


def registrar_evento(
    db: Session,
    *,
    usuario_id: uuid.UUID | None,
    tipo: EventType,
    payload: dict[str, Any] | None,
    idempotency_key: str,
    occurred_at: datetime | None = None,
    source_module: str = "progress",
    correlation_id: uuid.UUID | None = None,
    causation_id: uuid.UUID | None = None,
    version: int = 1,
    timezone: str | None = None,
    cfg: ServicioConfig | None = None,
) -> ReciboRecompensas:
    """Registra un evento de dominio y dispara el motor de gamificación.

    Es **idempotente**: si `idempotency_key` ya existe no se otorga nada y se
    devuelve el recibo del evento original (§4.1 regla 1 y §7.10 regla 4).
    """
    from app.modules.gamification import motor  # noqa: PLC0415 - evita el ciclo de importación

    configuracion = cfg or ServicioConfig(db)

    existente = buscar_por_clave(db, idempotency_key)
    if existente is not None:
        return reconstruir_recibo(db, existente, configuracion)

    zona = timezone or zona_horaria_de_usuario(db, usuario_id)
    tolerancia = configuracion.obtener_int("streak.sync_tolerance_min", 10)
    instante = resolve_occurred_at(occurred_at, tolerance_minutes=tolerancia)
    fecha_local = user_local_date(instante, zona)

    evento = crear_evento_dominio(
        db,
        usuario_id=usuario_id,
        tipo=tipo,
        payload=validar_payload(tipo, payload),
        idempotency_key=idempotency_key,
        occurred_at=instante,
        local_date=fecha_local,
        timezone=zona,
        source_module=source_module,
        correlation_id=correlation_id,
        causation_id=causation_id,
        version=version,
    )
    if evento is None:
        # Carrera: otro proceso insertó la misma clave entre la consulta y el INSERT.
        existente = buscar_por_clave(db, idempotency_key)
        if existente is None:  # pragma: no cover - imposible salvo borrado concurrente
            raise RuntimeError("No se pudo registrar el evento de dominio.")
        return reconstruir_recibo(db, existente, configuracion)

    recibo = motor.procesar_evento(db, evento, cfg=configuracion, timezone=zona)
    evento.processing_status = EventStatus.PROCESSED
    evento.processed_at = utcnow()
    db.flush()
    return recibo


__all__ = [
    "MODULOS_PRODUCTORES",
    "PAYLOADS_POR_EVENTO",
    "PayloadAssessmentCompleted",
    "PayloadChallengeCompleted",
    "PayloadCharacterCreated",
    "PayloadEvento",
    "PayloadLessonCompleted",
    "PayloadMissionClaimed",
    "PayloadModuleCompleted",
    "PayloadPathCompleted",
    "PayloadQuestionAnswered",
    "PayloadReviewCompleted",
    "PayloadStudyTimeTicked",
    "TipoEvento",
    "buscar_por_clave",
    "crear_evento_dominio",
    "reconstruir_recibo",
    "registrar_evento",
    "validar_payload",
    "zona_horaria_de_usuario",
]
