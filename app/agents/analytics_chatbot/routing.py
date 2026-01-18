"""Conditional routing logic for the analytics chatbot graph.

Contains routing functions that determine which node to execute next
based on the current state.
"""

from typing import Literal

from app.agents.analytics_chatbot.state import ChatbotState


def route_by_intent(
    state: ChatbotState,
) -> Literal["context_resolver", "csv_export", "sql_retrieval", "decline"]:
    """Main intent router - determines which pipeline to use.

    Args:
        state: Current chatbot state with intent classification.

    Returns:
        Name of the next node to execute.
    """
    intent = state.get("intent", "off_topic")

    routing = {
        "analytics_query": "context_resolver",  # Unified path through context resolver
        "follow_up": "context_resolver",
        "export_csv": "csv_export",
        "show_sql": "sql_retrieval",
        "off_topic": "decline",
    }

    return routing.get(intent, "decline")


def route_after_execution(
    state: ChatbotState,
) -> Literal["interpreter", "sql_generator", "error_response"]:
    """Route based on SQL execution result.

    Args:
        state: Current chatbot state with SQL execution results.

    Returns:
        Name of the next node to execute.
    """
    sql_error = state.get("sql_error")

    if not sql_error:
        return "interpreter"  # Success

    # Retry logic with error context
    retry_count = state.get("retry_count", 0)

    if retry_count < 3:  # Allow 3 retries
        return "sql_generator"

    return "error_response"


def route_after_interpretation(state: ChatbotState) -> Literal["format_response"]:
    """After interpretation, always format response.

    Args:
        state: Current chatbot state.

    Returns:
        Always returns "format_response".
    """
    return "format_response"
