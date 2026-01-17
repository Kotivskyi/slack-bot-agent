.PHONY: dev test lint format migrate migrate-create evals evals-quick docker-up docker-down

# Development
dev:
	uv run uvicorn app.main:app --reload --port 8000

# Testing
test:
	uv run pytest

test-cov:
	uv run pytest --cov=app --cov-report=term-missing

# Linting & Formatting
lint:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

format:
	uv run ruff format .

check: lint-fix format

# Database
migrate:
	uv run alembic upgrade head

migrate-create:
	@read -p "Migration message: " msg; \
	uv run alembic revision --autogenerate -m "$$msg"

migrate-down:
	uv run alembic downgrade -1

# Evaluations
evals:
	uv run python -m evals.main

evals-quick:
	uv run python -m evals.main --quick

# Docker
docker-up:
	docker compose up -d

docker-down:
	docker compose down

# Install dependencies
install:
	uv sync --dev
