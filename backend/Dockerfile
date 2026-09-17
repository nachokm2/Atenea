# syntax=docker/dockerfile:1
#
# Imagen del backend de Atenea (API y worker comparten imagen; cambia el comando).
# Construccion desde la raiz del repositorio:  docker build -f backend/Dockerfile backend
# o, con docker compose, con `context: ./backend`.

FROM python:3.12-slim AS base

# 12-factor: sin .pyc, salida sin buffer, pip silencioso y sin cache.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=UTC

WORKDIR /app

# Dependencias del sistema: `psycopg[binary]` no necesita compilar, pero curl sirve
# para el healthcheck y libpq-dev/gcc quedan fuera a proposito (imagen mas pequena).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Capa de dependencias primero: se reaprovecha mientras requirements.txt no cambie.
#
# Ese archivo lo genera pip-compile con el cierre transitivo entero fijado, no
# se edita a mano: las directas estan en requirements.in. Asi la imagen que se
# despliega es exactamente la que se probo, y no una resuelta al construir.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Codigo de la aplicacion y utillaje de migraciones.
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Usuario sin privilegios: nada se ejecuta como root.
RUN useradd --create-home --uid 10001 atenea \
    && mkdir -p /app/storage \
    && chown -R atenea:atenea /app
USER atenea

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT:-8000}/health || exit 1

# La API. El worker usa la misma imagen con `command: python -m app.worker`.
# `sh -c` para que $PORT (que Railway inyecta) se expanda en tiempo de ejecucion.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
