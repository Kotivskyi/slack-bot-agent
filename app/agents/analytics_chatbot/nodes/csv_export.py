"""CSV export node for the analytics chatbot.

Exports cached results as CSV without regenerating queries.
No LLM calls - retrieves from cache for cost efficiency.
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
    """Export cached results as CSV.

    NO LLM CALL - retrieves from cache for cost efficiency.
    Returns the CSV content as part of the response for the service
    layer to handle the actual Slack file upload.

    Args:
        state: Current chatbot state with query_cache.

    Returns:
        Dict with response_text, slack_blocks, and csv_content fields.
    """
    with logfire.span("export_csv"):
        cache = state.get("query_cache", {})

        if not cache:
            logfire.warn("CSV export requested but no cache available")
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

        # Get requested query or most recent
        query_id = state.get("referenced_query_id") or state.get("current_query_id")

        if query_id and query_id in cache:
            entry = cache[query_id]
            logfire.info("Exporting specific query", query_id=query_id)
        else:
            # Get most recent entry
            entry = max(cache.values(), key=lambda x: x["timestamp"])
            logfire.info("Exporting most recent query")

        results = entry["results"]

        if not results:
            logfire.warn("No data to export")
            response_text = "The query returned no data to export."
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
        natural_query = entry["natural_query"][:50]

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
