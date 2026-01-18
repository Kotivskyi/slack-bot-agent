"""Error handler node for the analytics chatbot.

Handles errors that occur during SQL generation or execution.
No LLM calls needed.
"""

import logging
from typing import Any

import logfire

from app.agents.analytics_chatbot.state import ChatbotState

logger = logging.getLogger(__name__)


def handle_error(state: ChatbotState) -> dict[str, Any]:
    """Handle errors from SQL generation or execution.

    Creates a user-friendly error message based on the error type.
    No LLM calls needed.

    Args:
        state: Current chatbot state with sql_error.

    Returns:
        Dict with response_text, response_format, and slack_blocks fields.
    """
    sql_error = state.get("sql_error", "An unknown error occurred")
    user_query = state.get("user_query", "")

    logfire.error(
        "Error response generated",
        error=sql_error,
        query=user_query[:100],
        retry_count=state.get("retry_count", 0),
    )

    # Create user-friendly error message
    if "write operation" in sql_error.lower():
        friendly_message = "I can only run read-only queries. I cannot modify any data."
    elif "execution failed" in sql_error.lower():
        friendly_message = (
            "I had trouble running the query. The data might not exist or "
            "the question might need to be rephrased."
        )
    elif "parse" in sql_error.lower():
        friendly_message = (
            "I had trouble understanding how to query for that information. "
            "Could you try rephrasing your question?"
        )
    else:
        friendly_message = (
            f"I encountered an issue while processing your request. Technical details: {sql_error}"
        )

    error_response = (
        f"Sorry, I couldn't answer your question.\n\n{friendly_message}\n\n"
        f'_Original question: "{user_query[:100]}..."_'
        if len(user_query) > 100
        else f"Sorry, I couldn't answer your question.\n\n{friendly_message}\n\n"
        f'_Original question: "{user_query}"_'
    )

    # Update conversation history for checkpointing
    current_history = list(state.get("conversation_history", []))
    current_history.append(
        {
            "user": user_query,
            "bot": error_response[:500],
        }
    )

    return {
        "response_text": error_response,
        "response_format": "error",
        "conversation_history": current_history,
        "slack_blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": error_response,
                },
            }
        ],
    }
