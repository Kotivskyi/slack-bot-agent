"""LangGraph workflow definition for the analytics chatbot.

Defines the complete workflow graph with nodes and edges for:
- Intent classification
- Context resolution for follow-ups
- SQL generation and execution with retry
- Response formatting
- Button operations (CSV export, SQL retrieval)
"""

import logging
from typing import TYPE_CHECKING, Any

import logfire
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.analytics_chatbot.nodes import (
    classify_intent,
    export_csv,
    format_slack_response,
    generate_sql,
    handle_error,
    interpret_results,
    polite_decline,
    resolve_context,
    retrieve_sql,
)
from app.agents.analytics_chatbot.nodes.sql_executor import execute_sql
from app.agents.analytics_chatbot.routing import route_after_execution, route_by_intent
from app.agents.analytics_chatbot.state import ChatbotState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.repositories import AnalyticsRepository

logger = logging.getLogger(__name__)


def create_executor_node(db: "AsyncSession", repository: "AnalyticsRepository"):
    """Create executor node with db session and repository bound.

    Args:
        db: Database session for query execution.
        repository: Analytics repository for query execution.

    Returns:
        Async function that executes SQL.
    """

    async def executor_node(state: ChatbotState) -> dict[str, Any]:
        return await execute_sql(state, db, repository)

    return executor_node


def create_analytics_chatbot(
    db: "AsyncSession | None" = None,
    repository: "AnalyticsRepository | None" = None,
) -> StateGraph:
    """Create the complete LangGraph workflow for the Slack analytics chatbot.

    Args:
        db: Optional database session for SQL execution.
        repository: Optional analytics repository for SQL execution. If both
            db and repository are provided, SQL execution is enabled.
            If either is None, a placeholder is used.

    Returns:
        Uncompiled StateGraph instance.
    """
    with logfire.span("create_analytics_chatbot"):
        # Initialize graph with state schema
        workflow = StateGraph(ChatbotState)

        # ===== Add all nodes =====

        # Entry & routing
        workflow.add_node("intent_router", classify_intent)

        # Context management
        workflow.add_node("context_resolver", resolve_context)

        # SQL pipeline
        workflow.add_node("sql_generator", generate_sql)

        # Executor node - needs both db and repository
        if db is not None and repository is not None:
            workflow.add_node("executor", create_executor_node(db, repository))
        else:
            # Placeholder that will be replaced at invoke time
            async def placeholder_executor(state: ChatbotState) -> dict[str, Any]:
                logfire.error("Executor called without repository")
                return {
                    "query_results": None,
                    "sql_error": "Analytics repository not configured",
                    "row_count": 0,
                    "column_names": [],
                }

            workflow.add_node("executor", placeholder_executor)

        workflow.add_node("interpreter", interpret_results)
        workflow.add_node("format_response", format_slack_response)

        # Button operations (no LLM)
        workflow.add_node("csv_export", export_csv)
        workflow.add_node("sql_retrieval", retrieve_sql)

        # Error & decline handling
        workflow.add_node("decline", polite_decline)
        workflow.add_node("error_response", handle_error)

        # ===== Set entry point =====
        workflow.set_entry_point("intent_router")

        # ===== Define edges =====

        # Intent routing (conditional)
        # Both analytics_query and follow_up route to context_resolver first
        workflow.add_conditional_edges(
            "intent_router",
            route_by_intent,
            {
                "context_resolver": "context_resolver",
                "csv_export": "csv_export",
                "sql_retrieval": "sql_retrieval",
                "decline": "decline",
            },
        )

        # Context resolver leads to SQL generator
        workflow.add_edge("context_resolver", "sql_generator")

        # SQL pipeline: generator -> executor -> conditional routing
        workflow.add_edge("sql_generator", "executor")

        # Route after execution: success -> interpreter, error -> retry or error_response
        workflow.add_conditional_edges(
            "executor",
            route_after_execution,
            {
                "interpreter": "interpreter",
                "sql_generator": "sql_generator",  # Retry
                "error_response": "error_response",
            },
        )

        workflow.add_edge("interpreter", "format_response")

        # ===== Terminal edges =====
        workflow.add_edge("format_response", END)
        workflow.add_edge("csv_export", END)
        workflow.add_edge("sql_retrieval", END)
        workflow.add_edge("decline", END)
        workflow.add_edge("error_response", END)

        logfire.info("Analytics chatbot graph created")
        return workflow


def compile_analytics_chatbot(
    db: "AsyncSession | None" = None,
    repository: "AnalyticsRepository | None" = None,
) -> CompiledStateGraph:
    """Compile the analytics chatbot graph.

    Args:
        db: Optional database session for SQL execution.
        repository: Optional analytics repository for SQL execution.

    Returns:
        Compiled StateGraph ready for invocation.
    """
    with logfire.span("compile_analytics_chatbot"):
        workflow = create_analytics_chatbot(db, repository)
        app = workflow.compile()

        logfire.info("Analytics chatbot compiled")
        return app


class AnalyticsChatbot:
    """High-level wrapper for the analytics chatbot.

    Provides a cleaner interface for running the chatbot with proper
    repository injection and state management.
    """

    def __init__(
        self,
        db: "AsyncSession",
        repository: "AnalyticsRepository",
    ):
        """Initialize the chatbot.

        Args:
            db: Database session for SQL execution.
            repository: Analytics repository for SQL execution.
        """
        self._db = db
        self._repository = repository
        self._graph: CompiledStateGraph | None = None

    @property
    def graph(self) -> CompiledStateGraph:
        """Lazy-load the compiled graph."""
        if self._graph is None:
            self._graph = compile_analytics_chatbot(
                db=self._db,
                repository=self._repository,
            )
        return self._graph

    async def run(
        self,
        user_query: str,
        thread_id: str,
        *,
        user_id: str = "",
        channel_id: str = "",
        thread_ts: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Run the chatbot for a user query.

        Args:
            user_query: The user's question or command.
            thread_id: Unique identifier for the conversation thread.
            user_id: Slack user ID.
            channel_id: Slack channel ID.
            thread_ts: Slack thread timestamp.
            conversation_history: Previous Q&A pairs in session.

        Returns:
            Final state dict with response_text, slack_blocks, etc.
        """
        with logfire.span(
            "analytics_chatbot_run",
            thread_id=thread_id,
            user_id=user_id,
            query=user_query[:100],
        ):
            # Prepare initial state
            initial_state: dict[str, Any] = {
                "user_query": user_query,
                "user_id": user_id,
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "conversation_history": conversation_history or [],
                "messages": [],
                "retry_count": 0,
            }

            # Run the graph
            config = {"configurable": {"thread_id": thread_id}}
            result = await self.graph.ainvoke(initial_state, config)

            logfire.info(
                "Chatbot run complete",
                intent=result.get("intent"),
                response_format=result.get("response_format"),
            )

            return result
