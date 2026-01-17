# Analytics Chatbot Architecture

This document describes the LangGraph-based analytics chatbot architecture for the Slack integration.

## Overview

The analytics chatbot converts natural language questions into SQL queries, executes them against the app_metrics database, and returns intelligently formatted responses via Slack. It uses a multi-node workflow pattern with intent routing, caching, and Block Kit formatting.

## Architecture Diagram

```
User Message → Intent Router → [Route by Intent]
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    │                               │                               │
    ▼                               ▼                               ▼
analytics_query              follow_up                    export_csv/show_sql/off_topic
    │                               │                               │
    ▼                               ▼                               ▼
SQL Generator ◄──────── Context Resolver              Cached Operations / Decline
    │                                                               │
    ▼                                                               │
SQL Validator ──(invalid)──► Retry (max 2)                          │
    │                                                               │
    ▼ (valid)                                                       │
SQL Executor + Cache                                                │
    │                                                               │
    ▼                                                               │
Result Interpreter                                                  │
    │                                                               │
    ▼                                                               │
Response Formatter ◄────────────────────────────────────────────────┘
    │
    ▼
Send to Slack
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

- CSV export: "export", "csv", "download"
- Show SQL: "show sql", "what sql", "sql query"

## SQL Pipeline

### 1. SQL Generator

Converts natural language to SQL using:
- Database schema documentation
- Few-shot examples
- JSON output format

### 2. SQL Validator

Validates generated SQL:
- Checks for dangerous keywords (DROP, DELETE, UPDATE, etc.)
- Verifies SELECT-only queries
- Parses with sqlparse for syntax validation

### 3. SQL Executor

Executes validated SQL and caches results:
- Converts database values to JSON-serializable format
- Generates 8-character query ID from SQL hash
- Maintains cache of last 10 queries per thread

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

## Slack Block Kit Formatting

Responses are formatted using Slack Block Kit:

1. **Section**: Main response text
2. **Section**: Table (for complex results)
3. **Context**: Assumptions made
4. **Actions**: Export CSV and Show SQL buttons

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
    )
```

### SlackService

Handles Slack-specific operations:
- `generate_analytics_response()`: Run chatbot for user message
- `handle_button_action()`: Process button clicks
- `upload_file()`: Upload CSV exports

## Observability

All nodes are instrumented with Logfire spans:
- `classify_intent`: Intent classification
- `resolve_context`: Context resolution
- `generate_sql`: SQL generation
- `validate_sql`: SQL validation
- `execute_and_cache`: Query execution
- `interpret_results`: Result interpretation
- `format_slack_response`: Response formatting

## Cost Optimization

| Query Type | LLM Calls |
|------------|-----------|
| New analytics question | 3 (intent + SQL + interpret) |
| Follow-up question | 4 (intent + context + SQL + interpret) |
| CSV export | 0 |
| Show SQL | 0 |
| Off-topic | 1 (intent only) |
