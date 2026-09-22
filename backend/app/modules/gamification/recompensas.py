"""`ReciboRecompensas`: objeto canónico de recompensas (CONTRACT.md §7.10).

Es lo **único** que el cliente usa para animar: la app nunca calcula XP, oro,
nivel ni dominio. Todas las secciones existen siempre; las vacías van como `null`
(objetos) o `[]` (listas).

`presentation_order` es autoritativo y su orden canónico es el de la cola de
celebraciones de UX::

    xp → gold → mastery → streak → level_up → item → achievement → mission

Aquí vive además el **agregador**: fusiona todo lo que produjo un evento (y su
cascada) en un único recibo, con límite de profundidad y protección contra bucles.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.time import utcnow

#: Orden canónico de presentación (§7.10 regla 2). El cliente anima en este orden.
ORDEN_PRESENTACION: tuple[str, ...] = (
    "xp",
    "gold",
    "mastery",
    "streak",
    "level_up",
    "item",
    "achievement",
    "mission",
)

#: Máximo de overlays a pantalla completa (posiciones 4–6 del orden canónico).
MAX_OVERLAYS = 3

#: Secciones que se presentan como overlay.
SECCIONES_OVERLAY: tuple[str, ...] = ("streak", "level_up", "item")

#: Profundidad máxima de la cascada de eventos derivados (protección anti-bucle).
MAX_PROFUNDIDAD_CASCADA = 3


class _Base(BaseModel):
    """Base común: se serializa por valor de enum y admite construcción desde ORM."""

    model_config = ConfigDict(from_attributes=True)


class XPRecibo(_Base):
    """Sección `xp` del recibo."""

    amount: int = 0
    base_amount: int = 0
    activity_xp: int = 0
    question_xp: int = 0
    multiplier: Decimal = Decimal("1.000")
    reason_code: str = ""
    is_educational: bool = True
    total_after: int = 0


class OroRecibo(_Base):
    """Sección `gold` del recibo."""

    amount: int = 0
    balance_after: int | None = None
    reason_code: str = ""


class NivelRecibo(_Base):
    """Sección `level` del recibo (curva global)."""

    before: int = 1
    after: int = 1
    leveled_up: bool = False
    rank_title_before: str = ""
    rank_title_after: str = ""
    rank_changed: bool = False
    xp_to_next: int = 0
    progress_pct: Decimal = Decimal("0.00")
    gold_bonus: int = 0
    # Bono de `gold.rank_up_bonus`, aparte del de `gold_bonus` (nivel): el
    # cliente los funde en el mismo total de oro del recibo si no viajan
    # desglosados, y no puede mostrar cuánto vino de cada uno.
    rank_bonus: int = 0
    unlocked_shop_rarities: list[str] = Field(default_factory=list)


class ConocimientoRecibo(_Base):
    """Sección `knowledge` del recibo (curva y dominio del conocimiento tocado)."""

    knowledge_area_id: uuid.UUID | None = None
    name: str | None = None
    xp_after: int = 0
    level_before: int | None = None
    level_after: int | None = None
    rank_title_after: str | None = None
    mastery_before: Decimal | None = None
    mastery_after: Decimal | None = None
    status: str | None = None


class DeltaDominio(_Base):
    """Entrada de `mastery_deltas` (la calcula `progress` y viaja en el recibo)."""

    scope: str
    id: uuid.UUID | None = None
    name: str | None = None
    before: Decimal | None = None
    after: Decimal | None = None
    status: str | None = None


class HitoRacha(_Base):
    """Hito de racha alcanzado en este evento."""

    length: int
    first_time: bool = True
    reward: dict[str, Any] = Field(default_factory=dict)


class RachaRecibo(_Base):
    """Sección `streak` del recibo."""

    current: int = 0
    best: int = 0
    change: str | None = None
    day_status: str | None = None
    is_first_activity_of_day: bool = False
    milestone: HitoRacha | None = None


class ObjetivoDiarioRecibo(_Base):
    """Sección `daily_goal` del recibo."""

    type: str
    target: int
    progress: int = 0
    met: bool = False
    just_met: bool = False
    bonus_gold: int = 0


class MisionRecibo(_Base):
    """Entrada de `missions`."""

    user_mission_id: uuid.UUID
    template_code: str
    title: str
    progress: int
    target: int
    status: str
    auto_claimed: bool = False
    reward: dict[str, Any] = Field(default_factory=dict)


class LogroRecibo(_Base):
    """Entrada de `achievements`."""

    code: str
    name: str
    tier: str
    reward: dict[str, Any] = Field(default_factory=dict)


class ItemRecibo(_Base):
    """Entrada de `items` (la produce el evaluador de desbloqueos de `economy`)."""

    user_item_id: uuid.UUID | None = None
    item_code: str
    name: str | None = None
    slot: str | None = None
    rarity: str | None = None
    origin: str | None = None
    unlock_reason: str | None = None
    can_equip: bool = True


class DesbloqueoRecibo(_Base):
    """Entrada de `unlocks` (módulo, territorio, evaluación…)."""

    type: str
    id: uuid.UUID | None = None
    name: str | None = None


class ReciboRecompensas(_Base):
    """Objeto canónico de recompensas del contrato §7.10.

    Lo devuelven todas las acciones que otorgan recompensas. Repetir la petición
    con la misma `Idempotency-Key` devuelve el **mismo** `receipt_id` y el mismo
    contenido, sin volver a otorgar nada.
    """

    receipt_id: uuid.UUID
    event_type: str
    occurred_at: datetime
    config_version: int = 0
    xp: XPRecibo | None = None
    gold: OroRecibo | None = None
    level: NivelRecibo | None = None
    knowledge: ConocimientoRecibo | None = None
    mastery_deltas: list[DeltaDominio] = Field(default_factory=list)
    streak: RachaRecibo | None = None
    daily_goal: ObjetivoDiarioRecibo | None = None
    missions: list[MisionRecibo] = Field(default_factory=list)
    achievements: list[LogroRecibo] = Field(default_factory=list)
    items: list[ItemRecibo] = Field(default_factory=list)
    unlocks: list[DesbloqueoRecibo] = Field(default_factory=list)
    assessment_result: dict[str, Any] | None = None
    presentation_order: list[str] = Field(default_factory=list)
    pending_sync: bool = False

    def secciones_con_contenido(self) -> list[str]:
        """Secciones que tienen algo que animar, en el orden canónico de §7.10."""
        presentes: list[str] = []
        for seccion in ORDEN_PRESENTACION:
            if (seccion == "xp" and self.xp is not None and self.xp.amount) or (seccion == "gold" and self.gold is not None and self.gold.amount) or (seccion == "mastery" and (self.mastery_deltas or self.knowledge is not None)) or (seccion == "streak" and self.streak is not None and self.streak.is_first_activity_of_day) or (seccion == "level_up" and self.level is not None and self.level.leveled_up) or (seccion == "item" and self.items) or (seccion == "achievement" and self.achievements) or (seccion == "mission" and self.missions):
                presentes.append(seccion)
        return presentes

    def overlays(self) -> list[str]:
        """Secciones que se muestran como overlay, con el tope de tres (§7.10)."""
        return [s for s in self.secciones_con_contenido() if s in SECCIONES_OVERLAY][:MAX_OVERLAYS]

    def finalizar(self) -> ReciboRecompensas:
        """Calcula `presentation_order` y devuelve el propio recibo."""
        self.presentation_order = self.secciones_con_contenido()
        return self


class LimiteCascadaExcedido(Exception):
    """Se alcanzó la profundidad máxima de la cascada de eventos derivados."""


class AgregadorRecibo:
    """Acumula lo producido por un evento y su cascada en un único recibo.

    Protege contra bucles de dos formas (§4.1 regla 2 y §7.10):

    - `profundidad` nunca supera `MAX_PROFUNDIDAD_CASCADA`;
    - cada `idempotency_key` de evento derivado se procesa **una sola vez**
      (`claves_vistas`), de modo que un ciclo A → B → A se corta solo.
    """

    __slots__ = (
        "achievements",
        "assessment_result",
        "claves_vistas",
        "config_version",
        "daily_goal",
        "event_type",
        "gold_amount",
        "gold_balance_after",
        "gold_reason",
        "items",
        "knowledge",
        "level",
        "mastery_deltas",
        "missions",
        "occurred_at",
        "pending_sync",
        "profundidad",
        "receipt_id",
        "streak",
        "unlocks",
        "xp_activity",
        "xp_base",
        "xp_educational",
        "xp_multiplier",
        "xp_question",
        "xp_reason",
        "xp_total",
        "xp_total_after",
    )

    def __init__(self, *, receipt_id: uuid.UUID, event_type: str, occurred_at: datetime | None = None) -> None:
        self.receipt_id = receipt_id
        self.event_type = str(event_type)
        self.occurred_at = occurred_at or utcnow()
        self.config_version = 0

        self.xp_total = 0
        self.xp_base = 0
        self.xp_activity = 0
        self.xp_question = 0
        self.xp_multiplier = Decimal("1.000")
        self.xp_reason = ""
        self.xp_educational = True
        self.xp_total_after = 0

        self.gold_amount = 0
        self.gold_balance_after: int | None = None
        self.gold_reason = ""

        self.level: NivelRecibo | None = None
        self.knowledge: ConocimientoRecibo | None = None
        self.mastery_deltas: list[DeltaDominio] = []
        self.streak: RachaRecibo | None = None
        self.daily_goal: ObjetivoDiarioRecibo | None = None
        self.missions: list[MisionRecibo] = []
        self.achievements: list[LogroRecibo] = []
        self.items: list[ItemRecibo] = []
        self.unlocks: list[DesbloqueoRecibo] = []
        self.assessment_result: dict[str, Any] | None = None
        self.pending_sync = False

        self.profundidad = 0
        self.claves_vistas: set[str] = set()

    # -- Control de la cascada ---------------------------------------------

    def puede_descender(self) -> bool:
        """Indica si aún se puede procesar un nivel más de eventos derivados."""
        return self.profundidad < MAX_PROFUNDIDAD_CASCADA

    def marcar_visto(self, idempotency_key: str) -> bool:
        """Registra una clave de cascada; `False` si ya se había procesado (bucle)."""
        if idempotency_key in self.claves_vistas:
            return False
        self.claves_vistas.add(idempotency_key)
        return True

    # -- Acumuladores -------------------------------------------------------

    def sumar_xp(
        self,
        *,
        amount: int,
        base_amount: int,
        multiplier: Decimal,
        reason_code: str,
        is_educational: bool,
        total_after: int,
        es_pregunta: bool = False,
    ) -> None:
        """Acumula una transacción de XP en la sección `xp` del recibo."""
        self.xp_total += int(amount)
        self.xp_base += int(base_amount)
        if es_pregunta:
            self.xp_question += int(amount)
        else:
            self.xp_activity += int(amount)
        if amount or not self.xp_reason:
            self.xp_reason = reason_code
            self.xp_multiplier = Decimal(str(multiplier))
        self.xp_educational = self.xp_educational and bool(is_educational)
        self.xp_total_after = max(self.xp_total_after, int(total_after))

    def sumar_oro(self, *, amount: int, balance_after: int | None, reason_code: str) -> None:
        """Acumula oro otorgado (lo aplica `economy`; aquí solo se reporta)."""
        self.gold_amount += int(amount)
        if balance_after is not None:
            self.gold_balance_after = int(balance_after)
        if amount or not self.gold_reason:
            self.gold_reason = reason_code

    def agregar_mision(self, mision: MisionRecibo) -> None:
        """Añade una misión sin duplicarla (la cascada puede tocarla dos veces)."""
        for existente in self.missions:
            if existente.user_mission_id == mision.user_mission_id:
                existente.progress = mision.progress
                existente.status = mision.status
                existente.auto_claimed = existente.auto_claimed or mision.auto_claimed
                if mision.reward:
                    existente.reward = mision.reward
                return
        self.missions.append(mision)

    def agregar_logro(self, logro: LogroRecibo) -> None:
        """Añade un logro desbloqueado sin duplicar el par código+nivel."""
        for existente in self.achievements:
            if existente.code == logro.code and existente.tier == logro.tier:
                return
        self.achievements.append(logro)

    def agregar_item(self, item: ItemRecibo) -> None:
        """Añade un ítem desbloqueado sin duplicar el código."""
        if any(existente.item_code == item.item_code for existente in self.items):
            return
        self.items.append(item)

    def agregar_desbloqueo(self, desbloqueo: DesbloqueoRecibo) -> None:
        """Añade un desbloqueo de contenido (módulo, territorio, evaluación)."""
        self.unlocks.append(desbloqueo)

    def agregar_delta_dominio(self, delta: DeltaDominio) -> None:
        """Añade un delta de dominio calculado por `progress`."""
        self.mastery_deltas.append(delta)

    # -- Resultado ----------------------------------------------------------

    def construir(self) -> ReciboRecompensas:
        """Construye el `ReciboRecompensas` final con su `presentation_order`."""
        xp = (
            XPRecibo(
                amount=self.xp_total,
                base_amount=self.xp_base,
                activity_xp=self.xp_activity,
                question_xp=self.xp_question,
                multiplier=self.xp_multiplier,
                reason_code=self.xp_reason,
                is_educational=self.xp_educational,
                total_after=self.xp_total_after,
            )
            if self.xp_total or self.xp_reason
            else None
        )
        gold = (
            OroRecibo(
                amount=self.gold_amount,
                balance_after=self.gold_balance_after,
                reason_code=self.gold_reason,
            )
            if self.gold_amount or self.gold_reason
            else None
        )
        recibo = ReciboRecompensas(
            receipt_id=self.receipt_id,
            event_type=self.event_type,
            occurred_at=self.occurred_at,
            config_version=self.config_version,
            xp=xp,
            gold=gold,
            level=self.level,
            knowledge=self.knowledge,
            mastery_deltas=list(self.mastery_deltas),
            streak=self.streak,
            daily_goal=self.daily_goal,
            missions=list(self.missions),
            achievements=list(self.achievements),
            items=list(self.items),
            unlocks=list(self.unlocks),
            assessment_result=self.assessment_result,
            pending_sync=self.pending_sync,
        )
        return recibo.finalizar()


def recibo_vacio(receipt_id: uuid.UUID, event_type: str, occurred_at: datetime | None = None) -> ReciboRecompensas:
    """Recibo sin recompensas (eventos que no otorgan nada)."""
    return AgregadorRecibo(
        receipt_id=receipt_id, event_type=event_type, occurred_at=occurred_at
    ).construir()


__all__ = [
    "MAX_OVERLAYS",
    "MAX_PROFUNDIDAD_CASCADA",
    "ORDEN_PRESENTACION",
    "SECCIONES_OVERLAY",
    "AgregadorRecibo",
    "ConocimientoRecibo",
    "DeltaDominio",
    "DesbloqueoRecibo",
    "HitoRacha",
    "ItemRecibo",
    "LimiteCascadaExcedido",
    "LogroRecibo",
    "MisionRecibo",
    "NivelRecibo",
    "ObjetivoDiarioRecibo",
    "OroRecibo",
    "RachaRecibo",
    "ReciboRecompensas",
    "XPRecibo",
    "recibo_vacio",
]
