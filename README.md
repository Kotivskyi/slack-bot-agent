# Slack Analytics App

FastAPI application with LangGraph AI agents.

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
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_SIGNING_SECRET=your-secret
```

### Test

```bash
# Verify the endpoint responds
curl -X POST localhost:8000/slack/events \
  -H "Content-Type: application/json" \
  -H "X-Slack-Request-Timestamp: $(date +%s)" \
  -H "X-Slack-Signature: v0=test" \
  -d '{"type":"url_verification","challenge":"test123"}'
```

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

## Architecture

```mermaid
graph TB
    subgraph Backend["Backend (FastAPI)"]
        API[API Routes]
        Services[Services Layer]
        Repos[Repositories]
        Agent[AI Agent]
    end

    subgraph Infrastructure
        DB[(PostgreSQL)]
    end

    subgraph External
        LLM[OpenAI/Anthropic]
    end

    API --> Services
    Services --> Repos
    Services --> Agent
    Repos --> DB
    Agent --> LLM
```

### Layered Architecture

The backend follows a **Repository + Service** pattern:

| Layer | Responsibility |
|-------|---------------|
| **Routes** | HTTP handling, validation |
| **Services** | Business logic, orchestration |
| **Repositories** | Data access, queries |

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app with lifespan
│   ├── api/
│   │   ├── routes/          # API endpoints
│   │   ├── deps.py          # Dependency injection
│   │   └── router.py        # Route aggregation
│   ├── core/config.py       # Settings
│   ├── db/models/           # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   ├── repositories/        # Data access layer
│   ├── services/            # Business logic
│   ├── agents/              # AI agents
│   └── commands/            # CLI commands
├── tests/                   # pytest test suite
└── alembic/                 # Database migrations
```

## Key Conventions

- Use `db.flush()` in repositories (not `commit`)
- Services raise domain exceptions (`NotFoundError`, `AlreadyExistsError`)
- Schemas: separate `Create`, `Update`, `Response` models

## Documentation

For more details, see the `docs/` folder:
- `docs/architecture.md` - Architecture details
- `docs/adding_features.md` - Adding new features
- `docs/testing.md` - Testing guide
- `docs/patterns.md` - Code patterns
