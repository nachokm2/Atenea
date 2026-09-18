"""Freno de peticiones (§8.7).

El contrato fija cuatro límites: 60 por minuto en general, 10 en la compra, 5 en
la creación de Rutas y 20 en el envío de respuestas. Todos estaban escritos en el
contrato y ninguno existía en el código: `slowapi` figuraba en las dependencias,
tres routers tenían un TODO esperándolo, y `RATE_LIMITED` era el único código del
catálogo de errores que nadie lanzaba nunca.

Sin freno, dos cosas salen caras de verdad. `POST /paths` y `POST /documents`
gastan presupuesto de Claude por petición, así que un bucle basta para vaciar el
saldo del día de todo el mundo. Y `POST /auth/login` verifica la contraseña con
bcrypt de coste 12 sobre un backend síncrono con cinco conexiones: probar
credenciales en masa es, además de un robo, una denegación de servicio barata.

## A quién se le cuenta

La clave del cubo es el usuario cuando hay sesión, y la IP cuando no la hay. Con
la IP sola, una universidad entera detrás de una salida compartida se frenaría a
sí misma; con el usuario solo, el acceso quedaría sin defensa, que es justo donde
más hace falta.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from limits import parse_many
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.errors import AteneaError

#: Ventana propia para los frenos aplicados como dependencia. En un solo proceso
#: basta con memoria; el día que haya varias réplicas hay que cambiar esto y el
#: almacenamiento de `slowapi` por uno compartido (Redis), o cada réplica contará
#: por su cuenta y el límite real será el que se fije multiplicado por réplicas.
_ventana = MovingWindowRateLimiter(MemoryStorage())


def clave_de_cubo(request: Request) -> str:
    """Identidad a la que se le cuentan las peticiones.

    `request.state.user_id` lo deja puesto el middleware de contexto cuando la
    petición trae una sesión válida. Si no la hay, se cae a la dirección de red.
    """
    usuario = getattr(request.state, "user_id", None)
    if usuario:
        return f"usuario:{usuario}"
    return f"ip:{get_remote_address(request)}"


limitador = Limiter(
    key_func=clave_de_cubo,
    default_limits=[settings.rate_limit_default],
    headers_enabled=True,
    # En pruebas el freno estorba: cada caso abre y cierra sesión muchas veces
    # en el mismo segundo y no está midiendo esto.
    enabled=settings.environment != "test",
)


def _respuesta_de_freno(request: Request, exc: RateLimitExceeded) -> Response:
    """Traduce el error de `slowapi` al sobre de error del contrato (§8.6)."""
    error = AteneaError(code="RATE_LIMITED", details={"limit": str(exc.detail)})
    cuerpo: dict[str, Any] = error.to_payload(getattr(request.state, "request_id", None))
    respuesta = JSONResponse(status_code=error.status_code, content=cuerpo)
    # `Retry-After` le dice al cliente cuándo volver, en vez de que lo adivine.
    respuesta.headers["Retry-After"] = "60"
    return respuesta


def freno(expresion: str) -> Callable[[Request], None]:
    """Freno aplicable como **dependencia**, no como decorador.

    Acepta **varios límites separados por `;`** —`"10/minute;60/hour"`— y los
    exige todos. Uno solo no basta donde lo que se defiende es la creación de
    algo: diez por minuto siguen siendo catorce mil cuentas al día. El de la
    ventana corta para la ráfaga, el de la larga para el goteo.

    El decorador `@limitador.limit(...)` envuelve la función, y el envoltorio
    pierde el espacio de nombres del módulo original. En una ruta con anotaciones
    diferidas y tipos de FastAPI (`UploadFile`, `File`, `Form`), eso deja a
    FastAPI sin poder resolver `UploadFile` y la aplicación no arranca. La subida
    de material es justo esa ruta, y es la que más conviene frenar porque cada
    archivo acaba en una ingesta que trocea, vectoriza y cuesta dinero.

    Como dependencia no hay envoltorio y la firma de la ruta se queda intacta.
    """
    limites = parse_many(expresion)

    def comprobar(request: Request) -> None:
        # Mismo interruptor que el limitador general: en pruebas el freno estorba,
        # porque un solo caso puede llamar veinte veces a la misma ruta en el
        # mismo segundo y no está midiendo esto.
        if not limitador.enabled:
            return
        clave = clave_de_cubo(request)
        for limite in limites:
            # Se cuenta también la petición que se rechaza, a propósito: quien
            # está abusando no recupera hueco por chocar contra el freno.
            if not _ventana.hit(limite, clave, request.url.path):
                # Se lanza el error del propio proyecto y no el de `slowapi`: así
                # el cuerpo sale con el sobre del contrato (§8.6) sin depender de
                # la forma interna de una clase de terceros, que ya cambió una vez.
                raise AteneaError(
                    code="RATE_LIMITED",
                    details={
                        "limit": str(limite),
                        "retry_after_seconds": limite.GRANULARITY.seconds,
                    },
                )

    return comprobar


def montar_limitador(app: FastAPI) -> None:
    """Instala el freno en la aplicación.

    El middleware aplica el límite general a todas las rutas; los decoradores
    `@limitador.limit(...)` de cada router aprietan donde el contrato lo pide.
    """
    app.state.limiter = limitador
    app.add_exception_handler(RateLimitExceeded, _respuesta_de_freno)
    app.add_middleware(SlowAPIMiddleware)


__all__ = ["clave_de_cubo", "freno", "limitador", "montar_limitador"]
