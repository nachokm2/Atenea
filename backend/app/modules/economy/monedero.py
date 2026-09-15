"""Billetera y ledger de oro del módulo `economy` (contrato §3.6, §6.3).

Reglas que este archivo materializa:

- La **fuente de verdad del saldo es el ledger** `gold_transactions`, que es append-only:
  nunca se hace `UPDATE` ni `DELETE` sobre él. `wallets.balance` es solo un saldo
  cacheado que se actualiza **en la misma transacción** que la fila del ledger y que
  puede recalcularse en cualquier momento con :func:`reconciliar_billetera`.
- Toda operación es **idempotente por `(user_id, idempotency_key)`**: un reintento de red
  devuelve la misma fila del ledger y no vuelve a mover oro.
- Toda operación es **atómica**: la billetera se bloquea con `SELECT … FOR UPDATE` y el
  crédito o débito se escribe dentro del mismo punto de guardado.
- El servidor es la autoridad: el importe, el motivo y la fecha local los decide este
  módulo; el cliente jamás envía cantidades de oro.
- Ningún valor de juego se escribe a mano: todo sale de `game_configs` a través de
  :func:`valor_config`.

TODO(A6): cuando el módulo `gamification` publique su servicio de configuración
(`game_configs` con caché de 60 s), :func:`valor_config` y :func:`version_config` deben
delegar en él en vez de consultar la tabla directamente.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, InternalError, NotFound, ValidationFailed
from app.core.logging import get_logger
from app.core.time import user_local_date, utcnow
from app.models.economy import GoldTransaction, Wallet
from app.models.enums import (
    Currency,
    EventStatus,
    EventType,
    GoldSink,
    GoldSource,
    LedgerDirection,
)
from app.models.gamification import DomainEvent, GameConfig
from app.models.identity import User

logger = get_logger("atenea.economy")

#: Nombre del módulo productor que se estampa en `domain_events.source_module`.
SOURCE_MODULE = "economy"

#: Longitud máxima de `gold_transactions.idempotency_key` y de la del evento (§3.6).
MAX_CLAVE = 120

_SIN_DEFECTO = object()


# ---------------------------------------------------------------------------
# Errores propios del monedero
# ---------------------------------------------------------------------------


class SaldoInsuficiente(Conflict):
    """409 `INSUFFICIENT_GOLD` · el saldo no alcanza para el débito solicitado."""

    code = "INSUFFICIENT_GOLD"


class ConfiguracionAusente(InternalError):
    """500 · falta una clave de `game_configs`; el servidor no inventa valores de juego."""

    code = "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# Lectura de `game_configs`
# ---------------------------------------------------------------------------


def valor_config(
    db: Session,
    clave: str,
    *,
    por_defecto: Any = _SIN_DEFECTO,
    ahora: dt.datetime | None = None,
) -> Any:
    """Devuelve el valor vigente de una clave de `game_configs`.

    Vigente = `valid_from <= ahora < coalesce(valid_to, infinito)`, y entre las vigentes
    la de mayor `version`. Si la clave no existe se lanza :class:`ConfiguracionAusente`
    salvo que se indique `por_defecto`: ningún parámetro de juego se escribe como literal
    en el código (contrato §8.10, regla 5).
    """
    momento = ahora or utcnow()
    consulta = (
        sa.select(GameConfig.value)
        .where(
            GameConfig.key == clave,
            GameConfig.valid_from <= momento,
            sa.or_(GameConfig.valid_to.is_(None), GameConfig.valid_to > momento),
        )
        .order_by(GameConfig.version.desc())
        .limit(1)
    )
    fila = db.execute(consulta).scalar_one_or_none()
    if fila is None:
        if por_defecto is not _SIN_DEFECTO:
            return por_defecto
        raise ConfiguracionAusente(details={"config_key": clave})
    return fila


def version_config(db: Session, *, ahora: dt.datetime | None = None) -> int:
    """Versión global de configuración vigente, que se sella en cada fila del ledger."""
    momento = ahora or utcnow()
    consulta = sa.select(sa.func.max(GameConfig.config_version)).where(
        GameConfig.valid_from <= momento,
        sa.or_(GameConfig.valid_to.is_(None), GameConfig.valid_to > momento),
    )
    return int(db.execute(consulta).scalar() or 0)


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------


def _usuario(db: Session, usuario_id: uuid.UUID) -> User:
    """Carga el usuario dueño de la billetera o lanza 404 (nunca filtra existencia)."""
    usuario = db.get(User, usuario_id)
    if usuario is None or usuario.deleted_at is not None:
        raise NotFound(details={"user_id": str(usuario_id)})
    return usuario


def fecha_local(
    db: Session, usuario_id: uuid.UUID, momento: dt.datetime | None = None
) -> dt.date:
    """Fecha local del usuario (§8.6): la calcula siempre el servidor, nunca el cliente."""
    usuario = _usuario(db, usuario_id)
    return user_local_date(momento, usuario.timezone)


def recortar_clave(clave: str) -> str:
    """Recorta una clave de idempotencia al largo de la columna (`String(120)`)."""
    return clave[:MAX_CLAVE]


def _transaccion_existente(
    db: Session, usuario_id: uuid.UUID, clave: str
) -> GoldTransaction | None:
    """Devuelve la fila del ledger ya escrita con esa clave, si la hay."""
    return db.execute(
        sa.select(GoldTransaction).where(
            GoldTransaction.user_id == usuario_id,
            GoldTransaction.idempotency_key == clave,
        )
    ).scalar_one_or_none()


def registrar_evento(
    db: Session,
    *,
    event_type: EventType,
    usuario: User,
    payload: dict[str, Any],
    clave: str,
    local_date: dt.date | None,
    momento: dt.datetime,
    correlation_id: uuid.UUID | None = None,
    causation_id: uuid.UUID | None = None,
    procesar: bool = False,
) -> DomainEvent:
    """Inserta (o reutiliza) el evento de dominio que acompaña al movimiento de oro.

    Con ``procesar=True`` el evento pasa además por el motor de gamificación, que
    es lo que hace que avancen misiones y se desbloqueen logros.

    No está activado por defecto y la razón importa. Los eventos de oro
    (``GOLD_AWARDED``, ``GOLD_SPENT``) los emite este módulo **desde dentro** del
    propio motor, cuando el motor paga: procesarlos ahí lo llamaría a sí mismo.
    Los eventos de objeto, en cambio, nacen de una acción del aprendiz (equipar,
    quitarse algo, mirar una ficha) y ahí no hay motor corriendo.

    Sin esto, equipar un objeto no desbloqueaba nada: cinco logros del catálogo
    dependen de ``ITEM_EQUIPPED`` o ``ITEM_ACQUIRED`` y eran inalcanzables.
    """
    clave = recortar_clave(clave)
    existente = db.execute(
        sa.select(DomainEvent).where(DomainEvent.idempotency_key == clave)
    ).scalar_one_or_none()
    if existente is not None:
        return existente

    evento = DomainEvent(
        event_type=event_type,
        user_id=usuario.id,
        occurred_at=momento,
        received_at=momento,
        local_date=local_date,
        timezone=usuario.timezone,
        version=1,
        source_module=SOURCE_MODULE,
        payload=payload,
        correlation_id=correlation_id,
        causation_id=causation_id,
        processing_status=EventStatus.PENDING,
        idempotency_key=clave,
    )
    db.add(evento)
    db.flush()

    if procesar:
        from app.modules.gamification import motor  # noqa: PLC0415 - cruce perezoso (§1.3)
        from app.modules.gamification.servicio_config import ServicioConfig  # noqa: PLC0415

        try:
            motor.procesar_evento(
                db, evento, cfg=ServicioConfig(db), timezone=usuario.timezone
            )
        except Exception as error:
            # Equipar un objeto no puede fallar porque el motor no consiga
            # calcular una recompensa. La acción del aprendiz vale más que el
            # logro que la acompaña: el evento queda pendiente y su premio se
            # cobra cuando alguien lo drene.
            logger.warning(
                "economy.evento_sin_procesar",
                event_type=evento.event_type.value,
                error=type(error).__name__,
            )
        else:
            evento.processing_status = EventStatus.PROCESSED
            evento.processed_at = momento
        db.flush()

    return evento


# ---------------------------------------------------------------------------
# Billetera
# ---------------------------------------------------------------------------


def obtener_billetera(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    currency: Currency = Currency.GOLD,
    bloquear: bool = False,
    crear: bool = True,
) -> Wallet:
    """Devuelve la billetera del usuario, creándola vacía la primera vez.

    Con `bloquear=True` la fila se toma con `SELECT … FOR UPDATE`: es lo que serializa
    dos compras simultáneas del mismo usuario (contrato §6.3).
    """
    consulta = sa.select(Wallet).where(
        Wallet.user_id == usuario_id, Wallet.currency == currency
    )
    if bloquear:
        consulta = consulta.with_for_update()
    billetera = db.execute(consulta).scalar_one_or_none()
    if billetera is not None:
        return billetera
    if not crear:
        raise NotFound(details={"user_id": str(usuario_id), "currency": currency.value})

    _usuario(db, usuario_id)
    try:
        with db.begin_nested():
            billetera = Wallet(
                user_id=usuario_id,
                currency=currency,
                balance=0,
                lifetime_earned=0,
                lifetime_spent=0,
                version=0,
            )
            db.add(billetera)
            db.flush()
    except IntegrityError:
        # Otra petición creó la billetera a la vez: se relee la que ganó.
        billetera = db.execute(consulta).scalar_one()
    return billetera


def saldo(db: Session, usuario_id: uuid.UUID, *, currency: Currency = Currency.GOLD) -> int:
    """Saldo cacheado en `wallets` (lectura O(1) para la UI)."""
    valor = db.execute(
        sa.select(Wallet.balance).where(
            Wallet.user_id == usuario_id, Wallet.currency == currency
        )
    ).scalar_one_or_none()
    return int(valor or 0)


def saldo_ledger(
    db: Session, usuario_id: uuid.UUID, *, currency: Currency = Currency.GOLD
) -> int:
    """Saldo **derivado del ledger**: `SUM(créditos) - SUM(débitos)` (fuente de verdad)."""
    creditos, debitos = _totales_ledger(db, usuario_id, currency)
    return creditos - debitos


def _totales_ledger(
    db: Session, usuario_id: uuid.UUID, currency: Currency
) -> tuple[int, int]:
    """Suma de créditos y de débitos del ledger para un usuario y una moneda."""
    fila = db.execute(
        sa.select(
            sa.func.coalesce(
                sa.func.sum(
                    sa.case(
                        (GoldTransaction.direction == LedgerDirection.CREDIT, GoldTransaction.amount),
                        else_=0,
                    )
                ),
                0,
            ),
            sa.func.coalesce(
                sa.func.sum(
                    sa.case(
                        (GoldTransaction.direction == LedgerDirection.DEBIT, GoldTransaction.amount),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(
            GoldTransaction.user_id == usuario_id,
            GoldTransaction.currency == currency,
        )
    ).one()
    return int(fila[0]), int(fila[1])


@dataclass(frozen=True)
class Reconciliacion:
    """Resultado de recalcular el saldo cacheado desde el ledger."""

    user_id: uuid.UUID
    currency: Currency
    balance_ledger: int
    balance_cacheado_previo: int
    lifetime_earned: int
    lifetime_spent: int
    corregido: bool

    @property
    def desvio(self) -> int:
        """Diferencia detectada entre el saldo cacheado y el del ledger."""
        return self.balance_ledger - self.balance_cacheado_previo


def reconciliar_billetera(
    db: Session, usuario_id: uuid.UUID, *, currency: Currency = Currency.GOLD
) -> Reconciliacion:
    """Recalcula `wallets` desde el ledger y corrige el saldo cacheado si hace falta.

    Es la función que ejecuta el trabajo nocturno de conciliación y la que usan las
    pruebas para comprobar el invariante `wallets.balance = SUM(cr) - SUM(deb)`.
    """
    billetera = obtener_billetera(db, usuario_id, currency=currency, bloquear=True)
    creditos, debitos = _totales_ledger(db, usuario_id, currency)
    saldo_real = creditos - debitos
    previo = int(billetera.balance)

    corregido = (
        previo != saldo_real
        or int(billetera.lifetime_earned) != creditos
        or int(billetera.lifetime_spent) != debitos
    )
    if corregido:
        billetera.balance = saldo_real
        billetera.lifetime_earned = creditos
        billetera.lifetime_spent = debitos
        billetera.version = int(billetera.version) + 1
        db.flush()

    return Reconciliacion(
        user_id=usuario_id,
        currency=currency,
        balance_ledger=saldo_real,
        balance_cacheado_previo=previo,
        lifetime_earned=creditos,
        lifetime_spent=debitos,
        corregido=corregido,
    )


# ---------------------------------------------------------------------------
# Movimientos del ledger
# ---------------------------------------------------------------------------


def _registrar(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    direction: LedgerDirection,
    amount: int,
    reason_code: str,
    idempotency_key: str,
    source: GoldSource | None = None,
    sink: GoldSink | None = None,
    source_id: uuid.UUID | None = None,
    currency: Currency = Currency.GOLD,
    momento: dt.datetime | None = None,
    payload_extra: dict[str, Any] | None = None,
    correlation_id: uuid.UUID | None = None,
    causation_id: uuid.UUID | None = None,
) -> GoldTransaction:
    """Escribe una fila del ledger, su evento y el saldo cacheado, todo atómico."""
    if int(amount) <= 0:
        raise ValidationFailed(
            "El importe de oro debe ser mayor que cero.",
            field_errors=[{"field": "amount", "message": "Debe ser un entero positivo."}],
        )
    clave = recortar_clave(idempotency_key)

    existente = _transaccion_existente(db, usuario_id, clave)
    if existente is not None:
        return existente

    usuario = _usuario(db, usuario_id)
    instante = momento or utcnow()
    local_date = user_local_date(instante, usuario.timezone)
    importe = int(amount)

    try:
        with db.begin_nested():
            billetera = obtener_billetera(db, usuario_id, currency=currency, bloquear=True)
            actual = int(billetera.balance)

            if direction is LedgerDirection.DEBIT and actual < importe:
                raise SaldoInsuficiente(
                    details={
                        "required": importe,
                        "balance": actual,
                        "missing": importe - actual,
                    }
                )

            posterior = actual + importe if direction is LedgerDirection.CREDIT else actual - importe

            payload: dict[str, Any] = {
                "amount": importe,
                "balance_after": posterior,
                "reason_code": reason_code,
            }
            if direction is LedgerDirection.CREDIT:
                payload["source"] = source.value if source else None
                tipo_evento = EventType.GOLD_AWARDED
                prefijo = "gold-awarded"
            else:
                payload["sink"] = sink.value if sink else None
                tipo_evento = EventType.GOLD_SPENT
                prefijo = "gold-spent"
            payload.update(payload_extra or {})

            evento = registrar_evento(
                db,
                event_type=tipo_evento,
                usuario=usuario,
                payload=payload,
                clave=f"{prefijo}:{usuario_id}:{clave}",
                local_date=local_date,
                momento=instante,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )

            transaccion = GoldTransaction(
                user_id=usuario_id,
                currency=currency,
                event_id=evento.id,
                direction=direction,
                source=source,
                sink=sink,
                source_id=source_id,
                amount=importe,
                balance_after=posterior,
                reason_code=reason_code,
                config_version=version_config(db, ahora=instante),
                local_date=local_date,
                idempotency_key=clave,
            )
            db.add(transaccion)

            billetera.balance = posterior
            if direction is LedgerDirection.CREDIT:
                billetera.lifetime_earned = int(billetera.lifetime_earned) + importe
            else:
                billetera.lifetime_spent = int(billetera.lifetime_spent) + importe
            billetera.version = int(billetera.version) + 1
            db.flush()
    except IntegrityError:
        # Carrera con otra petición que usó la misma clave: gana la primera.
        previa = _transaccion_existente(db, usuario_id, clave)
        if previa is None:
            raise
        return previa

    return transaccion


def otorgar_oro(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    amount: int,
    source: GoldSource,
    reason_code: str,
    idempotency_key: str,
    source_id: uuid.UUID | None = None,
    currency: Currency = Currency.GOLD,
    momento: dt.datetime | None = None,
    ref_event_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
) -> GoldTransaction:
    """Acredita oro (`direction = credit`) de forma atómica e idempotente.

    `source` es obligatorio y tipado (`GoldSource`); el check de tabla
    `ck_gold_transactions_direction_dimension` rechaza un crédito sin fuente.
    Emite `GOLD_AWARDED` y deja `wallets` al día en la misma transacción.
    """
    extra = {"ref_event_id": str(ref_event_id) if ref_event_id else None}
    return _registrar(
        db,
        usuario_id,
        direction=LedgerDirection.CREDIT,
        amount=amount,
        source=source,
        reason_code=reason_code,
        idempotency_key=idempotency_key,
        source_id=source_id,
        currency=currency,
        momento=momento,
        payload_extra=extra,
        correlation_id=correlation_id,
    )


def gastar_oro(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    amount: int,
    sink: GoldSink,
    reason_code: str,
    idempotency_key: str,
    source_id: uuid.UUID | None = None,
    currency: Currency = Currency.GOLD,
    momento: dt.datetime | None = None,
    payload_extra: dict[str, Any] | None = None,
    correlation_id: uuid.UUID | None = None,
) -> GoldTransaction:
    """Debita oro (`direction = debit`) validando saldo suficiente.

    Lanza :class:`SaldoInsuficiente` (409 `INSUFFICIENT_GOLD`) **sin efecto alguno** si el
    saldo no alcanza: el punto de guardado se revierte entero. `sink` es obligatorio.
    """
    return _registrar(
        db,
        usuario_id,
        direction=LedgerDirection.DEBIT,
        amount=amount,
        sink=sink,
        reason_code=reason_code,
        idempotency_key=idempotency_key,
        source_id=source_id,
        currency=currency,
        momento=momento,
        payload_extra=payload_extra,
        correlation_id=correlation_id,
    )


def movimientos(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    currency: Currency = Currency.GOLD,
    limit: int = 20,
    antes_de: dt.datetime | None = None,
) -> list[GoldTransaction]:
    """Últimos movimientos del ledger, del más reciente al más antiguo."""
    consulta = sa.select(GoldTransaction).where(
        GoldTransaction.user_id == usuario_id,
        GoldTransaction.currency == currency,
    )
    if antes_de is not None:
        consulta = consulta.where(GoldTransaction.created_at < antes_de)
    consulta = consulta.order_by(
        GoldTransaction.created_at.desc(), GoldTransaction.id.desc()
    ).limit(limit)
    return list(db.execute(consulta).scalars().all())


__all__ = [
    "MAX_CLAVE",
    "SOURCE_MODULE",
    "ConfiguracionAusente",
    "Reconciliacion",
    "SaldoInsuficiente",
    "fecha_local",
    "gastar_oro",
    "movimientos",
    "obtener_billetera",
    "otorgar_oro",
    "reconciliar_billetera",
    "recortar_clave",
    "registrar_evento",
    "saldo",
    "saldo_ledger",
    "valor_config",
    "version_config",
]
