"""CSV export node for the analytics chatbot.

Exports query results as CSV.
No LLM calls - uses results from state (pre-populated by SlackService for button clicks).
"""

import csv
import io
import logging
from datetime import datetime
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


def export_csv(state: ChatbotState) -> dict[str, Any]:
    """Export query results as CSV.

    NO LLM CALL - uses results from state.
    For button clicks, SlackService pre-populates query_results from DB.
    Returns the CSV content as part of the response for the service
    layer to handle the actual Slack file upload.

    Args:
        state: Current chatbot state with query_results.

    Returns:
        Dict with response_text, slack_blocks, and csv_content fields.
    """
    with logfire.span("export_csv"):
        results = state.get("query_results")

        if not results:
            logfire.warn("CSV export requested but no results available")
            response_text = "No recent query results to export. Please ask a question first!"
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
                "csv_content": None,
                "csv_filename": None,
            }

        # Generate CSV content
        csv_buffer = io.StringIO()
        writer = csv.DictWriter(csv_buffer, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
        csv_content = csv_buffer.getvalue()

        filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        # Get the original query for context
        resolved_query = state.get("resolved_query") or state.get("user_query", "")
        natural_query = resolved_query[:50] if resolved_query else "query"

        logfire.info("CSV generated", row_count=len(results), filename=filename)

        response_text = (
            f'*CSV Export Complete*\n_{len(results)} rows exported from:_ "{natural_query}..."'
        )
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
            "csv_content": csv_content,
            "csv_filename": filename,
            "csv_title": f"Export: {natural_query}...",
        }
