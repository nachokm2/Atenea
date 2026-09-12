"""Otorgamiento de XP con las reglas anti-abuso del contrato (§6.2 y §6.9).

Todo el XP del juego pasa por aquí y se escribe en el ledger append-only
`xp_transactions`, que es la única fuente de verdad de la ⭐. La misma transacción
alimenta el XP global y el XP del conocimiento (`knowledge_area_id`).

Reglas implementadas, literalmente como en §6.2/§6.9:

- **A1** XP completo solo la primera vez: multiplicadores `xp.repeat_multipliers`
  (`[1.0, 0.2, 0.0]`) por número de finalización.
- **A2** XP por pregunta solo dentro de una actividad abierta.
- **A3** tope de XP por preguntas por lección (`xp.question_cap_per_lesson`).
- **A4** tiempo mínimo plausible (`xp.min_time.*`), con relojes del servidor.
- **A5** topes diarios blandos (`xp.daily_softcap`) sobre el XP **base de
  actividades** del día local.
- **A6** idempotencia por `(user_id, idempotency_key)`.
- **A8** contenido trivial: `xp.low_content_multiplier`.
- **D4** sin multiplicador de racha (`xp.streak_multiplier.enabled = false`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date as date_type
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.enums import EventType, XPSource
from app.models.gamification import DomainEvent, XPTransaction
from app.modules.gamification.servicio_config import ServicioConfig

# --- Códigos de motivo del contrato (§3.5 `xp_transactions.reason_code`) ----
RAZON_PRIMERA_VEZ = "first_completion"
RAZON_REPETICION_20 = "repeat_20"
RAZON_REPETICION_0 = "repeat_0"
RAZON_PREGUNTA_1 = "question_first_try"
RAZON_PREGUNTA_2 = "question_second_try"
RAZON_PREGUNTA_TOPE = "question_cap_reached"
RAZON_PREGUNTA_SIN_INTENTO = "question_no_attempt"
RAZON_TIEMPO_CORTO = "time_too_short"
RAZON_RESPUESTA_RAPIDA = "answer_too_fast"
RAZON_TOPE_50 = "daily_softcap_50"
RAZON_TOPE_10 = "daily_softcap_10"
RAZON_CONTENIDO_POBRE = "low_content_50"
RAZON_AJUSTE = "admin_adjustment"

#: Fuentes de XP que son **actividades** de aprendizaje: son las que cuentan para
#: el tope diario blando (§6.9 A5, que excluye misiones, hitos y logros).
FUENTES_ACTIVIDAD: frozenset[XPSource] = frozenset(
    {
        XPSource.LESSON,
        XPSource.QUESTION,
        XPSource.CHALLENGE,
        XPSource.ASSESSMENT,
        XPSource.MODULE,
        XPSource.PATH,
        XPSource.REVIEW,
    }
)

#: Claves de `xp.min_time.*` por tipo de actividad.
CLAVE_TIEMPO_MINIMO: dict[str, str] = {
    "lesson": "xp.min_time.lesson",
    "challenge": "xp.min_time.challenge",
}


@dataclass(frozen=True, slots=True)
class CalculoXP:
    """Resultado del cálculo de una transacción de XP, con su trazabilidad."""

    amount: int
    base_amount: int
    multiplier: Decimal
    reason_code: str

    @property
    def paga(self) -> bool:
        """Indica si la transacción otorga algo."""
        return self.amount > 0


# ---------------------------------------------------------------------------
# Multiplicadores (§6.2)
# ---------------------------------------------------------------------------


def multiplicador_repeticion(cfg: ServicioConfig, completion_index: int | None) -> tuple[Decimal, str]:
    """A1 · Multiplicador por número de finalización y su `reason_code`."""
    multiplicadores = cfg.obtener_lista("xp.repeat_multipliers")
    indice = max(1, int(completion_index or 1))
    posicion = min(indice, len(multiplicadores)) - 1
    valor = Decimal(str(multiplicadores[posicion]))
    if indice <= 1:
        return valor, RAZON_PRIMERA_VEZ
    if valor == 0:
        return valor, RAZON_REPETICION_0
    return valor, RAZON_REPETICION_20


def multiplicador_contenido(cfg: ServicioConfig, is_low_content: bool) -> Decimal:
    """A8 · Las lecciones de material insuficiente pagan la fracción configurada."""
    if not is_low_content:
        return Decimal("1")
    return cfg.obtener_decimal("xp.low_content_multiplier")


def multiplicador_racha(cfg: ServicioConfig) -> Decimal:
    """D4 · El MVP no tiene multiplicador de XP por racha; la clave queda abierta."""
    parametros = cfg.obtener_json("xp.streak_multiplier")
    if not parametros.get("enabled"):
        return Decimal("1")
    return Decimal(str(parametros.get("multiplier", 1)))


def multiplicador_tope_diario(cfg: ServicioConfig, base_acumulado_del_dia: int) -> tuple[Decimal, str | None]:
    """A5 · Tope diario blando sobre el XP base de actividades del día local."""
    tramos = cfg.obtener_lista("xp.daily_softcap")
    multiplicador = Decimal("1")
    razon: str | None = None
    for tramo in tramos:
        limite = int(tramo["limit"])
        if base_acumulado_del_dia > limite:
            multiplicador = Decimal(str(tramo["mult"]))
            razon = RAZON_TOPE_50 if multiplicador >= Decimal("0.5") else RAZON_TOPE_10
    return multiplicador, razon


def tiempo_minimo_requerido(
    cfg: ServicioConfig,
    tipo_actividad: str,
    *,
    estimated_seconds: int | None = None,
    question_count: int | None = None,
) -> int:
    """A4 · Segundos mínimos plausibles de una actividad (`max(abs, ratio × est.)`)."""
    if tipo_actividad == "assessment":
        por_pregunta = cfg.obtener_int("xp.min_time.assessment_per_question")
        return por_pregunta * int(question_count or 0)
    clave = CLAVE_TIEMPO_MINIMO.get(tipo_actividad)
    if clave is None:
        return 0
    parametros = cfg.obtener_json(clave)
    absoluto = int(parametros.get("abs_seconds", 0))
    ratio = Decimal(str(parametros.get("ratio", 0)))
    proporcional = int(ratio * Decimal(int(estimated_seconds or 0)))
    return max(absoluto, proporcional)


def tiempo_plausible(
    cfg: ServicioConfig,
    tipo_actividad: str,
    duracion_s: int | None,
    *,
    estimated_seconds: int | None = None,
    question_count: int | None = None,
) -> bool:
    """A4 · `True` si la duración observada alcanza el mínimo plausible."""
    minimo = tiempo_minimo_requerido(
        cfg, tipo_actividad, estimated_seconds=estimated_seconds, question_count=question_count
    )
    if minimo <= 0:
        return True
    return int(duracion_s or 0) >= minimo


# ---------------------------------------------------------------------------
# Cálculo (§6.2)
# ---------------------------------------------------------------------------


def calcular_xp(
    cfg: ServicioConfig,
    *,
    base: int,
    completion_index: int | None = 1,
    is_low_content: bool = False,
    base_acumulado_del_dia: int = 0,
    aplica_repeticion: bool = True,
    aplica_tope_diario: bool = True,
    tiempo_ok: bool = True,
    razon_forzada: str | None = None,
) -> CalculoXP:
    """Implementa `compute_xp` de §6.2 tal cual está escrito en el contrato."""
    if razon_forzada is not None:
        return CalculoXP(amount=0, base_amount=int(base), multiplier=Decimal("0"), reason_code=razon_forzada)

    if not tiempo_ok:
        # La actividad se marca completada igual; simplemente no paga.
        return CalculoXP(
            amount=0, base_amount=int(base), multiplier=Decimal("0"), reason_code=RAZON_TIEMPO_CORTO
        )

    if aplica_repeticion:
        m_repeat, razon = multiplicador_repeticion(cfg, completion_index)
    else:
        m_repeat, razon = Decimal("1"), RAZON_PRIMERA_VEZ
    if m_repeat == 0:
        return CalculoXP(amount=0, base_amount=int(base), multiplier=Decimal("0"), reason_code=razon)

    m_content = multiplicador_contenido(cfg, is_low_content)
    if m_content != 1:
        razon = RAZON_CONTENIDO_POBRE

    m_streak = multiplicador_racha(cfg)

    if aplica_tope_diario:
        m_cap, razon_cap = multiplicador_tope_diario(cfg, base_acumulado_del_dia)
    else:
        m_cap, razon_cap = Decimal("1"), None
    if razon_cap is not None:
        razon = razon_cap

    multiplicador = m_repeat * m_content * m_streak * m_cap
    bruto = Decimal(int(base)) * multiplicador
    monto = int(bruto.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return CalculoXP(
        amount=max(0, monto),
        base_amount=int(base),
        multiplier=multiplicador.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        reason_code=razon,
    )


def calcular_xp_pregunta(
    cfg: ServicioConfig,
    *,
    attempt_no: int,
    is_correct: bool,
    response_ms: int | None,
    actividad_abierta: bool = True,
    xp_preguntas_ya_pagado: int = 0,
) -> CalculoXP:
    """XP de una respuesta dentro de una lección (§6.2, reglas A2 y A3).

    1.er intento correcto paga `xp.question_first_try`; el 2.º,
    `xp.question_second_try`; del 3.º en adelante, 0. Una respuesta más rápida que
    `xp.min_time.answer_ms` no paga (la evidencia sí se registra para dominio) y
    el tope por lección es `xp.question_cap_per_lesson`.
    """
    if not actividad_abierta:
        return CalculoXP(0, 0, Decimal("0"), RAZON_PREGUNTA_SIN_INTENTO)

    if not is_correct:
        return CalculoXP(0, 0, Decimal("0"), RAZON_PREGUNTA_1 if attempt_no <= 1 else RAZON_PREGUNTA_2)

    minimo_ms = cfg.obtener_int("xp.min_time.answer_ms")
    if response_ms is not None and int(response_ms) < minimo_ms:
        return CalculoXP(0, 0, Decimal("0"), RAZON_RESPUESTA_RAPIDA)

    if attempt_no <= 1:
        base, razon = cfg.obtener_int("xp.question_first_try"), RAZON_PREGUNTA_1
    elif attempt_no == 2:
        base, razon = cfg.obtener_int("xp.question_second_try"), RAZON_PREGUNTA_2
    else:
        return CalculoXP(0, 0, Decimal("0"), RAZON_PREGUNTA_2)

    tope = cfg.obtener_int("xp.question_cap_per_lesson")
    disponible = max(0, tope - int(xp_preguntas_ya_pagado))
    if disponible <= 0:
        return CalculoXP(0, base, Decimal("0"), RAZON_PREGUNTA_TOPE)
    if base > disponible:
        return CalculoXP(disponible, base, Decimal("1.000"), RAZON_PREGUNTA_TOPE)
    return CalculoXP(base, base, Decimal("1.000"), razon)


def calcular_xp_repaso(cfg: ServicioConfig, *, aciertos: int, repasos_pagados_hoy: int) -> CalculoXP:
    """XP de un repaso: base + `min(aciertos × por_acierto, tope)` (§6.2)."""
    maximo_pagados = cfg.obtener_int("xp.review_max_paid_per_day")
    if int(repasos_pagados_hoy) >= maximo_pagados:
        return CalculoXP(0, 0, Decimal("0"), RAZON_REPETICION_0)
    base = cfg.obtener_int("xp.review_completed")
    por_acierto = cfg.obtener_int("xp.review_per_correct")
    tope = cfg.obtener_int("xp.review_correct_cap")
    total = base + min(int(aciertos) * por_acierto, tope)
    return CalculoXP(total, total, Decimal("1.000"), RAZON_PRIMERA_VEZ)


# ---------------------------------------------------------------------------
# Consultas al ledger
# ---------------------------------------------------------------------------


def xp_total(db: Session, usuario_id: uuid.UUID) -> int:
    """XP global acumulado del usuario (suma del ledger)."""
    return int(
        db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(XPTransaction.amount), 0)).where(
                XPTransaction.user_id == usuario_id
            )
        ).scalar()
        or 0
    )


def xp_de_conocimiento(db: Session, usuario_id: uuid.UUID, knowledge_area_id: uuid.UUID) -> int:
    """XP acumulado del usuario en un conocimiento (§3.5: la misma fila alimenta ambos)."""
    return int(
        db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(XPTransaction.amount), 0)).where(
                XPTransaction.user_id == usuario_id,
                XPTransaction.knowledge_area_id == knowledge_area_id,
            )
        ).scalar()
        or 0
    )


def xp_base_actividades_del_dia(db: Session, usuario_id: uuid.UUID, local_date: date_type) -> int:
    """XP **base** de actividades del día local: la magnitud del tope blando A5."""
    return int(
        db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(XPTransaction.base_amount), 0)).where(
                XPTransaction.user_id == usuario_id,
                XPTransaction.local_date == local_date,
                XPTransaction.source.in_(list(FUENTES_ACTIVIDAD)),
            )
        ).scalar()
        or 0
    )


def xp_preguntas_de_leccion(db: Session, usuario_id: uuid.UUID, lesson_id: uuid.UUID) -> int:
    """XP ya pagado por preguntas de una lección concreta (tope A3).

    Se cruza el ledger con el evento que originó cada transacción, porque la
    lección viaja en el payload de `QUESTION_ANSWERED`.
    """
    return int(
        db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(XPTransaction.amount), 0))
            .join(DomainEvent, DomainEvent.id == XPTransaction.event_id)
            .where(
                XPTransaction.user_id == usuario_id,
                XPTransaction.source == XPSource.QUESTION,
                DomainEvent.payload["lesson_id"].astext == str(lesson_id),
            )
        ).scalar()
        or 0
    )


def repasos_pagados_hoy(db: Session, usuario_id: uuid.UUID, local_date: date_type) -> int:
    """Número de repasos remunerados del día local (`xp.review_max_paid_per_day`)."""
    return int(
        db.execute(
            sa.select(sa.func.count())
            .select_from(XPTransaction)
            .where(
                XPTransaction.user_id == usuario_id,
                XPTransaction.local_date == local_date,
                XPTransaction.source == XPSource.REVIEW,
                XPTransaction.amount > 0,
            )
        ).scalar()
        or 0
    )


# ---------------------------------------------------------------------------
# Escritura en el ledger
# ---------------------------------------------------------------------------


def otorgar_xp(
    db: Session,
    cfg: ServicioConfig,
    *,
    usuario_id: uuid.UUID,
    calculo: CalculoXP,
    event_type: EventType,
    source: XPSource,
    local_date: date_type,
    idempotency_key: str,
    event_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    knowledge_area_id: uuid.UUID | None = None,
    topic_id: uuid.UUID | None = None,
    is_educational: bool = True,
) -> XPTransaction | None:
    """Escribe una fila del ledger de XP de forma idempotente.

    Devuelve la fila insertada, o `None` si la clave de idempotencia ya existía
    (en cuyo caso no se otorga nada nuevo, regla A6). Las transacciones de 0 XP
    **sí** se registran: son la respuesta a "¿por qué no gané XP?".
    """
    saldo_previo = xp_total(db, usuario_id)
    valores: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": usuario_id,
        "event_id": event_id,
        "event_type": event_type,
        "source": source,
        "source_id": source_id,
        "knowledge_area_id": knowledge_area_id,
        "topic_id": topic_id,
        "is_educational": is_educational,
        "base_amount": int(calculo.base_amount),
        "multiplier": calculo.multiplier,
        "amount": int(calculo.amount),
        "reason_code": calculo.reason_code,
        "config_version": cfg.config_version(),
        "balance_after": saldo_previo + int(calculo.amount),
        "local_date": local_date,
        "idempotency_key": idempotency_key,
    }
    sentencia = (
        pg_insert(XPTransaction)
        .values(**valores)
        .on_conflict_do_nothing(index_elements=["user_id", "idempotency_key"])
        .returning(XPTransaction.id)
    )
    insertado = db.execute(sentencia).scalar_one_or_none()
    if insertado is None:
        return None
    db.flush()
    return db.execute(sa.select(XPTransaction).where(XPTransaction.id == insertado)).scalar_one()


__all__ = [
    "CLAVE_TIEMPO_MINIMO",
    "FUENTES_ACTIVIDAD",
    "RAZON_AJUSTE",
    "RAZON_CONTENIDO_POBRE",
    "RAZON_PREGUNTA_1",
    "RAZON_PREGUNTA_2",
    "RAZON_PREGUNTA_SIN_INTENTO",
    "RAZON_PREGUNTA_TOPE",
    "RAZON_PRIMERA_VEZ",
    "RAZON_REPETICION_0",
    "RAZON_REPETICION_20",
    "RAZON_RESPUESTA_RAPIDA",
    "RAZON_TIEMPO_CORTO",
    "RAZON_TOPE_10",
    "RAZON_TOPE_50",
    "CalculoXP",
    "calcular_xp",
    "calcular_xp_pregunta",
    "calcular_xp_repaso",
    "multiplicador_contenido",
    "multiplicador_racha",
    "multiplicador_repeticion",
    "multiplicador_tope_diario",
    "otorgar_xp",
    "repasos_pagados_hoy",
    "tiempo_minimo_requerido",
    "tiempo_plausible",
    "xp_base_actividades_del_dia",
    "xp_de_conocimiento",
    "xp_preguntas_de_leccion",
    "xp_total",
]
