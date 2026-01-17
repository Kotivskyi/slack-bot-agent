"""Context resolver node for the analytics chatbot.

Expands follow-up questions using conversation history to create standalone queries.
"""

import logging
from typing import Any

import logfire
from langchain_openai import ChatOpenAI

from app.agents.analytics_chatbot.prompts import CONTEXT_RESOLVER_PROMPT
from app.agents.analytics_chatbot.state import ChatbotState
from app.core.config import settings

logger = logging.getLogger(__name__)


def resolve_context(state: ChatbotState) -> dict[str, Any]:
    """Expand follow-up questions using conversation context.

    Identifies which previous query is being referenced and
    rewrites the question as a complete, standalone query.

    Args:
        state: Current chatbot state with user_query and conversation_history.

    Returns:
        Dict with resolved_query and referenced_query_id fields.
    """
    with logfire.span("resolve_context", current_query=state.get("user_query", "")[:100]):
        # Format history with query IDs for reference
        history = state.get("conversation_history", [])
        history_text = "\n".join(
            [
                f"[Query {i + 1}] User: {turn['user']}\nBot: {turn['bot'][:300]}"
                for i, turn in enumerate(history[-5:])
            ]
        )

        if not history_text:
            logfire.info("No history to resolve against")
            return {
                "resolved_query": state.get("user_query"),
                "referenced_query_id": None,
            }

        with logfire.span("llm_context_resolution"):
            llm = ChatOpenAI(
                model=settings.AI_MODEL,
                temperature=0,
                api_key=settings.OPENAI_API_KEY,
            )
            chain = CONTEXT_RESOLVER_PROMPT | llm
            response = chain.invoke(
                {
                    "current_query": state.get("user_query", ""),
                    "history": history_text,
                }
            )

        resolved = response.content.strip()
        referenced_id = state.get("current_query_id")

        logfire.info(
            "Context resolved",
            original=state.get("user_query", "")[:100],
            resolved=resolved[:100],
        )

        return {
            "resolved_query": resolved,
            "referenced_query_id": referenced_id,
        }
