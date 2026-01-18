"""SQL retrieval node for the analytics chatbot.

Retrieves SQL from state (pre-populated by SlackService for button clicks).
No LLM calls - uses generated_sql from state.
"""

import logging
from typing import Any

import logfire

from app.agents.analytics_chatbot.state import ChatbotState

logger = logging.getLogger(__name__)


def _update_history(state: ChatbotState, response_text: str) -> list[dict[str, str]]:
    """Helper to update conversation history."""
    current_history = list(state.get("conversation_history", []))
    current_history.append(
        {
            "user": state.get("user_query", ""),
            "bot": response_text[:500],
        }
    )
    return current_history


def retrieve_sql(state: ChatbotState) -> dict[str, Any]:
    """Retrieve SQL statement from state.

    NO LLM CALL - uses generated_sql from state.
    For button clicks, SlackService pre-populates generated_sql from DB.

    Args:
        state: Current chatbot state with generated_sql.

    Returns:
        Dict with response_text and slack_blocks fields.
    """
    with logfire.span("retrieve_sql"):
        sql = state.get("generated_sql")

        if not sql:
            logfire.warn("SQL retrieval requested but no SQL available")
            response_text = "No SQL queries in history. Please ask a question first!"
            return {
                "response_text": response_text,
                "conversation_history": _update_history(state, response_text),
                "slack_blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": response_text,
                        },
                    }
                ],
            }

        # Get the original query for context
        resolved_query = state.get("resolved_query") or state.get("user_query", "")
        natural_query = resolved_query[:50] if resolved_query else "query"

        logfire.info("SQL retrieval complete", sql_length=len(sql))

        response_text = f'*SQL Query*\n_For: "{natural_query}..."_'
        # Format as Slack code snippet
        return {
            "response_text": response_text,
            "conversation_history": _update_history(state, response_text),
            "slack_blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": response_text,
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"```sql\n{sql}\n```",
                    },
                },
            ],
        }
