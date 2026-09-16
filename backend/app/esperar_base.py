"""Espera a que la base conteste antes de migrar.

Corre delante de `alembic upgrade head` en el arranque de Railway, y existe por
una carrera que solo se pierde en la nube.

La base vive en la red privada de Railway —`postgres.railway.internal`, que no
paga salida ni queda expuesta a internet—, y esa red **tarda unos segundos en
levantarse dentro del contenedor**. Alembic arranca de inmediato, así que el
primer despliegue moría con `psycopg.errors.ConnectionTimeout` teniendo la base
perfectamente viva al lado: el contenedor todavía no sabía llegar a ella.

Esperar un número fijo de segundos también funcionaría, y sería peor de dos
maneras: se paga la espera entera aunque la red esté lista al primer intento, y
el día que tarde un segundo más vuelve a fallar. Esto pregunta.

Lo que **no** hace es ocultar un fallo de verdad. Si al cabo del plazo la base
sigue sin contestar, sale con código 1 y el despliegue se detiene con el último
error en pantalla, que es justo lo que hay que leer.
"""

from __future__ import annotations

import sys
import time

import sqlalchemy as sa
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

#: Cuánto se espera en total, en segundos.
#:
#: La red privada suele estar lista en dos o tres; un minuto deja margen de
#: sobra para una base que además se esté iniciando por primera vez, sin llegar
#: a parecer que el despliegue se ha colgado.
PLAZO = 60.0

#: Cuánto se espera entre intentos.
PAUSA = 2.0

#: Cuánto se le da a cada intento antes de darlo por perdido.
#:
#: Corto a propósito: mientras la red no está, conectar no falla rápido, se
#: queda esperando. Sin este tope el primer intento se comería el plazo entero.
TIMEOUT = 3


def esperar(plazo: float = PLAZO) -> bool:
    """Pregunta a la base hasta que conteste. `True` si llegó a contestar."""
    motor = sa.create_engine(
        settings.database_url,
        connect_args={"connect_timeout": TIMEOUT},
        pool_pre_ping=False,
    )
    limite = time.monotonic() + plazo
    intento = 0
    ultimo: Exception | None = None

    while time.monotonic() < limite:
        intento += 1
        try:
            with motor.connect() as conexion:
                conexion.execute(sa.text("SELECT 1"))
            logger.info("base.lista", intento=intento)
            return True
        except Exception as error:  # cualquier fallo aquí significa «todavía no»
            ultimo = error
            time.sleep(PAUSA)

    logger.error("base.no_contesta", intentos=intento, error=str(ultimo))
    return False


def main() -> int:
    if esperar():
        return 0
    # Por stderr y no por el registro estructurado: esto lo lee una persona
    # mirando la consola de un despliegue que acaba de detenerse.
    print(
        "La base de datos no contestó a tiempo. Si es el primer despliegue, "
        "comprueba que el servicio de postgres está en marcha y que "
        "DATABASE_URL apunta a él.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
