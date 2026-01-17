# CLAUDE.md

## Project Overview

**slack_analytics_app** - FastAPI application generated with [Full-Stack FastAPI + Next.js Template](https://github.com/vstorm-co/full-stack-fastapi-nextjs-llm-template).

**Stack:** FastAPI + Pydantic v2, PostgreSQL (async), LangGraph

## Commands

```bash
cd backend

# Using Make (recommended)
make dev              # Start dev server
make test             # Run tests
make check            # Lint + format
make migrate          # Apply migrations
make migrate-create   # Create new migration
make evals            # Run evaluations
make evals-quick      # Quick evaluation (5 traces)

# Or directly with uv
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run ruff check . --fix && uv run ruff format .
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "Description"
uv run python -m evals.main

# Docker
docker compose up -d
```

## Project Structure

```
backend/
├── app/
│   ├── api/routes/       # HTTP endpoints (health.py, slack.py)
│   ├── services/         # Business logic (agent.py, slack.py)
│   ├── repositories/     # Data access (checkpoint.py)
│   ├── schemas/          # Pydantic models
│   ├── db/models/        # Database models (checkpoint.py)
│   ├── core/             # Config, middleware, logging
│   ├── agents/           # AI agents
│   │   ├── checkpointer.py   # PostgresCheckpointer
│   │   └── assistant/        # Agent graph, nodes, tools
│   └── commands/         # CLI commands
├── evals/                # Agent evaluation (pydantic-evals)
│   ├── main.py           # CLI: uv run python -m evals.main
│   ├── dataset.py        # Test cases
│   └── evaluator.py      # Custom evaluators
└── Makefile              # Common commands
```

## API Routes

Routes are mounted at root level:
- `/health` - Health check
- `/slack/events` - Slack webhook

## AI Agent

Uses `AgentService` for running the LangGraph ReAct agent:

```python
from app.services.agent import AgentService
from app.db.session import get_db_context

async with get_db_context() as db:
    agent_service = AgentService(db)
    output, tool_events = await agent_service.run(
        user_input="Hello",
        thread_id="my-thread",  # Same thread_id = resume conversation
    )
```

- **Add tools:** `app/agents/assistant/tools.py`
- **Modify prompts:** `app/agents/assistant/prompts.py`
- **Checkpoints:** Stored in `agent_checkpoints` table

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
