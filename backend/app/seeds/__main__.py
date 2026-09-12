"""Punto de entrada de `python -m app.seeds`.

Es la forma en que invocan la siembra el Makefile, `scripts/dev.ps1`,
`scripts/dev.sh`, `docker-compose.yml` y las notas de despliegue. Sin este
archivo, Python responde que el paquete no se puede ejecutar directamente y
todos esos caminos fallan a la vez.

La siembra es idempotente: cada fila lleva un identificador derivado con uuid5
de su clave natural, así que volver a ejecutarla no duplica nada.
"""

from __future__ import annotations

import sys

from app.seeds.ejecutar import main

if __name__ == "__main__":
    sys.exit(main())
