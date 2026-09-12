#!/usr/bin/env bash
# Comandos habituales de desarrollo de Atenea (Linux, macOS, Git Bash y WSL).
#
# Uso:  ./scripts/dev.sh <comando> [argumentos]
#       ./scripts/dev.sh help
#
# Todos los comandos de Python se ejecutan desde `backend/`, que es donde viven
# `alembic.ini` y el paquete `app`.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
PYTHON="${PYTHON:-python}"

en_backend() { cd "$BACKEND"; }
en_raiz()    { cd "$ROOT"; }

ayuda() {
  cat <<'EOF'

Atenea - comandos de desarrollo

  install    Instala requirements.txt y requirements-dev.txt
  db         Levanta PostgreSQL 16 + pgvector (docker compose up -d db)
  db-stop    Para los contenedores
  db-reset   Borra el volumen de datos y vuelve a levantar la base (DESTRUCTIVO)
  db-shell   Abre psql dentro del contenedor atenea-db
  migrate    alembic upgrade head
  downgrade  alembic downgrade -1  (o: downgrade base)
  revision   alembic revision --autogenerate -m "<mensaje>"
  seed       Carga las semillas (python -m app.seeds)
  api        uvicorn app.main:app --reload
  worker     python -m app.worker
  test       pytest -q
  lint       ruff check .
  format     ruff format . && ruff check --fix .
  check      alembic check (deriva entre modelos y base de datos)
  tables     Imprime las tablas de Base.metadata y las de la base real

EOF
}

comando="${1:-help}"
shift || true

case "$comando" in
  help|--help|-h) ayuda ;;

  install)
    en_backend
    "$PYTHON" -m pip install -r requirements.txt -r requirements-dev.txt
    ;;

  db)
    en_raiz
    docker compose up -d db
    echo "Base de datos en postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea"
    ;;

  db-stop)
    en_raiz
    docker compose down
    ;;

  db-reset)
    echo "AVISO: esto BORRA todos los datos locales de Atenea." >&2
    en_raiz
    docker compose down -v
    docker compose up -d db
    sleep 5
    en_backend
    alembic upgrade head
    ;;

  db-shell)
    docker exec -it atenea-db psql -U atenea -d atenea
    ;;

  migrate)
    en_backend
    alembic upgrade head
    ;;

  downgrade)
    en_backend
    alembic downgrade "${1:--1}"
    ;;

  revision)
    if [ $# -eq 0 ]; then
      echo 'Indica el mensaje: ./scripts/dev.sh revision "descripcion del cambio"' >&2
      exit 2
    fi
    en_backend
    alembic revision --autogenerate -m "$*"
    ;;

  seed)
    en_backend
    "$PYTHON" -m app.seeds
    ;;

  api)
    en_backend
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    ;;

  worker)
    en_backend
    "$PYTHON" -m app.worker
    ;;

  test)
    en_backend
    "$PYTHON" -m pytest -q "$@"
    ;;

  lint)
    en_backend
    ruff check .
    ;;

  format)
    en_backend
    ruff format .
    ruff check --fix .
    ;;

  check)
    en_backend
    alembic check
    ;;

  tables)
    en_backend
    "$PYTHON" - <<'PY'
import app.models  # noqa: F401
from sqlalchemy import create_engine, inspect

from app.core.config import settings
from app.core.db import Base

meta = sorted(Base.metadata.tables)
print(len(meta), "tablas en Base.metadata")
real = sorted(
    t for t in inspect(create_engine(settings.database_url)).get_table_names()
    if t != "alembic_version"
)
print(len(real), "tablas en la base")
print("faltan en la base:", sorted(set(meta) - set(real)) or "ninguna")
print("sobran en la base:", sorted(set(real) - set(meta)) or "ninguna")
PY
    ;;

  *)
    echo "Comando desconocido: $comando" >&2
    ayuda
    exit 2
    ;;
esac
