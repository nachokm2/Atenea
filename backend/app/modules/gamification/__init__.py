"""Módulo `gamification` de Atenea: el motor que convierte aprendizaje en juego.

Piezas (CONTRACT.md §1.3, §4, §5, §6 y §7.9):

- `servicio_config`: lectura cacheada y tipada de `game_configs`. **Ningún número
  de juego vive en el código**: todo sale de aquí.
- `eventos`: catálogo de eventos, payloads tipados y `registrar_evento`, el punto
  de entrada idempotente del bus `domain_events`.
- `reglas`: motor de reglas declarativo acotado sobre `reward_rules`.
- `xp` y `niveles`: ledger de XP con las reglas anti-abuso y las dos curvas de nivel.
- `rachas`: día activo, calendario, objetivo diario y hitos de racha.
- `misiones` y `logros`: instanciación, avance por evento y desbloqueo idempotente.
- `recompensas`: el `ReciboRecompensas` canónico y su agregador.
- `motor`: orquesta el orden de consumo XP/oro → día → racha → misiones → logros
  → desbloqueos, con límite de cascada.
- `router`: los endpoints de misiones, logros, racha, objetivo y notificaciones.

La comunicación con otros módulos es por eventos de dominio; la única llamada
directa permitida es la función pública de `economy` para el oro y los
desbloqueos de ítems, siempre con importación perezosa.
"""

from __future__ import annotations

from app.modules.gamification.eventos import registrar_evento
from app.modules.gamification.motor import procesar_evento
from app.modules.gamification.recompensas import ReciboRecompensas
from app.modules.gamification.router import router
from app.modules.gamification.servicio_config import ServicioConfig, invalidar_cache

__all__ = [
    "ReciboRecompensas",
    "ServicioConfig",
    "invalidar_cache",
    "procesar_evento",
    "registrar_evento",
    "router",
]
