"""Conditional routing logic for the analytics chatbot graph.

Contains routing functions that determine which node to execute next
based on the current state.
"""

from typing import Literal

from app.agents.analytics_chatbot.state import ChatbotState


def route_by_intent(
    state: ChatbotState,
) -> Literal["sql_generator", "context_resolver", "csv_export", "sql_retrieval", "decline"]:
    """Main intent router - determines which pipeline to use.

    Args:
        state: Current chatbot state with intent classification.

    Returns:
        Name of the next node to execute.
    """
    intent = state.get("intent", "off_topic")

    routing = {
        "analytics_query": "sql_generator",
        "follow_up": "context_resolver",
        "export_csv": "csv_export",
        "show_sql": "sql_retrieval",
        "off_topic": "decline",
    }

    return routing.get(intent, "decline")


def route_after_validation(
    state: ChatbotState,
) -> Literal["executor", "sql_generator", "error_response"]:
    """Route based on SQL validation result.

    Args:
        state: Current chatbot state with SQL validation results.

    Returns:
        Name of the next node to execute.
    """
    if state.get("sql_valid", False):
        return "executor"

    # Retry logic with error context
    retry_count = state.get("retry_count", 0)

    if retry_count < 2:  # Allow 2 retries
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
