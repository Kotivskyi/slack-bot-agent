# CLAUDE.md

## Project Overview

**slack_analytics_app** - FastAPI application generated with [Full-Stack FastAPI + Next.js Template](https://github.com/vstorm-co/full-stack-fastapi-nextjs-llm-template).

**Stack:** FastAPI + Pydantic v2, PostgreSQL (async), LangGraph

## Commands

```bash
# Using Make (from project root)
make run              # Start dev server (with hot reload)
make test             # Run tests
make lint             # Check code quality
make format           # Auto-format code
make db-init          # Initialize database (start + migrate)
make db-upgrade       # Apply migrations
make db-migrate       # Create new migration

# Or directly with uv (from backend/)
cd backend
uv run slack_analytics_app server run --reload
uv run pytest
uv run ruff check . --fix && uv run ruff format .

# Docker
make docker-db        # Start PostgreSQL only
make docker-up        # Start all backend services
```

## Project Structure

```
├── docs/                     # Documentation (project root)
│   ├── database_skill.md     # Database & repository patterns
│   ├── agent_architecture.md # Analytics chatbot docs
│   ├── patterns.md           # General patterns
│   ├── testing.md            # Testing guide
│   └── ...
├── backend/
│   ├── app/
│   │   ├── api/routes/       # HTTP endpoints (health.py, slack.py)
│   │   ├── services/         # Business logic (agent.py, slack.py)
│   │   ├── repositories/     # Data access (checkpoint.py)
│   │   ├── schemas/          # Pydantic models
│   │   ├── db/models/        # Database models (checkpoint.py)
│   │   ├── core/             # Config, middleware, logging
│   │   ├── agents/           # AI agents
│   │   │   ├── checkpointer.py       # PostgresCheckpointer
│   │   │   ├── assistant/            # Generic agent (ReAct pattern)
│   │   │   └── analytics_chatbot/    # Analytics SQL chatbot
│   │   │       ├── graph.py          # LangGraph workflow
│   │   │       ├── state.py          # ChatbotState, CacheEntry
│   │   │       ├── prompts.py        # LLM prompts
│   │   │       ├── routing.py        # Conditional routing
│   │   │       └── nodes/            # Node implementations
│   │   └── commands/         # CLI commands
│   ├── evals/                # Agent evaluation (pydantic-evals)
│   │   ├── main.py           # CLI: uv run python -m evals.main
│   │   ├── dataset.py        # Test cases
│   │   └── evaluator.py      # Custom evaluators
│   └── Makefile              # Common commands
```

## API Routes

Routes are mounted at root level:
- `/health` - Health check
- `/slack/events` - Slack event webhook (messages, mentions)
- `/slack/interactions` - Slack interactive components (button clicks)

## AI Agents

### Generic Agent (ReAct Pattern)

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

### Analytics Chatbot

Uses `AnalyticsAgentService` for SQL-based analytics via Slack:

```python
from app.services.agent import AnalyticsAgentService
from app.db.session import get_db_context

async with get_db_context() as db:
    analytics_service = AnalyticsAgentService(db)
    response = await analytics_service.run(
        user_query="How many apps do we have?",
        thread_id="slack-thread-123",
        user_id="U12345",
        channel_id="C12345",
    )
    # response.text - Response text
    # response.slack_blocks - Slack Block Kit blocks
    # response.intent - Classified intent
```

**Features:**
- Intent routing (analytics, follow-up, export, show SQL, off-topic)
- Natural language to SQL conversion
- Result caching for cost optimization
- Slack Block Kit formatting with action buttons
- CSV export and SQL retrieval without LLM calls

**Documentation:** `docs/agent_architecture.md`

## Key Conventions

- Commands auto-discovered from `app/commands/`

### Database & Repository Patterns

**Repositories:**
- Always extend `BaseRepository` for entity repositories
- Use `db.flush()` (not `commit`) — let callers manage transactions
- Pass session to methods, don't store in `__init__`

**Services:**
- Store session in `__init__`, instantiate repositories
- Raise domain exceptions (`NotFoundError`, `AlreadyExistsError`) — never `HTTPException`
- Orchestrate business logic across repositories

**Schemas:**
- `XxxCreate` — required fields for creation
- `XxxUpdate` — all fields optional (partial updates)
- `XxxResponse` — all fields + timestamps, inherit from `BaseSchema`

**Session patterns:**
```python
# Routes: FastAPI dependency injection
@router.get("/users")
async def get_users(db: AsyncSession = Depends(get_db_session)):
    ...

# Background tasks: context manager
async with get_db_context() as db:
    ...

# Analytics (read-only, always rollbacks):
async with get_analytics_db_context() as db:
    ...
```

### Dependency Injection

Use FastAPI's `Depends` for:
- Database session management (`get_db_session`)
- Authentication/authorization
- Shared business logic reuse
- Configuration injection

### Async Patterns

Async everywhere in this project:
- Route handlers (`async def`)
- Database operations (`await db.execute()`)
- Background tasks
- External API calls

### Best Practices

| Do | Don't |
|----|-------|
| Async for DB, external APIs | Sync database drivers (blocks event loop) |
| Business logic in services | Business logic in route handlers |
| Domain exceptions in services | `HTTPException` in services |
| Type hints on all functions | Missing type annotations |
| Test all layers | Skip integration tests |

### Common Pitfalls

- **Blocking in async:** Using `psycopg2` instead of async driver
- **Fat routes:** DB queries and business logic directly in handlers
- **Commit in repos:** Use `flush()`, let caller manage transactions
- **Session in repo `__init__`:** Pass session to methods instead

**Full guide:** `docs/database_skill.md`

## Where to Find More Info

Before starting complex tasks, read relevant docs:
- **Database patterns:** `docs/database_skill.md`
- **Analytics chatbot:** `docs/agent_architecture.md`
- **Design document:** `langgraph_slack_chatbot_design.md`

## Environment Variables

Key variables in `.env`:
```bash
ENVIRONMENT=local
POSTGRES_HOST=localhost
POSTGRES_PASSWORD=secret
OPENAI_API_KEY=sk-...
LOGFIRE_TOKEN=your-token
LOGFIRE_READ_TOKEN=your-read-token  # For MCP server
```

## Runtime Logs Access

Two methods are available for Claude to access runtime logs:

### 1. File-based Logging

Application logs are written to `logs/app.log` in JSON format.

**To read recent logs:**
```bash
# Read the log file directly
Read logs/app.log

# Or tail recent entries
tail -100 logs/app.log
```

**Log format:** JSON with timestamp, level, logger, message, and context fields.

**Configuration:**
- Location: `logs/app.log`
- Max size: 10 MB per file
- Rotation: 5 backup files kept
- Format: JSON (for easy parsing)

### 2. Logfire MCP Server

The project includes Logfire MCP configuration in `.mcp.json` for querying traces.

**Setup:**
1. Get a read token from Logfire dashboard
2. Set `LOGFIRE_READ_TOKEN` environment variable
3. Claude Code will auto-discover the MCP server

**Usage:** Once configured, Claude can use Logfire MCP tools to:
- Search traces by span name or attributes
- View detailed span information
- Analyze errors and performance

**Example queries Claude can perform:**
- "Find all SQL generation spans from the last hour"
- "Show me errors in the analytics chatbot"
- "What's the average latency for intent classification?"
