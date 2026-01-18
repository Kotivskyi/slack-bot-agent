# Analytics Chatbot Architecture

This document describes the LangGraph-based analytics chatbot architecture for the Slack integration.

## Overview

The analytics chatbot converts natural language questions into SQL queries, executes them against the app_metrics database, and returns intelligently formatted responses via Slack. It uses a multi-node workflow pattern with intent routing, caching, conversation history persistence, and Block Kit formatting.

## Architecture Diagram

```
User Message → Intent Router → [Route by Intent]
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    │                               │                               │
    ▼                               ▼                               ▼
analytics_query / follow_up   export_csv/show_sql              off_topic
    │                               │                               │
    ▼                               ▼                               ▼
Context Resolver            Cached Operations                   Decline
    │                               │                               │
    ▼                               │                               │
SQL Generator                       │                               │
    │                               │                               │
    ▼                               │                               │
SQL Validator ──(retry)──► SQL Generator                            │
    │                               │                               │
    │──(max retries)──► Error Handler ─────────────────────────────┤
    │                               │                               │
    ▼ (valid)                       │                               │
SQL Executor + Cache                │                               │
    │                               │                               │
    ▼                               │                               │
Result Interpreter                  │                               │
    │                               │                               │
    ▼                               │                               │
Response Formatter ◄────────────────┴───────────────────────────────┘
    │
    ▼
Save to Conversation History → Send to Slack
```

## Package Structure

```
app/agents/analytics_chatbot/
├── __init__.py                 # Public exports
├── graph.py                    # LangGraph workflow definition
├── state.py                    # ChatbotState and CacheEntry types
├── prompts.py                  # All LLM prompts
├── routing.py                  # Conditional routing functions
└── nodes/                      # Node implementations
    ├── __init__.py
    ├── intent_router.py        # classify_intent()
    ├── context_resolver.py     # resolve_context()
    ├── sql_generator.py        # generate_sql()
    ├── sql_validator.py        # validate_sql()
    ├── sql_executor.py         # execute_and_cache()
    ├── result_interpreter.py   # interpret_results()
    ├── response_formatter.py   # format_slack_response()
    ├── csv_export.py           # export_csv()
    ├── sql_retrieval.py        # retrieve_sql()
    ├── decline.py              # polite_decline()
    └── error_handler.py        # handle_error()
```

## State Management

The chatbot uses `ChatbotState` (TypedDict) to track data through the workflow:

```python
class ChatbotState(TypedDict):
    # Message tracking
    messages: Annotated[list[BaseMessage], add_messages]

    # Core conversation
    user_query: str
    user_id: str
    channel_id: str
    thread_ts: str | None
    conversation_history: list[dict[str, str]]

    # Intent classification
    intent: Literal["analytics_query", "follow_up", "export_csv", "show_sql", "off_topic"]
    confidence: float

    # Context resolution (for follow-ups)
    resolved_query: str
    referenced_query_id: str | None

    # SQL pipeline
    generated_sql: str
    sql_valid: bool
    sql_error: str | None
    retry_count: int
    query_results: list[dict[str, Any]]
    row_count: int
    column_names: list[str]

    # Caching
    query_cache: dict[str, CacheEntry]
    current_query_id: str

    # Response
    response_format: Literal["simple", "table", "error"]
    response_text: str
    assumptions_made: list[str]
    slack_blocks: list[dict[str, Any]]

    # CSV export
    csv_content: str | None
    csv_filename: str | None
    csv_title: str | None
```

## Intent Classification

The chatbot classifies user intents into five categories:

| Intent | Description | LLM Required |
|--------|-------------|--------------|
| `analytics_query` | New data question | Yes |
| `follow_up` | References previous context | Yes |
| `export_csv` | Download data as CSV | No (keyword) |
| `show_sql` | View the SQL query | No (keyword) |
| `off_topic` | Not related to analytics | Yes |

### Keyword Fast-Path

For common intents, keyword matching is used to avoid LLM calls:

- **CSV export**: "export", "csv", "download", "save as", "get file"
- **Show SQL**: "show sql", "show me the sql", "what sql", "sql query", "sql statement", "what query", "see the query"

## SQL Pipeline

### 1. SQL Generator

Converts natural language to SQL using:
- Database schema documentation (`DB_SCHEMA` constant)
- Few-shot examples (`FEW_SHOT_EXAMPLES`)
- JSON output format with fallback regex extraction

On retry (after validation failure), uses `SQL_RETRY_PROMPT` with the previous SQL and error message.

### 2. SQL Validator

Validates generated SQL (no LLM required):
- Checks for dangerous keywords: DROP, DELETE, UPDATE, INSERT, TRUNCATE, ALTER, CREATE, GRANT, REVOKE, EXEC, EXECUTE
- Verifies SELECT-only (or WITH) queries
- Parses with sqlparse for syntax validation

### 3. SQL Executor

Executes validated SQL and caches results:
- Executes via `AnalyticsRepository.execute_raw_query()`
- Converts database values to JSON-serializable format
- Generates 8-character query ID from MD5 hash of SQL
- Maintains cache of last 10 queries per session

### 4. Error Handler

Handles SQL generation failures after max retries:
- Generates user-friendly messages based on error type
- Suggests rephrasing for parse errors
- No LLM required

## Caching Mechanism

Query results are cached per conversation thread to enable:

1. **Cost Optimization**: CSV export and SQL retrieval don't require LLM calls
2. **Session Continuity**: Previous results accessible via buttons
3. **Follow-up Questions**: Context available for reference resolution

Cache structure:
```python
class CacheEntry(TypedDict):
    sql: str                        # The SQL query
    results: list[dict[str, Any]]   # Query results
    timestamp: datetime             # When executed
    natural_query: str              # Original question
    assumptions: list[str]          # Assumptions made
```

## Conversation History Persistence

Conversation turns are persisted to the database for context across sessions.

### Database Model

```python
# app/db/models/conversation.py
class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[int]                 # Primary key
    thread_id: Mapped[str]          # Slack thread ID (indexed)
    user_message: Mapped[str]       # User's question
    bot_response: Mapped[str]       # Bot's response (truncated to 500 chars)
    intent: Mapped[str]             # Classified intent
    sql_query: Mapped[str | None]   # SQL if analytics query
    created_at: Mapped[datetime]    # Timestamp (indexed with thread_id)
```

### Repository

```python
# app/repositories/conversation.py
class ConversationRepository:
    async def add_turn(db, thread_id, user_message, bot_response, intent, sql_query)
    async def get_recent_turns(db, thread_id, limit=10) -> list[ConversationTurn]
    async def get_most_recent_sql(db, thread_id) -> str | None
    async def find_sql_by_keyword(db, thread_id, keyword) -> str | None
    async def cleanup_old_turns(db, max_age_hours=24)

def turns_to_history(turns: list[ConversationTurn]) -> list[dict]
```

### Usage in Workflow

1. **Loading**: SlackService loads last 5 turns before running chatbot
2. **Context Resolution**: `resolve_context` node uses history for follow-up queries
3. **Saving**: Each response formatter node appends to `conversation_history`
4. **Persistence**: SlackService saves the turn after chatbot completes

## Slack Block Kit Formatting

Responses are formatted using Slack Block Kit:

1. **Section**: Main response text
2. **Section**: Table (for complex results, using monospace formatting)
3. **Context**: Assumptions made (if any)
4. **Actions**: Export CSV and Show SQL buttons (if results exist)

## Button Action Handling

When users click Export CSV or Show SQL buttons:

1. **SlackService.handle_button_action()** receives the action
2. Query ID is extracted from button value
3. For cached queries: Results retrieved from in-memory cache
4. For expired cache: SQL is retrieved from `conversation_turns` table and re-executed
5. Response is generated without LLM calls

## Routing Logic

### route_by_intent()
Maps intents to their target nodes:
- `analytics_query` → `context_resolver` (unified path)
- `follow_up` → `context_resolver` (unified path)
- `export_csv` → `csv_export`
- `show_sql` → `sql_retrieval`
- `off_topic` → `decline`

### route_after_validation()
Routes after SQL validation:
- `sql_valid=True` → `executor`
- `sql_valid=False` and `retry_count < 2` → `sql_generator` (retry)
- `sql_valid=False` and `retry_count >= 2` → `error_response`

## Adding New Intents

1. Add intent to `ChatbotState.intent` literal type in `state.py`
2. Update `INTENT_CLASSIFIER_PROMPT` in `prompts.py`
3. Create node implementation in `nodes/`
4. Add routing in `routing.py` (`route_by_intent`)
5. Add node and edges in `graph.py`

## Adding New Nodes

1. Create node file in `nodes/`:
```python
def my_node(state: ChatbotState) -> dict[str, Any]:
    with logfire.span("my_node"):
        # Implementation
        return {"field": "value"}
```

2. Export from `nodes/__init__.py`
3. Add to graph in `graph.py`:
```python
workflow.add_node("my_node", my_node)
workflow.add_edge("previous_node", "my_node")
```

## Service Integration

### AnalyticsAgentService

High-level service for running the chatbot:

```python
from app.services.agent import AnalyticsAgentService

async with get_db_context() as db:
    service = AnalyticsAgentService(db)
    response = await service.run(
        user_query="How many apps do we have?",
        thread_id="thread-123",
        user_id="U12345",
        channel_id="C12345",
        thread_ts="1234567890.123456",
        conversation_history=[...],  # Previous turns
        query_cache={...},           # Cached queries
    )
    # response.text - Response text
    # response.slack_blocks - Slack Block Kit blocks
    # response.intent - Classified intent
    # response.query_cache - Updated cache
    # response.conversation_history - Updated history
    # response.csv_content - CSV data (if export)
    # response.csv_filename - CSV filename (if export)
```

### SlackService

Handles Slack-specific operations with conversation persistence:

```python
# Full flow for user messages
async def generate_analytics_response(channel_id, thread_ts, user_id, text):
    # 1. Load conversation history from DB
    turns = await ConversationRepository.get_recent_turns(db, thread_ts, limit=5)
    history = turns_to_history(turns)

    # 2. Run analytics chatbot
    response = await analytics_service.run(
        user_query=text,
        thread_id=thread_ts,
        conversation_history=history,
        ...
    )

    # 3. Save turn to DB
    await ConversationRepository.add_turn(
        db, thread_ts, text, response.text,
        response.intent, response.generated_sql
    )

    return response

# Button click handling
async def handle_button_action(action_id, value, thread_ts):
    # Rebuilds query_cache from stored SQL if needed
    # Returns CSV content or SQL display
```

Additional methods:
- `upload_file()`: Upload CSV exports to Slack

## Observability

All nodes are instrumented with Logfire spans:
- `classify_intent`: Intent classification
- `resolve_context`: Context resolution
- `generate_sql`: SQL generation
- `validate_sql`: SQL validation
- `execute_and_cache`: Query execution
- `interpret_results`: Result interpretation
- `format_slack_response`: Response formatting
- `export_csv`: CSV export
- `retrieve_sql`: SQL retrieval
- `polite_decline`: Off-topic handling
- `handle_error`: Error response generation

## Cost Optimization

| Query Type | LLM Calls |
|------------|-----------|
| New analytics question | 4 (intent + context + SQL + interpret) |
| Follow-up question | 4 (intent + context + SQL + interpret) |
| CSV export | 0 |
| Show SQL | 0 |
| Off-topic | 1 (intent only) |
| Failed SQL (after retries) | 3-4 (intent + context + SQL attempts) |

## LLM Prompts

Five prompts are defined in `prompts.py`:

| Prompt | Purpose |
|--------|---------|
| `INTENT_CLASSIFIER_PROMPT` | Classifies user intent (5 categories) |
| `CONTEXT_RESOLVER_PROMPT` | Resolves follow-up references using history |
| `SQL_GENERATOR_PROMPT` | Generates SQL from natural language |
| `SQL_RETRY_PROMPT` | Fixes invalid SQL based on error message |
| `INTERPRETER_PROMPT` | Generates natural language response from results |

Supporting constants:
- `DB_SCHEMA`: Full schema documentation for app_metrics table
- `FEW_SHOT_EXAMPLES`: Example Q&A pairs with SQL
