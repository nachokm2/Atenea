"""Punto de entrada de `python -m app.worker`.

Es el comando con el que arrancan el worker el Makefile, `scripts/dev.ps1`,
`scripts/dev.sh`, `docker-compose.yml`, el Dockerfile y las notas de despliegue
de Railway. Sin este archivo, ninguno de esos caminos levanta el procesador de
trabajos, y sin él no hay ingesta, ni diseño de Ruta, ni generación de módulos:
el aprendiz sube su material y se queda mirando la pantalla de generación.
"""

from __future__ import annotations

import sys

from app.worker.principal import main

if __name__ == "__main__":
    sys.exit(main())
