"""Módulo `identity`: cuentas, sesiones JWT, ajustes, personaje y avatar.

Es el módulo raíz de la pirámide de dependencias (§1.3): no conoce el progreso ni
el contenido de nadie, y todos los demás lo referencian por `users.id`. Sí llama
—hacia abajo— a `gamification` (bus de eventos, curva de niveles, racha y
objetivo diario) y a `economy` (monedero y equipamiento), que son los dueños de
esas tablas.

Superficie pública que pueden usar los demás módulos:

- **Autenticación** (:mod:`app.modules.identity.servicio_auth`):
  :func:`registrar`, :func:`iniciar_sesion`, :func:`refrescar`,
  :func:`cerrar_sesion`, :func:`cambiar_contrasena`,
  :func:`revocar_todos_los_refresh`.
- **Cuenta y preferencias** (:mod:`app.modules.identity.servicio_usuario`):
  :func:`vista_ajustes`, :func:`actualizar_ajustes`, :func:`estado_onboarding`,
  :func:`borrar_cuenta`.
- **Personaje** (:mod:`app.modules.identity.personaje`): :func:`crear_personaje`
  (emite `CHARACTER_CREATED` y devuelve el `RewardsReceipt`),
  :func:`obtener_personaje`, :func:`vista_personaje`.
- **Avatar** (:mod:`app.modules.identity.avatar`): :func:`vista_avatar`,
  :func:`actualizar_rasgos`, :func:`actualizar_equipamiento`.
- **API**: `router` (:mod:`app.modules.identity.router`), que monta el agente de
  integración bajo `/api/v1`.

Ninguna recompensa se otorga aquí: todo pasa por
`app.modules.gamification.eventos.registrar_evento`, y ningún valor de juego se
escribe a mano (sale de `game_configs` vía `ServicioConfig`).
"""

from __future__ import annotations

from app.modules.identity.avatar import (
    actualizar_equipamiento,
    actualizar_rasgos,
    obtener_o_crear_rasgos,
    vista_avatar,
)
from app.modules.identity.personaje import (
    actualizar_personaje,
    buscar_personaje,
    crear_personaje,
    obtener_personaje,
    sincronizar_cache,
    vista_personaje,
)
from app.modules.identity.servicio_auth import (
    ParTokens,
    buscar_por_email,
    cambiar_contrasena,
    cerrar_sesion,
    emitir_par,
    iniciar_sesion,
    normalizar_email,
    refrescar,
    registrar,
    revocar_todos_los_refresh,
    validar_fuerza_contrasena,
)
from app.modules.identity.servicio_usuario import (
    actualizar_ajustes,
    borrar_cuenta,
    cambiar_zona_horaria,
    estado_onboarding,
    obtener_o_crear_ajustes,
    tiene_personaje,
    tiene_ruta,
    vista_ajustes,
)

__all__ = [
    "ParTokens",
    "actualizar_ajustes",
    "actualizar_equipamiento",
    "actualizar_personaje",
    "actualizar_rasgos",
    "borrar_cuenta",
    "buscar_personaje",
    "buscar_por_email",
    "cambiar_contrasena",
    "cambiar_zona_horaria",
    "cerrar_sesion",
    "crear_personaje",
    "emitir_par",
    "estado_onboarding",
    "iniciar_sesion",
    "normalizar_email",
    "obtener_o_crear_ajustes",
    "obtener_o_crear_rasgos",
    "obtener_personaje",
    "refrescar",
    "registrar",
    "revocar_todos_los_refresh",
    "sincronizar_cache",
    "tiene_personaje",
    "tiene_ruta",
    "validar_fuerza_contrasena",
    "vista_ajustes",
    "vista_avatar",
    "vista_personaje",
]
