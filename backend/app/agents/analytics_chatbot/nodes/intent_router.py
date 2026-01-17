"""Intent router node for the analytics chatbot.

Classifies user intent to route to the appropriate pipeline.
Uses keyword matching first for efficiency, then LLM for ambiguous cases.
"""

import json
import logging
from typing import Any

import logfire
from langchain_openai import ChatOpenAI

from app.agents.analytics_chatbot.prompts import INTENT_CLASSIFIER_PROMPT
from app.agents.analytics_chatbot.state import ChatbotState
from app.core.config import settings

logger = logging.getLogger(__name__)


def classify_intent(state: ChatbotState) -> dict[str, Any]:
    """Route to appropriate pipeline based on user intent.

    Uses keyword matching first for common intents (export, SQL),
    then falls back to LLM classification for ambiguous cases.

    Args:
        state: Current chatbot state with user_query.

    Returns:
        Dict with intent and confidence fields.
    """
    with logfire.span("classify_intent", user_query=state.get("user_query", "")[:100]):
        query_lower = state.get("user_query", "").lower().strip()

        # ===== Fast-path: Keyword detection (no LLM needed) =====

        # CSV export requests
        csv_keywords = ["export", "csv", "download", "save as", "get file"]
        if any(kw in query_lower for kw in csv_keywords):
            logfire.info("Intent detected via keyword", intent="export_csv")
            return {"intent": "export_csv", "confidence": 0.95}

        # SQL display requests
        sql_keywords = [
            "show sql",
            "show me the sql",
            "what sql",
            "sql query",
            "sql statement",
            "what query",
            "see the query",
        ]
        if any(kw in query_lower for kw in sql_keywords):
            logfire.info("Intent detected via keyword", intent="show_sql")
            return {"intent": "show_sql", "confidence": 0.95}

        # ===== LLM classification for ambiguous cases =====

        # Format conversation history
        history = state.get("conversation_history", [])
        history_text = (
            "\n".join(
                [f"User: {turn['user']}\nBot: {turn['bot'][:200]}..." for turn in history[-5:]]
            )
            or "No previous conversation."
        )

        with logfire.span("llm_intent_classification"):
            llm = ChatOpenAI(
                model=settings.AI_MODEL,
                temperature=0,
                api_key=settings.OPENAI_API_KEY,
            )
            chain = INTENT_CLASSIFIER_PROMPT | llm
            response = chain.invoke({"query": state.get("user_query", ""), "history": history_text})

        # Parse response
        try:
            result = json.loads(response.content)
            logfire.info(
                "Intent classified",
                intent=result.get("intent"),
                confidence=result.get("confidence", 0.8),
            )
            return {
                "intent": result.get("intent", "analytics_query"),
                "confidence": result.get("confidence", 0.8),
            }
        except json.JSONDecodeError:
            logfire.warn("Failed to parse intent response, defaulting to analytics_query")
            return {"intent": "analytics_query", "confidence": 0.5}
