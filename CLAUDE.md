# CLAUDE.md

## Project Overview

**slack_analytics_app** - FastAPI application generated with [Full-Stack FastAPI + Next.js Template](https://github.com/vstorm-co/full-stack-fastapi-nextjs-llm-template).

**Stack:** FastAPI + Pydantic v2, PostgreSQL (async), LangGraph

## Commands

```bash
# Using Make (from project root)
make run              # Start dev server (with hot reload)
make test             # Run tests
make evals            # Run analytics chatbot evaluations (18 cases)
make evals-quick      # Quick evaluation (3 cases)
make lint             # Check code quality
make format           # Auto-format code
make db-init          # Initialize database (start + migrate)
make db-upgrade       # Apply migrations
make db-seed          # Seed database with sample data
make db-migrate       # Create new migration

# Or directly with uv
uv run slack_analytics_app server run --reload
uv run pytest
uv run ruff check . --fix && uv run ruff format .

# Docker
make docker-db        # Start PostgreSQL only
make docker-up        # Start all backend services
```

## Project Structure

```
├── docs/                     # Documentation
│   ├── database_skill.md     # Database & repository patterns
│   ├── agent_architecture.md # Analytics chatbot docs
│   ├── patterns.md           # General patterns
│   ├── testing.md            # Testing guide
│   └── ...
├── app/
│   ├── api/routes/           # HTTP endpoints (health.py, slack.py)
│   ├── services/             # Business logic (agent.py, slack.py)
│   ├── repositories/         # Data access (checkpoint.py, conversation.py, analytics.py)
│   ├── schemas/              # Pydantic models
│   ├── db/models/            # Database models (checkpoint.py, conversation.py)
│   ├── core/                 # Config, middleware, logging
│   ├── agents/               # AI agents
│   │   ├── checkpointer.py   # PostgresCheckpointer
│   │   └── analytics_chatbot/# Analytics SQL chatbot
│   │       ├── graph.py      # LangGraph workflow
│   │       ├── state.py      # ChatbotState
│   │       ├── prompts.py    # LLM prompts
│   │       ├── routing.py    # Conditional routing
│   │       └── nodes/        # Node implementations
│   └── commands/             # CLI commands
├── evals/                    # Agent evaluation (pydantic-evals)
│   ├── main.py               # CLI: uv run python -m evals.main
│   ├── analytics_dataset.py  # Test cases (18 cases)
│   └── evaluator.py          # Custom evaluators
├── tests/                    # pytest test suite
└── alembic/                  # Database migrations
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
    # response.generated_sql - SQL query (if generated)
    # response.action_id - UUID for button lookups
```

**Features:**
- Intent routing (analytics, follow-up, export, show SQL, off-topic)
- Natural language to SQL conversion with retry on execution errors
- Slack Block Kit formatting with action buttons (UUID-based lookups)
- CSV export and SQL retrieval without LLM calls
- Message truncation for Slack API limits

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
- **System architecture:** `docs/system-architecture.md`

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


# Adding New Features

## Adding a New API Endpoint

1. **Create schema** in `schemas/`
   ```python
   # schemas/item.py
   class ItemCreate(BaseModel):
       name: str
       description: str | None = None

   class ItemResponse(BaseModel):
       id: UUID
       name: str
       created_at: datetime
   ```

2. **Create model** in `db/models/` (if new entity)
   ```python
   # db/models/item.py
   class Item(Base):
       __tablename__ = "items"
       id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
       name: Mapped[str] = mapped_column(String(255))
   ```

3. **Create repository** in `repositories/`
   ```python
   # repositories/item.py
   class ItemRepository:
       async def create(self, db: AsyncSession, **kwargs) -> Item:
           item = Item(**kwargs)
           db.add(item)
           await db.flush()
           await db.refresh(item)
           return item
   ```

4. **Create service** in `services/`
   ```python
   # services/item.py
   class ItemService:
       def __init__(self, db: AsyncSession):
           self.db = db
           self.repo = ItemRepository()

       async def create(self, item_in: ItemCreate) -> Item:
           return await self.repo.create(self.db, **item_in.model_dump())
   ```

5. **Create route** in `api/routes/`
   ```python
   # api/routes/items.py
   router = APIRouter()

   @router.post("/", response_model=ItemResponse, status_code=201)
   async def create_item(
       item_in: ItemCreate,
       db: AsyncSession = Depends(get_db),
   ):
       service = ItemService(db)
       return await service.create(item_in)
   ```

6. **Register route** in `api/router.py`
   ```python
   from app.api.routes import items
   api_router.include_router(items.router, prefix="/items", tags=["items"])
   ```

## Adding a Custom CLI Command

Commands are auto-discovered from `app/commands/`.

```python
# app/commands/my_command.py
from app.commands import command, success, error
import click

@command("my-command", help="Description of what this does")
@click.option("--name", "-n", required=True, help="Name parameter")
def my_command(name: str):
    # Your logic here
    success(f"Done: {name}")
```

Run with: `uv run slack_analytics_app cmd my-command --name test`

## Adding a Database Migration

```bash
# Create migration
uv run alembic revision --autogenerate -m "Add items table"

# Apply migration
uv run alembic upgrade head

# Or use CLI
uv run slack_analytics_app db migrate -m "Add items table"
uv run slack_analytics_app db upgrade
