.PHONY: help up down restart logs ps build \
        migrate migration backend-shell db-shell \
        backend-venv backend-install test lint fmt clean

help:
	@echo "TrialLens Lite - common commands"
	@echo ""
	@echo "  make up              Build and start the full stack (db, backend, frontend)"
	@echo "  make down            Stop the stack"
	@echo "  make restart         Restart the stack"
	@echo "  make logs            Tail logs for all services"
	@echo "  make ps              Show container status"
	@echo "  make build           Rebuild backend/frontend images"
	@echo ""
	@echo "  make migrate         Run Alembic migrations inside the backend container"
	@echo "  make migration m=... Autogenerate a new Alembic revision named 'm'"
	@echo "  make backend-shell   Open a shell in the running backend container"
	@echo "  make db-shell        Open a psql shell in the running db container"
	@echo ""
	@echo "  make backend-venv    Create a local Python 3.12 virtualenv for the backend"
	@echo "  make backend-install Install backend deps into .venv (requires network)"
	@echo "  make test            Run pytest (uses .venv if present, else system python)"
	@echo "  make lint            Run ruff over the backend"
	@echo "  make clean           Remove containers, volumes, and local caches"

up:
	docker compose up --build

down:
	docker compose down

restart: down up

logs:
	docker compose logs -f

ps:
	docker compose ps

build:
	docker compose build

migrate:
	docker compose exec backend alembic upgrade head

migration:
	docker compose exec backend alembic revision --autogenerate -m "$(m)"

backend-shell:
	docker compose exec backend /bin/bash

db-shell:
	docker compose exec db psql -U $${POSTGRES_USER:-triallens} -d $${POSTGRES_DB:-triallens}

backend-venv:
	python3.12 -m venv backend/.venv
	@echo "Activate with: source backend/.venv/bin/activate"

backend-install:
	backend/.venv/bin/pip install --upgrade pip
	backend/.venv/bin/pip install -r backend/requirements-dev.txt

test:
	@if [ -x backend/.venv/bin/pytest ]; then \
		PYTHONPATH=backend backend/.venv/bin/pytest; \
	else \
		PYTHONPATH=backend python3.12 -m pytest; \
	fi

lint:
	@if [ -x backend/.venv/bin/ruff ]; then \
		backend/.venv/bin/ruff check backend; \
	else \
		ruff check backend; \
	fi

clean:
	docker compose down -v
	rm -rf backend/.venv frontend/node_modules frontend/.next
