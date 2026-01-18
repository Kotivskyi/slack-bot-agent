# Conversation History: How It Works

## Overview

The chatbot tracks conversation state in a single structure per thread:

| Component | Purpose | Used For |
|-----------|---------|----------|
| **`conversation_turns`** | Persist what was asked/answered + SQL | Context resolution, CSV export, SQL retrieval |

Each turn stores the SQL query directly, enabling CSV export by re-executing the stored SQL.

> **Reference:** This design aligns with the package structure in `app/agents/analytics_chatbot/` and the `ChatbotState` defined in `state.py`.

---

## Architecture Diagram

> **Reference:** This aligns with the flow diagram in `agent_architecture.md`

```
User Message → Intent Router → [Route by Intent]
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    │                               │                               │
    ▼                               ▼                               ▼
analytics_query              follow_up                    export_csv/show_sql/off_topic
    │                               │                               │
    │                               ▼                               │
    │                        Context Resolver                       │
    │                         (reads history)                       │
    │                               │                               │
    └───────────────┬───────────────┘                               │
                    ▼                                               │
              SQL Generator                                         │
                    │                                               │
                    ▼                                               │
              SQL Validator ──(invalid)──► Retry (max 2)            │
                    │          ──(max retries)──► Error Handler ────┤
                    ▼ (valid)                                       │
              SQL Executor                                          │
                    │                                               │
                    ▼                                               │
           Result Interpreter                                       │
                    │                                               │
                    ▼                                               │
           Response Formatter ◄─────────────────────────────────────┘
             (Slack Block Kit)               (reads SQL from history,
                    │                         re-executes for export)
                    ▼
             Send to Slack
```

**Data Flow:**
- `conversation_history` → read by Intent Router, Context Resolver, CSV Export, SQL Retrieval
- SQL stored directly in conversation turns, re-executed when needed for export

### Example Thread Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SLACK THREAD                                │
│                      (thread_id = "slack_thread_1234.567")          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Turn 1: "how many Android apps do we have?"                        │
│     └─► Bot: "We have 15 Android apps"                              │
│         └─► Saved to conversation_turns with SQL                    │
│                                                                     │
│  Turn 2: "what about iOS?"  ← FOLLOW-UP                             │
│     └─► Context Resolver reads conversation_history                 │
│     └─► Expands to: "How many iOS apps do we have?"                 │
│     └─► Bot: "We have 10 iOS apps"                                  │
│         └─► Saved to conversation_turns with SQL                    │
│                                                                     │
│  Turn 3: "export as csv"                                            │
│     └─► Reads SQL from most recent turn in conversation_turns       │
│     └─► Re-executes SQL query                                       │
│     └─► Returns CSV file                                            │
│                                                                     │
│  Turn 4: "show SQL for the first question"                          │
│     └─► Searches conversation_turns for "Android apps"              │
│     └─► Returns SQL from that turn                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Structures

### 1. Conversation History Entry (Dict Format)

> **Location:** Converted by `turns_to_history()` in `app/repositories/conversation.py`

```python
# What we pass to the LLM for context
ConversationHistoryEntry = TypedDict('ConversationHistoryEntry', {
    "user": str,               # User's message
    "bot": str,                # Bot's response (truncated to 500 chars + "...")
    "intent": str,             # "analytics_query", "follow_up", etc.
    "sql": str | None,         # The SQL query (if applicable)
    "timestamp": str | None,   # ISO format timestamp
})
```

### 2. Thread State (Managed by SlackService)

```python
# Thread state is stored in PostgreSQL via ConversationRepository
# Each turn is a row in conversation_turns table
# The repository handles:
#   - Fetching last 10 turns per thread
#   - Auto-truncating bot responses to 500 chars + "..."
#   - Cleanup of old turns (24h TTL)
```

---

## Storage Strategy

> **From architecture:** The `SlackService` handles thread state management. State is passed into the graph, not managed by LangGraph checkpointing.

### Database Schema

```sql
-- Conversation turns table
CREATE TABLE conversation_turns (
    id SERIAL PRIMARY KEY,
    thread_id VARCHAR(255) NOT NULL,
    user_message TEXT NOT NULL,
    bot_response TEXT NOT NULL,           -- Truncated to 500 chars + "..."
    intent VARCHAR(50) NOT NULL,
    sql_query TEXT,                        -- NULL for non-analytics intents
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for fetching recent turns per thread (descending for LIMIT)
CREATE INDEX idx_conversation_turns_thread_recent
ON conversation_turns (thread_id, created_at DESC);

-- Standard index on thread_id
CREATE INDEX ix_conversation_turns_thread_id
ON conversation_turns (thread_id);
```

### SQLAlchemy Model

> **Location:** `app/db/models/conversation.py`

```python
from datetime import datetime
from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.db.models.base import Base


class ConversationTurn(Base):
    """Conversation turn model for storing chat history."""

    __tablename__ = "conversation_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    bot_response: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(50), nullable=False)
    sql_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_conversation_turns_thread_recent", "thread_id", created_at.desc()),
    )
```

### Repository Layer

> **Location:** `app/repositories/conversation.py`
> **Pattern:** Session passed to methods (Pattern 1), not held in `__init__`.

```python
from datetime import UTC, datetime, timedelta
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# Maximum length for bot_response to prevent storing huge outputs
MAX_BOT_RESPONSE_LENGTH = 500


class ConversationRepository:
    """Repository for conversation turn operations.

    Follows Pattern 1: session passed to methods (not held in __init__).
    """

    async def add_turn(
        self,
        db: AsyncSession,
        thread_id: str,
        user_message: str,
        bot_response: str,
        intent: str,
        sql_query: str | None = None,
    ) -> ConversationTurn:
        """Add a new conversation turn."""
        # Truncate bot_response to prevent storing huge outputs
        truncated_response = bot_response[:MAX_BOT_RESPONSE_LENGTH]
        if len(bot_response) > MAX_BOT_RESPONSE_LENGTH:
            truncated_response += "..."

        turn = ConversationTurn(
            thread_id=thread_id,
            user_message=user_message,
            bot_response=truncated_response,
            intent=intent,
            sql_query=sql_query,
        )
        db.add(turn)
        await db.flush()  # Not commit - let caller manage transaction
        await db.refresh(turn)
        return turn

    async def get_recent_turns(
        self,
        db: AsyncSession,
        thread_id: str,
        limit: int = 10,
    ) -> list[ConversationTurn]:
        """Get recent conversation turns for a thread in chronological order."""
        # Query for most recent turns, then reverse to get chronological order
        result = await db.execute(
            select(ConversationTurn)
            .where(ConversationTurn.thread_id == thread_id)
            .order_by(ConversationTurn.created_at.desc())
            .limit(limit)
        )
        turns = list(result.scalars().all())
        turns.reverse()  # Oldest first (chronological order)
        return turns

    async def get_most_recent_sql(
        self,
        db: AsyncSession,
        thread_id: str,
    ) -> str | None:
        """Get the most recent SQL query for a thread."""
        result = await db.execute(
            select(ConversationTurn.sql_query)
            .where(ConversationTurn.thread_id == thread_id)
            .where(ConversationTurn.sql_query.isnot(None))
            .order_by(ConversationTurn.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_sql_by_keyword(
        self,
        db: AsyncSession,
        thread_id: str,
        keyword: str,
    ) -> str | None:
        """Find SQL query by keyword in user message."""
        result = await db.execute(
            select(ConversationTurn.sql_query)
            .where(ConversationTurn.thread_id == thread_id)
            .where(ConversationTurn.sql_query.isnot(None))
            .where(ConversationTurn.user_message.ilike(f"%{keyword}%"))
            .order_by(ConversationTurn.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def cleanup_old_turns(
        self,
        db: AsyncSession,
        max_age_hours: int = 24,
    ) -> int:
        """Delete turns older than max_age_hours. Returns count deleted."""
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        result = await db.execute(
            delete(ConversationTurn).where(ConversationTurn.created_at < cutoff)
        )
        await db.flush()
        return result.rowcount
```

### Helper Functions

```python
def turns_to_history(turns: list[ConversationTurn]) -> list[dict]:
    """Convert ConversationTurn models to history dict format.

    Returns list of dicts with keys: user, bot, intent, sql, timestamp (ISO string).
    """
    return [
        {
            "user": turn.user_message,
            "bot": turn.bot_response,
            "intent": turn.intent,
            "sql": turn.sql_query,
            "timestamp": turn.created_at.isoformat() if turn.created_at else None,
        }
        for turn in turns
    ]
```

---

## How Each Intent Uses History

### 1. Analytics Query (New Question)

```python
# User: "What's our revenue by country?"
# Intent: analytics_query

# History provides context but isn't strictly needed for new questions
# SQL is generated fresh and stored in the turn after response
```

### 2. Follow-up Question

```python
# Previous: "What's our revenue by country?"
# User: "What about just Q4?"
# Intent: follow_up

# Context resolver reads history to understand "what about"
resolved_query = context_resolver(
    user_query="What about just Q4?",
    history=conversation_history[-5:]  # Last 5 turns
)
# → "What's our revenue by country for Q4?"
```

### 3. CSV Export

```python
# User: "export as csv"
# Intent: export_csv

# For button clicks: query_cache is rebuilt by re-executing stored SQL
# For text commands: uses in-session query_cache or most recent SQL from DB
```

### 4. Show SQL

```python
# User: "show me the SQL"
# Intent: show_sql

# Retrieves SQL from query_cache (in-session) or conversation_turns (DB)
# Supports ordinal references: "first", "second", "last", "previous"
# Supports keyword search: "show SQL for the Android question"
```

---

## Slack Integration

> **From architecture:** Uses `AnalyticsAgentService` and `SlackService` for handling requests.

### SlackService.generate_analytics_response()

> **Location:** `app/services/slack.py`

```python
async def generate_analytics_response(
    self,
    message: str,
    user_id: str,
    channel_id: str,
    thread_ts: str | None = None,
) -> dict[str, Any]:
    """Generate analytics chatbot response."""
    from app.db.session import get_analytics_db_context, get_db_context
    from app.repositories import ConversationRepository, turns_to_history
    from app.services.agent import AnalyticsAgentService

    # Thread ID for conversation continuity
    thread_id = f"slack_thread_{thread_ts}" if thread_ts else f"slack_user_{user_id}"

    # 1. Load history from DB
    async with get_db_context() as db:
        repo = ConversationRepository()
        turns = await repo.get_recent_turns(db, thread_id, limit=10)
        conversation_history = turns_to_history(turns)

    # 2. Run analytics agent (uses separate read-only analytics DB)
    async with get_analytics_db_context() as analytics_db:
        analytics_service = AnalyticsAgentService(analytics_db=analytics_db)
        response = await analytics_service.run(
            user_query=message,
            thread_id=thread_id,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            conversation_history=conversation_history,
            query_cache={},  # Rebuilt per request through graph execution
        )

    # 3. Save new turn to DB (extract SQL from query_cache)
    async with get_db_context() as db:
        sql_query = None
        query_cache = response.query_cache or {}
        if query_cache:
            # Get the most recent cache entry by timestamp
            most_recent = max(
                query_cache.values(), key=lambda x: x.get("timestamp", datetime.min)
            )
            sql_query = most_recent.get("sql")

        await repo.add_turn(
            db,
            thread_id=thread_id,
            user_message=message,
            bot_response=response.text,
            intent=response.intent or "unknown",
            sql_query=sql_query,
        )

    return {
        "text": response.text,
        "blocks": response.slack_blocks,
        "intent": response.intent,
        "csv_content": response.csv_content,
        "csv_filename": response.csv_filename,
        "csv_title": response.csv_title,
    }
```

### Button Actions (CSV Export / Show SQL)

> **Location:** `app/services/slack.py`

```python
async def handle_button_action(
    self,
    action_id: str,
    value: str,
    user_id: str,
    channel_id: str,
    thread_ts: str,
) -> dict[str, Any]:
    """Handle button action from Slack interactive component."""
    from app.db.session import get_analytics_db_context, get_db_context
    from app.repositories import AnalyticsRepository, ConversationRepository, turns_to_history
    from app.services.agent import AnalyticsAgentService

    thread_id = f"slack_thread_{thread_ts}"

    # Create appropriate user query based on action
    if action_id == "export_csv":
        user_query = "export csv"
    elif action_id == "show_sql":
        user_query = "show sql"
    else:
        return {"text": f"Unknown action: {action_id}", "blocks": None}

    # 1. Load history from DB
    async with get_db_context() as db:
        repo = ConversationRepository()
        turns = await repo.get_recent_turns(db, thread_id, limit=10)
        conversation_history = turns_to_history(turns)

    # 2. Rebuild query_cache by re-executing SQL for turns that have SQL
    # This is needed because CSV export requires the actual results data
    query_cache: dict[str, Any] = {}
    async with get_analytics_db_context() as analytics_db:
        analytics_repo = AnalyticsRepository()
        for i, turn in enumerate(turns):
            if turn.sql_query:
                try:
                    rows, _columns = await analytics_repo.execute_query(
                        analytics_db, turn.sql_query
                    )
                    # Use index-based key to allow referencing specific queries
                    query_id = f"turn_{i}"
                    query_cache[query_id] = {
                        "sql": turn.sql_query,
                        "results": rows,
                        "timestamp": turn.created_at,
                        "natural_query": turn.user_message,
                        "assumptions": [],
                    }
                except Exception as e:
                    logger.warning(f"Failed to re-execute SQL for turn {i}: {e}")

        # 3. Run analytics agent with rebuilt cache
        analytics_service = AnalyticsAgentService(analytics_db=analytics_db)
        response = await analytics_service.run(
            user_query=user_query,
            thread_id=thread_id,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            conversation_history=conversation_history,
            query_cache=query_cache,
        )

    return {
        "text": response.text,
        "blocks": response.slack_blocks,
        "csv_content": response.csv_content,
        "csv_filename": response.csv_filename,
        "csv_title": response.csv_title,
    }
```

---

## Key Design Decisions

### 1. Why truncate bot responses in history?

```python
# ❌ Bad: Store full response
{"bot": "Here's the data:\n| country | revenue |\n| USA | $1,234,567 |..."}  # Could be 5000+ chars

# ✅ Good: Store truncated response + "..."
{"bot": "Here's the data showing revenue by country. USA leads with $1.2M..."}  # ~500 chars
```

**Reason:** LLM context window limits. History is used for understanding context, not reproducing answers.

### 2. Why store SQL directly instead of caching results?

| Approach | Pros | Cons |
|----------|------|------|
| **Store SQL (current)** | Simple, no cache management, always fresh data | Re-executes query on export |
| Cache results | Faster export, no re-query | Stale data, memory overhead, cache invalidation |

**Decision:** Store SQL directly. For most analytics queries, re-execution is fast and ensures fresh data.

### 3. Why use Pattern 1 (session passed to methods)?

```python
# ✅ Pattern 1 (used): Session passed to methods
repo = ConversationRepository()
await repo.add_turn(db, thread_id, user_message, ...)

# ❌ Pattern 2: Session in __init__
repo = ConversationRepository(db)
await repo.add_turn(thread_id, user_message, ...)
```

**Reason:** Pattern 1 is the project standard per `docs/database_skill.md`. Allows single repository instance across multiple transactions.

### 4. How much history to send to LLM?

```python
# For intent classification: Last 5-10 turns (configurable)
history_for_intent = conversation_history[-10:]

# For context resolution: Last 5 turns
history_for_context = conversation_history[-5:]

# For SQL generation: Just the resolved query (no history needed)
# For interpretation: Just the query + results (no history needed)
```

**Rule:** Only send history where it actually helps. More history = more tokens = more cost + latency.

### 5. When does history reset?

| Scenario | History Behavior |
|----------|------------------|
| New Slack thread | Fresh state (new thread_id) |
| Same thread, new day | Persisted (until 24h TTL) |
| Different channel | Fresh state (different thread_id) |
| Bot restart | Persisted in PostgreSQL ✓ |

---

## Summary

```
┌────────────────────────────────────────────────────────────┐
│                    THREAD STATE                            │
│              (Stored in PostgreSQL)                        │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  conversation_turns table (last 10 per thread)             │
│  ├── Used by: intent_router.py, context_resolver.py,       │
│  │            csv_export.py, sql_retrieval.py              │
│  ├── Contains: user query, truncated bot response, SQL     │
│  ├── Purpose: Context resolution + serve export/SQL        │
│  │            requests by re-executing stored SQL          │
│  └── TTL: 24 hours (cleanup_old_turns)                     │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### Alignment with Architecture

| Architecture Component | Conversation History Usage |
|------------------------|---------------------------|
| `models/conversation.py` | Defines `ConversationTurn` SQLAlchemy model |
| `repositories/conversation.py` | CRUD operations + `turns_to_history()` helper |
| `state.py` | Defines `ChatbotState` with `conversation_history` field |
| `nodes/intent_router.py` | Reads `conversation_history` for follow-up detection |
| `nodes/context_resolver.py` | Reads `conversation_history` for reference expansion |
| `nodes/sql_executor.py` | SQL stored via SlackService after graph completes |
| `nodes/csv_export.py` | Reads from `query_cache` (rebuilt from DB) |
| `nodes/sql_retrieval.py` | Reads from `query_cache` (rebuilt from DB) |
| `AnalyticsAgentService` | Orchestrates graph execution with history/cache |
| `SlackService` | Manages DB persistence + button action cache rebuilding |
