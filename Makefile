.PHONY: install format lint test evals evals-analytics evals-analytics-quick run clean help db-init db-seed

# === Setup ===
install:
	uv sync --dev
	@if git rev-parse --git-dir > /dev/null 2>&1; then \
		uv run pre-commit install; \
	else \
		echo "⚠️  Not a git repository - skipping pre-commit install"; \
		echo "   Run 'git init && make install' to set up pre-commit hooks"; \
	fi
	@echo ""
	@echo "✅ Installation complete!"
	@echo ""
	@echo "Next steps:"
	@echo "  • make docker-db        # Start PostgreSQL"
	@echo "  • make db-upgrade       # Apply migrations"
	@echo "  • make run              # Start development server"
	@echo ""
	@echo "Note: .env is pre-configured for development"

# === Code Quality ===
format:
	uv run ruff format app tests cli
	uv run ruff check app tests cli --fix

lint:
	uv run ruff check app tests cli
	uv run ruff format app tests cli --check
	uv run mypy app

# === Testing ===
test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

evals:
	uv run python -m evals.main

evals-analytics:
	uv run python -m evals.main --analytics

evals-analytics-quick:
	uv run python -m evals.main --analytics --quick

# === Database ===
db-init: docker-db
	@echo "Waiting for PostgreSQL to be ready..."
	@sleep 3
	uv run slack_analytics_app db upgrade
	@echo ""
	@echo "✅ Database initialized!"

db-migrate:
	@read -p "Migration message: " msg; \
	uv run slack_analytics_app db migrate -m "$$msg"

db-upgrade:
	uv run slack_analytics_app db upgrade

db-seed:
	uv run slack_analytics_app cmd seed

db-downgrade:
	uv run slack_analytics_app db downgrade

db-current:
	uv run slack_analytics_app db current

db-history:
	uv run slack_analytics_app db history

# === Server ===
run:
	uv run slack_analytics_app server run --reload

run-prod:
	uv run slack_analytics_app server run --host 0.0.0.0 --port 8000

routes:
	uv run slack_analytics_app server routes

# === Docker: Backend (Development) ===
docker-up:
	docker-compose up -d
	@echo ""
	@echo "✅ Backend services started!"
	@echo "   API: http://localhost:8000"
	@echo "   Docs: http://localhost:8000/docs"
	@echo "   PostgreSQL: localhost:5432"

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-build:
	docker-compose build

docker-shell:
	docker-compose exec app /bin/bash

# === Docker: Production (with Traefik) ===
docker-prod:
	docker-compose -f docker-compose.prod.yml up -d
	@echo ""
	@echo "✅ Production services started with Traefik!"
	@echo ""
	@echo "Endpoints (replace DOMAIN with your domain):"
	@echo "   API: https://api.$$DOMAIN"
	@echo "   Traefik: https://traefik.$$DOMAIN"

docker-prod-down:
	docker-compose -f docker-compose.prod.yml down

docker-prod-logs:
	docker-compose -f docker-compose.prod.yml logs -f

docker-prod-build:
	docker-compose -f docker-compose.prod.yml build

# === Docker: Individual Services ===
docker-db:
	docker-compose up -d db
	@echo ""
	@echo "✅ PostgreSQL started on port 5432"
	@echo "   Connection: postgresql://postgres:postgres@localhost:5432/slack_analytics_app"

docker-db-stop:
	docker-compose stop db

# === Cleanup ===
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml

# === Help ===
help:
	@echo ""
	@echo "slack_analytics_app - Available Commands"
	@echo "======================================"
	@echo ""
	@echo "Setup:"
	@echo "  make install       Install dependencies + pre-commit hooks"
	@echo ""
	@echo "Development:"
	@echo "  make run                  Start dev server (with hot reload)"
	@echo "  make test                 Run tests"
	@echo "  make evals                Run generic agent evaluations"
	@echo "  make evals-analytics      Run analytics chatbot evaluations"
	@echo "  make evals-analytics-quick Quick analytics evals (3 cases)"
	@echo "  make lint                 Check code quality"
	@echo "  make format               Auto-format code"
	@echo ""
	@echo "Database:"
	@echo "  make db-init       Initialize database (start + migrate)"
	@echo "  make db-migrate    Create new migration"
	@echo "  make db-upgrade    Apply migrations"
	@echo "  make db-seed       Seed database with sample data"
	@echo "  make db-downgrade  Rollback last migration"
	@echo "  make db-current    Show current migration"
	@echo ""
	@echo "Docker (Development):"
	@echo "  make docker-up            Start backend services"
	@echo "  make docker-down          Stop all services"
	@echo "  make docker-logs          View backend logs"
	@echo "  make docker-build         Build backend images"
	@echo "  make docker-db            Start only PostgreSQL"
	@echo ""
	@echo "Docker (Production with Traefik):"
	@echo "  make docker-prod          Start production stack"
	@echo "  make docker-prod-down     Stop production stack"
	@echo "  make docker-prod-logs     View production logs"
	@echo ""
	@echo "Other:"
	@echo "  make routes        Show all API routes"
	@echo "  make clean         Clean cache files"
	@echo ""
