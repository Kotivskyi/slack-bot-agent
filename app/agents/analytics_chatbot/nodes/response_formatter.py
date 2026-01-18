"""Response formatter node for the analytics chatbot.

Formats the final response for Slack using Block Kit.
No LLM calls - pure formatting logic.
"""

import logging
from typing import Any

import logfire

from app.agents.analytics_chatbot.state import ChatbotState

logger = logging.getLogger(__name__)


def format_table_for_slack(columns: list[str], rows: list[dict], max_rows: int = 20) -> str:
    """Format results as a Slack-friendly table using code blocks.

    Args:
        columns: Column names for headers.
        rows: List of row dicts.
        max_rows: Maximum number of rows to display.

    Returns:
        Formatted table string wrapped in code block.
    """
    if not rows:
        return "_No data found._"

    # Calculate column widths (max 30 chars per column to prevent overflow)
    widths = {col: min(len(col), 30) for col in columns}
    for row in rows[:max_rows]:
        for col in columns:
            val = str(row.get(col, ""))
            widths[col] = min(max(widths[col], len(val)), 30)

    # Build table
    header = " | ".join(col.ljust(widths[col])[: widths[col]] for col in columns)
    separator = "-+-".join("-" * widths[col] for col in columns)

    lines = [header, separator]
    for row in rows[:max_rows]:
        line = " | ".join(
            str(row.get(col, "")).ljust(widths[col])[: widths[col]] for col in columns
        )
        lines.append(line)

    if len(rows) > max_rows:
        lines.append(f"... and {len(rows) - max_rows} more rows")

    return "```\n" + "\n".join(lines) + "\n```"


def format_slack_response(state: ChatbotState) -> dict[str, Any]:
    """Format final response for Slack using Block Kit.

    Builds a response with:
    - Main response text
    - Table (if complex response)
    - Assumptions (if any)
    - Action buttons (Export CSV, Show SQL)

    Args:
        state: Current chatbot state with response_text, response_format, etc.

    Returns:
        Dict with slack_blocks field.
    """
    with logfire.span("format_slack_response", format=state.get("response_format")):
        blocks: list[dict[str, Any]] = []

        # Main response text
        response_text = state.get("response_text", "")
        if response_text:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": response_text,
                    },
                }
            )

        # Add table if complex response
        if state.get("response_format") == "table" and state.get("query_results"):
            table_text = format_table_for_slack(
                state.get("column_names", []),
                state.get("query_results", []),
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": table_text,
                    },
                }
            )

        # Add assumptions if any
        assumptions = state.get("assumptions_made", [])
        if assumptions:
            assumptions_text = "_Assumptions: " + "; ".join(assumptions) + "_"
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": assumptions_text,
                        }
                    ],
                }
            )

        # Add action buttons (only if we have results)
        query_id = state.get("current_query_id", "")
        if query_id and state.get("query_results"):
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Export CSV", "emoji": True},
                            "action_id": "export_csv",
                            "value": query_id,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Show SQL", "emoji": True},
                            "action_id": "show_sql",
                            "value": query_id,
                        },
                    ],
                }
            )

        logfire.info("Response formatted", block_count=len(blocks))

        # Update conversation history for checkpointing
        user_query = state.get("user_query", "")
        current_history = list(state.get("conversation_history", []))
        current_history.append(
            {
                "user": user_query,
                "bot": response_text[:500] if response_text else "",
            }
        )

        return {"slack_blocks": blocks, "conversation_history": current_history}
