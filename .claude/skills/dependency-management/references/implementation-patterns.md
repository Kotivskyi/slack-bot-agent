# Implementation Patterns

## 1. FastAPI Route (Entry Point)

```python
# app/api/routes/slack.py
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, get_slack_client
from app.services.agent import AnalyticsAgentService
from app.db.models import User

router = APIRouter()


@router.post("/slack/events")
async def handle_slack_event(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    slack_client: WebClient = Depends(get_slack_client),
):
    """
    Route only handles:
    - Request parsing
    - Dependency injection
    - Delegating to service
    """
    body = await request.json()

    service = AnalyticsAgentService(
        db=db,
        slack_client=slack_client,
    )

    response = await service.run(
        user_query=body["event"]["text"],
        thread_id=body["event"]["thread_ts"],
        channel_id=body["event"]["channel"],
        user_id=current_user.id,
    )

    return {"ok": True}
```

## 2. Service Layer (Bridge)

```python
# app/services/agent.py
from sqlalchemy.ext.asyncio import AsyncSession
from slack_sdk import WebClient

from app.agents.analytics_chatbot import build_graph, ChatbotState
from app.repositories.metrics import MetricsRepository
from app.repositories.query_cache import QueryCacheRepository


class AnalyticsAgentService:
    """
    Service responsibilities:
    - Create repositories from db session
    - Initialize LangGraph state
    - Configure and run the graph
    - Handle top-level errors
    """

    def __init__(self, db: AsyncSession, slack_client: WebClient):
        self.db = db
        self.slack_client = slack_client

        # Create repositories (data access layer)
        self.metrics_repo = MetricsRepository(db)
        self.cache_repo = QueryCacheRepository(db)

        # Build the graph once
        self.graph = build_graph()

    async def run(
        self,
        user_query: str,
        thread_id: str,
        channel_id: str,
        user_id: str,
    ) -> str:
        # Initialize LangGraph state (workflow data)
        initial_state: ChatbotState = {
            "user_query": user_query,
            "thread_id": thread_id,
            "channel_id": channel_id,
            "intent": None,
            "sql": None,
            "results": [],
            "assumptions": [],
            "response": "",
            "error": None,
            "retry_count": 0,
        }

        # Pass resources via config (not state)
        config = {
            "configurable": {
                "metrics_repo": self.metrics_repo,
                "cache_repo": self.cache_repo,
                "slack_client": self.slack_client,
                "user_id": user_id,
            }
        }

        try:
            final_state = await self.graph.ainvoke(initial_state, config=config)
            return final_state["response"]
        except Exception as e:
            # Top-level error handling
            return f"Sorry, something went wrong: {e}"
```

## 3. LangGraph Node (Accessing Resources)

```python
# app/agents/analytics_chatbot/nodes/sql_executor.py
from typing import Any
import logfire
from langchain_core.runnables import RunnableConfig

from app.agents.analytics_chatbot.state import ChatbotState
from app.repositories.metrics import MetricsRepository


async def execute_and_cache(
    state: ChatbotState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """
    Node responsibilities:
    - Extract resources from config
    - Execute single unit of work
    - Return state updates (not full state)
    """
    with logfire.span("execute_and_cache"):
        # Extract repository from config
        metrics_repo: MetricsRepository = config["configurable"]["metrics_repo"]

        # Execute query via repository
        try:
            results = await metrics_repo.execute_raw_sql(state["sql"])

            return {
                "results": results,
                "error": None,
            }
        except Exception as e:
            return {
                "results": [],
                "error": str(e),
            }
```

## 4. Repository (Data Access)

```python
# app/repositories/metrics.py
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class MetricsRepository:
    """
    Repository responsibilities:
    - Database operations only
    - No business logic
    - Use flush(), not commit() (let service manage transactions)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute_raw_sql(self, sql: str) -> list[dict[str, Any]]:
        """Execute validated SQL and return results as dicts."""
        result = await self.db.execute(text(sql))
        rows = result.fetchall()
        columns = result.keys()

        return [dict(zip(columns, row)) for row in rows]

    async def get_schema_info(self) -> dict[str, list[str]]:
        """Get table and column information for SQL generation."""
        # Implementation...
        pass
```

## 5. State Type Definition

```python
# app/agents/analytics_chatbot/state.py
from typing import TypedDict, Literal, Any
from datetime import datetime


class CacheEntry(TypedDict):
    sql: str
    results: list[dict[str, Any]]
    timestamp: datetime
    natural_query: str
    assumptions: list[str]


class ChatbotState(TypedDict, total=False):
    # Input (set once at start)
    user_query: str
    thread_id: str
    channel_id: str

    # Workflow data (modified by nodes)
    intent: Literal["analytics_query", "follow_up", "export_csv", "show_sql", "off_topic"] | None
    sql: str | None
    results: list[dict[str, Any]]
    assumptions: list[str]
    cache: dict[str, CacheEntry]

    # Output (built incrementally)
    response: str
    blocks: list[dict[str, Any]]

    # Error handling
    error: str | None
    retry_count: int
```
