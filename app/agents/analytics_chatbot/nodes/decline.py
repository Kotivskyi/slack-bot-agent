"""Polite decline node for the analytics chatbot.

Handles off-topic questions gracefully.
No LLM calls needed.
"""

import logging
from typing import Any

import logfire

from app.agents.analytics_chatbot.state import ChatbotState

logger = logging.getLogger(__name__)

DECLINE_MESSAGE = """I'm focused on helping with app portfolio analytics!

I can help you with questions about:
• App installs and downloads
• Revenue (in-app purchases & ads)
• User acquisition costs
• Performance by country or platform
• Trends and comparisons over time

What would you like to know about our apps?"""


def polite_decline(state: ChatbotState) -> dict[str, Any]:
    """Politely decline off-topic questions.

    Returns a helpful message explaining what the chatbot can do.
    No LLM calls needed.

    Args:
        state: Current chatbot state with user_query.

    Returns:
        Dict with response_text and slack_blocks fields.
    """
    logfire.info("Off-topic query declined", query=state.get("user_query", "")[:100])

    return {
        "response_text": DECLINE_MESSAGE,
        "slack_blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": DECLINE_MESSAGE,
                },
            }
        ],
    }
