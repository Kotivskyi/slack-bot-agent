"""State definitions for the analytics chatbot graph.

Contains TypedDict definitions for the chatbot state that flows through the graph.
"""

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ChatbotState(TypedDict):
    """Complete state schema for the Slack Analytics Chatbot.

    This state flows through all nodes in the LangGraph workflow.
    Uses add_messages reducer for proper message history management.
    """

    # ===== Message History (LangGraph standard) =====
    messages: Annotated[list[BaseMessage], add_messages]

    # ===== Core Conversation =====
    user_query: str  # Current user message
    user_id: str  # Slack user ID (for future permissions)
    channel_id: str  # Slack channel ID
    thread_ts: str | None  # Thread timestamp for replies
    conversation_history: list[dict[str, str]]  # Previous Q&A pairs in session

    # ===== Intent Classification =====
    intent: Literal[
        "analytics_query",  # New data question
        "follow_up",  # References previous context
        "export_csv",  # Request to download data
        "show_sql",  # Request to see SQL query
        "off_topic",  # Not related to app analytics
    ]
    confidence: float  # Intent classification confidence

    # ===== Context Resolution =====
    resolved_query: str | None  # Expanded query after context resolution
    referenced_query_id: str | None  # ID of query being referenced

    # ===== SQL Pipeline =====
    generated_sql: str | None  # The SQL query generated
    sql_error: str | None  # Error message if execution failed
    retry_count: int  # Number of SQL generation retries
    query_results: list[dict[str, Any]] | None  # Raw query results
    row_count: int  # Number of rows returned
    column_names: list[str]  # Column headers

    # ===== Query Tracking =====
    current_query_id: str | None  # ID of current/most recent query (MD5 hash)

    # ===== Response Generation =====
    response_format: Literal["simple", "table", "error"]
    response_text: str  # Final formatted response
    assumptions_made: list[str]  # Assumptions noted for user
    slack_blocks: list[dict[str, Any]] | None  # Slack Block Kit formatted response
    action_id: str | None  # UUID for button action lookups
