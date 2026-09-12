"""Módulo `economy`: oro, inventario, equipamiento, requisitos de desbloqueo y tienda.

Superficie pública que pueden usar los demás módulos (siempre a través de estas
funciones, nunca tocando sus tablas por su cuenta):

- **Oro** (:mod:`app.modules.economy.monedero`): :func:`otorgar_oro`, :func:`gastar_oro`,
  :func:`saldo`, :func:`saldo_ledger`, :func:`reconciliar_billetera`. `economy` es el
  único módulo que escribe `wallets` y `gold_transactions` (§1.3).
- **Desbloqueos** (:mod:`app.modules.economy.requisitos`): :func:`evaluar_desbloqueos`, que
  `gamification` invoca al final de la cascada de un evento (§4.1, orden de consumo), y
  :func:`evaluar_item` / :func:`explicar_requisitos` para gatear y explicar.
- **Inventario y equipamiento**: :func:`listar_inventario`, :func:`detalle_item`,
  :func:`equipar`, :func:`desequipar`, :func:`configuracion_avatar`.
- **Tienda**: :func:`catalogo`, :func:`comprar`, :func:`revertir_compra`.
- **API**: `router` (`app.modules.economy.router`), que monta el agente de integración.

Todo cálculo de oro ocurre en el servidor y se apoya en el ledger `gold_transactions`
con `idempotency_key`; ningún valor de juego se escribe a mano: sale de `game_configs`.
"""

from __future__ import annotations

from app.modules.economy.equipamiento import (
    CambioEquipamiento,
    aplicar_equipamiento,
    configuracion_avatar,
    desequipar,
    equipar,
    slots_activos,
)
from app.modules.economy.inventario import (
    FilaInventario,
    PaginaInventario,
    detalle_item,
    listar_inventario,
    posee,
    registrar_previsualizacion,
)
from app.modules.economy.monedero import (
    Reconciliacion,
    SaldoInsuficiente,
    gastar_oro,
    movimientos,
    obtener_billetera,
    otorgar_oro,
    reconciliar_billetera,
    saldo,
    saldo_ledger,
    valor_config,
    version_config,
)
from app.modules.economy.requisitos import (
    CondicionEvaluada,
    EvaluacionItem,
    evaluar_desbloqueos,
    evaluar_item,
    explicar_requisitos,
    otorgar_item,
)
from app.modules.economy.tienda import (
    CatalogoTienda,
    NoDisponible,
    PrecioCambiado,
    RequisitosNoCumplidos,
    ResultadoCompra,
    YaPoseido,
    catalogo,
    comprar,
    es_cosmetico,
    precio_por_rareza,
    revertir_compra,
)

__all__ = [
    "CambioEquipamiento",
    "CatalogoTienda",
    "CondicionEvaluada",
    "EvaluacionItem",
    "FilaInventario",
    "NoDisponible",
    "PaginaInventario",
    "PrecioCambiado",
    "Reconciliacion",
    "RequisitosNoCumplidos",
    "ResultadoCompra",
    "SaldoInsuficiente",
    "YaPoseido",
    "aplicar_equipamiento",
    "catalogo",
    "comprar",
    "configuracion_avatar",
    "desequipar",
    "detalle_item",
    "equipar",
    "es_cosmetico",
    "evaluar_desbloqueos",
    "evaluar_item",
    "explicar_requisitos",
    "gastar_oro",
    "listar_inventario",
    "movimientos",
    "obtener_billetera",
    "otorgar_item",
    "otorgar_oro",
    "posee",
    "precio_por_rareza",
    "reconciliar_billetera",
    "registrar_previsualizacion",
    "revertir_compra",
    "saldo",
    "saldo_ledger",
    "slots_activos",
    "valor_config",
    "version_config",
]
