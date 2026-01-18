# Slack Analytics App

A FastAPI application with LangGraph AI agents for Slack-based analytics queries. Users can ask natural language questions about their data, and the bot converts them to SQL, executes queries, and returns formatted results.

## Features

- **Analytics Chatbot** - Natural language to SQL conversion with intent routing
- **Slack Integration** - Responds to DMs and @mentions with Block Kit formatting
- **Conversation History** - Persistent chat history in PostgreSQL for context continuity
- **CSV Export** - Export query results with a button click
- **Evals Framework** - Evaluate agent responses with pydantic-evals

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Slack App Setup](#slack-app-setup)
- [ngrok Setup](#ngrok-setup)
- [Logfire Setup](#logfire-setup-optional)
- [Environment Variables](#environment-variables)
- [Development](#development)
- [Deployment](#deployment)
- [Commands Reference](#commands-reference)
- [Architecture](#architecture)
- [Documentation](#documentation)

## Prerequisites

- **Python 3.12+**
- **uv** - Fast Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **Docker** - For PostgreSQL (or a PostgreSQL 16+ instance)
- **ngrok** - For local Slack development ([install](https://ngrok.com/download))

## Quick Start

```bash
# 1. Clone and enter the project
git clone <repository-url>
cd slack-bot-agent

# 2. Install dependencies
make install

# 3. Configure environment
cp .env.example .env
# Edit .env with your API keys (see Environment Variables section)

# 4. Start PostgreSQL and apply migrations
make db-init

# 5. Seed sample analytics data (optional)
make db-seed

# 6. Start the development server
make run

# 7. Start ngrok (in a separate terminal)
ngrok http 8000
```

The API will be available at:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs
- **ngrok**: https://xxxxx.ngrok.io (use this URL for Slack webhooks)

**Next step**: Complete the [Slack App Setup](#slack-app-setup) and [ngrok Setup](#ngrok-setup).

## Slack App Setup

### Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Enter app name (e.g., "Analytics Bot") and select your workspace
4. Click **Create App**

### Step 2: Configure Bot Permissions

1. In the left sidebar, go to **OAuth & Permissions**
2. Scroll to **Scopes** → **Bot Token Scopes**
3. Add the following scopes:

| Scope | Purpose |
|-------|---------|
| `app_mentions:read` | Read messages where the bot is @mentioned |
| `channels:history` | Read messages in public channels |
| `channels:read` | View basic channel info |
| `chat:write` | Send messages as the bot |
| `files:write` | Upload CSV exports |
| `im:history` | Read direct message history |
| `im:read` | View basic DM info |
| `im:write` | Start direct messages |
| `users:read` | View user info (for display names) |

### Step 3: Install App to Workspace

1. Scroll to the top of **OAuth & Permissions**
2. Click **Install to Workspace**
3. Review permissions and click **Allow**
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

### Step 4: Get Signing Secret

1. In the left sidebar, go to **Basic Information**
2. Scroll to **App Credentials**
3. Copy the **Signing Secret**

### Step 5: Configure Environment Variables

Add tokens to your `.env` file:

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
```

### Step 6: Set Up Event Subscriptions (Local Development)

For local development, Slack needs a public URL to send events. Use ngrok:

```bash
# Start your server first
make run

# In another terminal, start ngrok
ngrok http 8000
```

Copy the ngrok URL (e.g., `https://abc123.ngrok.io`), then:

1. In Slack app settings, go to **Event Subscriptions**
2. Toggle **Enable Events** to ON
3. Set **Request URL** to: `https://YOUR_NGROK_URL/slack/events`
4. Wait for Slack to verify the URL (shows "Verified" ✓)
5. Under **Subscribe to bot events**, add:
   - `app_mention` - When bot is @mentioned
   - `message.channels` - Messages in public channels
   - `message.im` - Direct messages to the bot
6. Click **Save Changes**

### Step 7: Enable Interactivity (for buttons)

1. Go to **Interactivity & Shortcuts**
2. Toggle **Interactivity** to ON
3. Set **Request URL** to: `https://YOUR_NGROK_URL/slack/interactions`
4. Click **Save Changes**

### Step 8: Test the Bot

1. Invite the bot to a channel: `/invite @YourBotName`
2. Mention the bot: `@YourBotName How many users do we have?`
3. Or send a direct message to the bot

## ngrok Setup

ngrok creates a public URL that forwards to your local server, required for Slack webhooks during development.

1. **Create account** at [ngrok.com](https://ngrok.com) (free tier works)

2. **Install ngrok**:
   ```bash
   # macOS
   brew install ngrok

   # Linux
   curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
     | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
     && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
     | sudo tee /etc/apt/sources.list.d/ngrok.list \
     && sudo apt update && sudo apt install ngrok

   # Windows
   choco install ngrok
   ```

3. **Authenticate** (get token from [ngrok dashboard](https://dashboard.ngrok.com/get-started/your-authtoken)):
   ```bash
   ngrok config add-authtoken YOUR_AUTH_TOKEN
   ```

## Logfire Setup (Optional)

[Logfire](https://logfire.pydantic.dev) provides observability with tracing, logs, and metrics. Free tier available.

1. **Create account** at [logfire.pydantic.dev](https://logfire.pydantic.dev)

2. **Create a project** in the Logfire dashboard

3. **Get your write token**:
   - Go to your project → Settings → Write Tokens
   - Create a new token and copy it

4. **Add to `.env`**:
   ```bash
   LOGFIRE_TOKEN=your-write-token
   ```

Once configured, you'll see traces for:
- HTTP requests and responses
- LLM calls (OpenAI)
- Database queries (asyncpg)
- Agent workflow execution

## Environment Variables

Create a `.env` file from the example:

```bash
cp .env.example .env
```

### Required Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for LLM calls |
| `SLACK_BOT_TOKEN` | Slack bot token (starts with `xoxb-`) |
| `SLACK_SIGNING_SECRET` | Slack app signing secret |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `local` | Environment name (`local`, `production`) |
| `DEBUG` | `true` | Enable debug mode |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_USER` | `postgres` | PostgreSQL user |
| `POSTGRES_PASSWORD` | `postgres` | PostgreSQL password |
| `POSTGRES_DB` | `slack_analytics_app` | PostgreSQL database |
| `AI_MODEL` | `gpt-4.1` | OpenAI model for analytics |
| `LOGFIRE_TOKEN` | - | Logfire token for observability |

## Development

### Running Locally

```bash
# Start PostgreSQL only
make docker-db

# Apply database migrations
make db-upgrade

# Seed sample data (optional)
make db-seed

# Start dev server with hot reload
make run
```

### Code Quality

```bash
# Run linter
make lint

# Auto-format code
make format

# Run tests
make test

# Run evaluations
make evals
```

### Database Management

```bash
# Create a new migration
make db-migrate

# Apply migrations
make db-upgrade

# Rollback last migration
make db-downgrade

# Show current migration
make db-current
```

## Deployment

### Option 1: Docker Compose (Development)

Run the full stack with Docker:

```bash
# Start all services (app + PostgreSQL)
make docker-up

# View logs
make docker-logs

# Stop services
make docker-down
```

### Option 2: Docker Compose (Production)

For production deployment:

```bash
# 1. Create production environment file
cp .env.example .env.prod
# Edit .env.prod with production values

# 2. Start production stack
make docker-prod

# 3. View logs
make docker-prod-logs
```

Production configuration includes:
- 4 Uvicorn workers
- Resource limits (CPU/memory)
- Internal-only database network
- No debug mode

### Updating Slack Webhooks for Production

When deploying to production, update your Slack app URLs:

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Your App
2. **Event Subscriptions**: Change Request URL to `https://your-domain.com/slack/events`
3. **Interactivity**: Change Request URL to `https://your-domain.com/slack/interactions`
4. Save changes

## Commands Reference

```bash
# Setup
make install          # Install dependencies + pre-commit hooks

# Development
make run              # Start dev server (with hot reload)
make test             # Run tests
make evals            # Run evaluations (18 cases)
make evals-quick      # Quick evaluation (3 cases)
make lint             # Check code quality
make format           # Auto-format code

# Database
make db-init          # Initialize database (start + migrate)
make db-migrate       # Create new migration
make db-upgrade       # Apply migrations
make db-seed          # Seed sample data
make db-downgrade     # Rollback last migration

# Docker (Development)
make docker-up        # Start all services
make docker-down      # Stop services
make docker-logs      # View logs
make docker-db        # Start PostgreSQL only

# Docker (Production)
make docker-prod      # Start production stack
make docker-prod-down # Stop production stack
make docker-prod-logs # View production logs

# Other
make routes           # Show all API routes
make clean            # Clean cache files
make help             # Show all commands
```

## Architecture

See [System Architecture](docs/system-architecture.md) for detailed diagrams.

### Project Structure

```
├── app/
│   ├── api/routes/           # HTTP endpoints (slack.py, health.py)
│   ├── services/             # Business logic (agent.py, slack.py)
│   ├── repositories/         # Data access layer
│   ├── agents/
│   │   ├── checkpointer.py   # PostgresCheckpointer
│   │   └── analytics_chatbot/# Analytics SQL chatbot
│   │       ├── graph.py      # LangGraph workflow
│   │       ├── nodes/        # Node implementations
│   │       └── prompts.py    # LLM prompts
│   ├── db/models/            # SQLAlchemy models
│   └── schemas/              # Pydantic models
├── evals/                    # Agent evaluation framework
├── tests/                    # pytest test suite
├── alembic/                  # Database migrations
└── docs/                     # Documentation
```

## Documentation

For detailed documentation, see the `docs/` folder:

- **[System Architecture](docs/system-architecture.md)** - AWS deployment architecture and costs
- **[Agent Architecture](docs/agent_architecture.md)** - Analytics chatbot design
- **[Database Patterns](docs/database_skill.md)** - Repository and service patterns
- **[Testing Guide](docs/testing.md)** - Testing best practices

## Pre-Production Checklist

**Security (done):** Read-only DB, SQL allowlisting, Slack signature verification (HMAC-SHA256)

**P0 — Must Have:**
- SQL runtime validation
- User permissions management
- Cost alerts (AWS + LLM)

See [Future Improvements](docs/Future%20Improvements.md) for the full roadmap.

## Troubleshooting

### Slack not receiving events

1. Ensure ngrok is running and the URL is correct
2. Check that Event Subscriptions shows "Verified"
3. Verify `SLACK_SIGNING_SECRET` matches your app
4. Check server logs for signature validation errors

### Bot not responding

1. Ensure `SLACK_BOT_TOKEN` is correct
2. Check the bot has been invited to the channel
3. Verify bot scopes are configured correctly
4. Check server logs for errors

### Database connection issues

1. Ensure PostgreSQL is running: `make docker-db`
2. Verify `.env` has correct database credentials
3. Run migrations: `make db-upgrade`

### ngrok URL changes

Every time ngrok restarts, you get a new URL. Update:
1. Event Subscriptions Request URL
2. Interactivity Request URL

Consider using a paid ngrok plan for a stable URL, or deploy to production.
