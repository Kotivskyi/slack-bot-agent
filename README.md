# Slack Analytics App

FastAPI application with LangGraph AI agents and PostgreSQL state persistence.

## Features

- **LangGraph ReAct Agent** - AI assistant with tool calling capabilities
- **PostgreSQL Checkpointing** - Persistent conversation state across sessions
- **Slack Integration** - Bot responds to DMs and mentions
- **Structured Logging** - JSON logs in production, readable logs in development
- **Evals Framework** - Evaluate agent responses against custom metrics

## Quick Start

```bash
# Install dependencies
cd backend
uv sync --dev

# Start PostgreSQL
docker-compose up -d db

# Apply migrations
uv run alembic upgrade head

# Start dev server
uv run uvicorn app.main:app --reload --port 8000
```

**Access:**
- API: http://localhost:8000
- Docs: http://localhost:8000/docs

## Slack Integration

### Setup ngrok (for local development)

Slack requires a public URL for webhooks. Use ngrok to expose your local server:

```bash
# Install ngrok (macOS)
brew install ngrok

# Authenticate (get token from https://ngrok.com)
ngrok config add-authtoken YOUR_AUTH_TOKEN

# Start tunnel
ngrok http 8000
```

### Configure Slack App

1. Create app at https://api.slack.com/apps
2. Enable Event Subscriptions with URL: `https://YOUR_NGROK_URL/slack/events`
3. Subscribe to events: `message.channels`, `message.im`, `app_mention`
4. Add bot scopes: `chat:write`, `channels:history`, `im:history`
5. Install to workspace

### Environment Variables

Add to `.env`:
```bash
# Required for AI Agent
OPENAI_API_KEY=sk-your-key

# Slack integration
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_SIGNING_SECRET=your-secret
```


## Commands

```bash
cd backend

# Using Make (recommended)
make dev              # Start dev server
make test             # Run tests
make check            # Lint + format
make migrate          # Apply migrations
make evals            # Run evaluations
make evals-quick      # Run quick evaluation (5 traces)

# Or directly with uv
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run ruff check . --fix && uv run ruff format .
uv run alembic upgrade head
uv run python -m evals.main

# Docker
docker compose up -d
```

### Checkpointing

Conversation state is automatically persisted to PostgreSQL:

```python
# Resume a conversation by using the same thread_id
output, _ = await agent_service.run(
    user_input="What did we discuss earlier?",
    thread_id="conversation-123",  # Same thread_id resumes context
)
```

### Adding Tools

Add tools in `app/agents/assistant/tools.py`:

```python
from langchain_core.tools import tool

@tool
def my_tool(param: str) -> str:
    """Tool description for the LLM."""
    return f"Result: {param}"

TOOLS = [current_datetime, my_tool]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
```

## Architecture

```mermaid
graph TB
    subgraph Backend["Backend (FastAPI)"]
        API[API Routes]
        Services[Services Layer]
        Repos[Repositories]
        Agent[AgentService]
        Checkpointer[PostgresCheckpointer]
    end

    subgraph Infrastructure
        DB[(PostgreSQL)]
    end

    subgraph External
        LLM[OpenAI]
        Slack[Slack API]
    end

    API --> Services
    Services --> Repos
    Services --> Agent
    Agent --> Checkpointer
    Repos --> DB
    Checkpointer --> DB
    Agent --> LLM
    Services --> Slack
```

### Layered Architecture

The backend follows a **Repository + Service** pattern:

| Layer | Responsibility |
|-------|---------------|
| **Routes** | HTTP handling, validation |
| **Services** | Business logic, AgentService |
| **Repositories** | Data access, checkpoint storage |

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app with lifespan
│   ├── api/
│   │   ├── routes/          # API endpoints (slack.py, health.py, etc.)
│   │   ├── deps.py          # Dependency injection (AgentSvc, etc.)
│   │   └── router.py        # Route aggregation
│   ├── core/
│   │   ├── config.py        # Settings
│   │   ├── middleware.py    # LoggingContextMiddleware
│   │   └── logging_config.py # Structured logging setup
│   ├── db/models/           # SQLAlchemy models (checkpoint.py)
│   ├── schemas/             # Pydantic schemas
│   ├── repositories/        # Data access layer (checkpoint.py)
│   ├── services/            # Business logic (agent.py, slack.py)
│   ├── agents/
│   │   ├── checkpointer.py  # PostgresCheckpointer
│   │   └── assistant/       # Agent subpackage
│   │       ├── graph.py     # build_assistant_graph()
│   │       ├── nodes.py     # agent_node, tools_node
│   │       ├── state.py     # AgentState, AgentContext
│   │       ├── tools.py     # Agent tools
│   │       └── prompts.py   # System prompts
│   └── commands/            # CLI commands
├── evals/                   # Evaluation framework
│   ├── evaluator.py         # Core evaluation logic
│   ├── main.py              # CLI entry point
│   ├── schemas.py           # ScoreSchema, EvalReport
│   └── metrics/prompts/     # Metric definitions (*.md)
├── tests/                   # pytest test suite
└── alembic/                 # Database migrations
```

## Key Conventions

- Use `db.flush()` in repositories (not `commit`)
- Services raise domain exceptions (`NotFoundError`, `AlreadyExistsError`)
- Schemas: separate `Create`, `Update`, `Response` models

## Evaluations

Run agent evaluations against defined metrics:

```bash
cd backend

# Using Make
make evals            # Full evaluation
make evals-quick      # Quick mode (first 5 traces)

# Or directly with uv
uv run python -m evals.main
uv run python -m evals.main --quick
uv run python -m evals.main --no-report
```

### Adding Metrics

Create markdown files in `evals/metrics/prompts/`:

```markdown
# My Metric

Evaluate whether the agent's response meets criteria X.

## Scoring Guidelines

- **Score 1.0**: Excellent
- **Score 0.5**: Partial
- **Score 0.0**: Failed
```

Reports are saved to `evals/reports/`.

## Documentation

For more details, see the `docs/` folder:
- `docs/architecture.md` - Architecture details
- `docs/adding_features.md` - Adding new features
- `docs/testing.md` - Testing guide
- `docs/patterns.md` - Code patterns
