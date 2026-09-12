# Comandos de desarrollo de Atenea.
# Equivalente a scripts/dev.sh y scripts/dev.ps1; usalo si tienes `make`.
#
#   make db && make migrate && make api

SHELL   := /bin/bash
PYTHON  ?= python
BACKEND := backend

.DEFAULT_GOAL := help
.PHONY: help install db db-stop db-reset db-shell migrate downgrade downgrade-base \
        revision seed api worker test lint format check tables build up down logs

help: ## Lista los comandos disponibles
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Instala dependencias de ejecucion y de desarrollo
	cd $(BACKEND) && $(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

db: ## Levanta PostgreSQL 16 + pgvector en el puerto 55432
	docker compose up -d db
	@echo "postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea"

db-stop: ## Para los contenedores
	docker compose down

db-reset: ## DESTRUCTIVO: borra el volumen, recrea la base y migra
	docker compose down -v
	docker compose up -d db
	sleep 5
	cd $(BACKEND) && alembic upgrade head

db-shell: ## Abre psql en el contenedor atenea-db
	docker exec -it atenea-db psql -U atenea -d atenea

migrate: ## Aplica las migraciones (alembic upgrade head)
	cd $(BACKEND) && alembic upgrade head

downgrade: ## Revierte una migracion
	cd $(BACKEND) && alembic downgrade -1

downgrade-base: ## Revierte TODAS las migraciones
	cd $(BACKEND) && alembic downgrade base

revision: ## Nueva migracion autogenerada: make revision m="mensaje"
	@test -n "$(m)" || (echo 'Falta el mensaje: make revision m="descripcion"'; exit 2)
	cd $(BACKEND) && alembic revision --autogenerate -m "$(m)"

seed: ## Carga las semillas del juego
	cd $(BACKEND) && $(PYTHON) -m app.seeds

api: ## Arranca la API con recarga en caliente
	cd $(BACKEND) && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker: ## Arranca el worker de generation_jobs
	cd $(BACKEND) && $(PYTHON) -m app.worker

test: ## Pasa la suite de pruebas
	cd $(BACKEND) && $(PYTHON) -m pytest -q

lint: ## ruff check
	cd $(BACKEND) && ruff check .

format: ## ruff format + arreglos automaticos
	cd $(BACKEND) && ruff format . && ruff check --fix .

check: ## Comprueba deriva entre los modelos y la base de datos
	cd $(BACKEND) && alembic check

tables: ## Compara Base.metadata con las tablas reales
	./scripts/dev.sh tables

build: ## Construye las imagenes de docker compose
	docker compose build

up: ## Levanta base de datos + API (+ worker con --profile full)
	docker compose up -d --build

down: ## Para todo
	docker compose down

logs: ## Sigue los logs de la API
	docker compose logs -f api
