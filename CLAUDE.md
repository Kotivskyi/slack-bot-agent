# CLAUDE.md

## Project Overview

**slack_analytics_app** - FastAPI application generated with [Full-Stack FastAPI + Next.js Template](https://github.com/vstorm-co/full-stack-fastapi-nextjs-llm-template).

**Stack:** FastAPI + Pydantic v2, PostgreSQL (async), LangGraph

## Commands

```bash
# Backend
cd backend
uv run uvicorn app.main:app --reload --port 8000
pytest
ruff check . --fix && ruff format .

# Database
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "Description"

# Docker
docker compose up -d
```

## Project Structure

```
backend/app/
├── api/routes/       # HTTP endpoints (root-level, no versioning)
├── services/         # Business logic
├── repositories/     # Data access
├── schemas/          # Pydantic models
├── db/models/        # Database models
├── core/config.py    # Settings
├── agents/           # AI agents
└── commands/         # CLI commands
```

## API Routes

Routes are mounted at root level:
- `/health` - Health check
- `/items` - Items CRUD
- `/conversations` - Conversation management
- `/agent/ws` - WebSocket for AI agent

## Key Conventions

- Use `db.flush()` in repositories (not `commit`)
- Services raise domain exceptions (`NotFoundError`, `AlreadyExistsError`)
- Schemas: separate `Create`, `Update`, `Response` models
- Commands auto-discovered from `app/commands/`

## Where to Find More Info

Before starting complex tasks, read relevant docs:
- **Architecture details:** `docs/architecture.md`
- **Adding features:** `docs/adding_features.md`
- **Testing guide:** `docs/testing.md`
- **Code patterns:** `docs/patterns.md`

## Environment Variables

Key variables in `.env`:
```bash
ENVIRONMENT=local
POSTGRES_HOST=localhost
POSTGRES_PASSWORD=secret
OPENAI_API_KEY=sk-...
LOGFIRE_TOKEN=your-token
```
