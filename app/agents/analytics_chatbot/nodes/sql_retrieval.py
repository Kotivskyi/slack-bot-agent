"""SQL retrieval node for the analytics chatbot.

Retrieves SQL from cache without regenerating.
No LLM calls - retrieves from cache for cost efficiency.
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
    """Retrieve SQL statement from cache.

    NO LLM CALL - retrieves from cache for cost efficiency.

    Args:
        state: Current chatbot state with query_cache and user_query.

    Returns:
        Dict with response_text and slack_blocks fields.
    """
    with logfire.span("retrieve_sql"):
        cache = state.get("query_cache", {})

        if not cache:
            logfire.warn("SQL retrieval requested but no cache available")
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

        # Check for referenced query ID first (from button click)
        query_id = state.get("referenced_query_id")
        target_entry = None

        if query_id and query_id in cache:
            target_entry = cache[query_id]
            logfire.info("SQL retrieved by query_id", query_id=query_id)
        else:
            # Parse user request to find specific query
            query_lower = state.get("user_query", "").lower()

            # Look for specific references
            # Check for numbered references ("first query", "second query")
            ordinals = {"first": 0, "second": 1, "third": 2, "last": -1, "previous": -1}
            for word, idx in ordinals.items():
                if word in query_lower:
                    sorted_entries = sorted(cache.values(), key=lambda x: x["timestamp"])
                    if abs(idx) <= len(sorted_entries):
                        target_entry = sorted_entries[idx]
                        logfire.info("SQL retrieved by ordinal reference", ordinal=word)
                        break

            # Check for keyword matches in natural queries
            if not target_entry:
                for entry in cache.values():
                    natural = entry["natural_query"].lower()
                    if any(word in query_lower for word in natural.split() if len(word) > 3):
                        target_entry = entry
                        logfire.info("SQL retrieved by keyword match")
                        break

            # Default to most recent
            if not target_entry:
                target_entry = max(cache.values(), key=lambda x: x["timestamp"])
                logfire.info("SQL retrieved - most recent query")

        sql = target_entry["sql"]
        natural_query = target_entry["natural_query"][:50]

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
