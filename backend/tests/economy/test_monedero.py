"""Pruebas del monedero: ledger append-only, idempotencia y reconciliación."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.economy import GoldTransaction, Wallet
from app.models.enums import EventType, GoldSink, GoldSource, LedgerDirection
from app.models.gamification import DomainEvent
from app.modules.economy import monedero

pytestmark = pytest.mark.db


def test_otorgar_oro_credita_y_actualiza_el_saldo_cacheado(db, configuracion, usuario):
    """Un crédito escribe el ledger, el saldo cacheado y el evento `GOLD_AWARDED`."""
    transaccion = monedero.otorgar_oro(
        db,
        usuario.id,
        amount=100,
        source=GoldSource.WELCOME,
        reason_code="welcome_bag",
        idempotency_key=f"welcome:{usuario.id}",
    )

    assert transaccion.direction is LedgerDirection.CREDIT
    assert transaccion.balance_after == 100
    assert monedero.saldo(db, usuario.id) == 100
    assert monedero.saldo_ledger(db, usuario.id) == 100

    evento = db.get(DomainEvent, transaccion.event_id)
    assert evento is not None
    assert evento.event_type is EventType.GOLD_AWARDED
    assert evento.payload["balance_after"] == 100
    assert evento.source_module == "economy"


def test_otorgar_oro_es_idempotente(db, configuracion, usuario):
    """Repetir la misma clave no vuelve a acreditar ni duplica filas del ledger."""
    clave = f"lesson:{uuid.uuid4()}"
    primera = monedero.otorgar_oro(
        db,
        usuario.id,
        amount=20,
        source=GoldSource.LESSON,
        reason_code="first_completion",
        idempotency_key=clave,
    )
    segunda = monedero.otorgar_oro(
        db,
        usuario.id,
        amount=20,
        source=GoldSource.LESSON,
        reason_code="first_completion",
        idempotency_key=clave,
    )

    assert primera.id == segunda.id
    assert monedero.saldo(db, usuario.id) == 20
    total = db.execute(
        sa.select(sa.func.count()).select_from(GoldTransaction).where(
            GoldTransaction.user_id == usuario.id
        )
    ).scalar_one()
    assert total == 1


def test_gastar_oro_sin_saldo_falla_sin_efectos(db, configuracion, usuario):
    """Un débito mayor que el saldo lanza `INSUFFICIENT_GOLD` y no escribe nada."""
    monedero.otorgar_oro(
        db,
        usuario.id,
        amount=50,
        source=GoldSource.WELCOME,
        reason_code="welcome_bag",
        idempotency_key=f"welcome:{usuario.id}",
    )

    with pytest.raises(monedero.SaldoInsuficiente) as excinfo:
        monedero.gastar_oro(
            db,
            usuario.id,
            amount=150,
            sink=GoldSink.PURCHASE,
            reason_code="purchase",
            idempotency_key=f"compra:{uuid.uuid4()}",
        )

    assert excinfo.value.code == "INSUFFICIENT_GOLD"
    assert excinfo.value.details == {"required": 150, "balance": 50, "missing": 100}
    assert monedero.saldo(db, usuario.id) == 50
    debitos = db.execute(
        sa.select(sa.func.count()).select_from(GoldTransaction).where(
            GoldTransaction.user_id == usuario.id,
            GoldTransaction.direction == LedgerDirection.DEBIT,
        )
    ).scalar_one()
    assert debitos == 0


def test_saldo_del_ledger_y_cacheado_coinciden_tras_varias_operaciones(
    db, configuracion, usuario
):
    """Invariante de §6.3: `wallets.balance = SUM(créditos) - SUM(débitos)`."""
    movimientos = [
        monedero.otorgar_oro(
            db,
            usuario.id,
            amount=100,
            source=GoldSource.WELCOME,
            reason_code="welcome_bag",
            idempotency_key="w1",
        ),
        monedero.otorgar_oro(
            db,
            usuario.id,
            amount=20,
            source=GoldSource.LESSON,
            reason_code="first_completion",
            idempotency_key="l1",
        ),
        monedero.otorgar_oro(
            db,
            usuario.id,
            amount=80,
            source=GoldSource.MODULE,
            reason_code="first_completion",
            idempotency_key="m1",
        ),
        monedero.gastar_oro(
            db,
            usuario.id,
            amount=150,
            sink=GoldSink.PURCHASE,
            reason_code="purchase",
            idempotency_key="c1",
        ),
        monedero.otorgar_oro(
            db,
            usuario.id,
            amount=10,
            source=GoldSource.REVIEW,
            reason_code="first_completion",
            idempotency_key="r1",
        ),
    ]

    esperado = 100 + 20 + 80 - 150 + 10
    assert monedero.saldo_ledger(db, usuario.id) == esperado
    assert monedero.saldo(db, usuario.id) == esperado

    billetera = monedero.obtener_billetera(db, usuario.id)
    assert billetera.lifetime_earned == 210
    assert billetera.lifetime_spent == 150

    # Cada fila del ledger deja el saldo posterior coherente con la anterior.
    assert [fila.balance_after for fila in movimientos] == [100, 120, 200, 50, 60]
    assert movimientos[-1].balance_after == esperado
    assert (
        db.execute(
            sa.select(sa.func.count())
            .select_from(GoldTransaction)
            .where(GoldTransaction.user_id == usuario.id)
        ).scalar_one()
        == 5
    )


def test_reconciliar_billetera_corrige_un_saldo_cacheado_desviado(
    db, configuracion, usuario
):
    """La reconciliación recalcula el saldo desde el ledger y marca la corrección."""
    monedero.otorgar_oro(
        db,
        usuario.id,
        amount=300,
        source=GoldSource.PATH,
        reason_code="first_completion",
        idempotency_key="p1",
    )
    monedero.gastar_oro(
        db,
        usuario.id,
        amount=100,
        sink=GoldSink.PURCHASE,
        reason_code="purchase",
        idempotency_key="c1",
    )

    # Se corrompe el saldo cacheado a mano (nunca se hace esto en producción).
    db.execute(
        sa.update(Wallet).where(Wallet.user_id == usuario.id).values(balance=999)
    )
    db.flush()
    db.expire_all()
    assert monedero.saldo(db, usuario.id) == 999

    resultado = monedero.reconciliar_billetera(db, usuario.id)

    assert resultado.corregido is True
    assert resultado.balance_ledger == 200
    assert resultado.desvio == 200 - 999
    assert monedero.saldo(db, usuario.id) == 200

    # Reconciliar de nuevo ya no cambia nada.
    assert monedero.reconciliar_billetera(db, usuario.id).corregido is False


def test_valor_config_exige_la_clave_en_game_configs(db, usuario):
    """Sin semilla no hay valor por defecto escrito en el código: falla explícitamente."""
    with pytest.raises(monedero.ConfiguracionAusente):
        monedero.valor_config(db, "shop.price_by_rarity")
