"""Context resolver node for the analytics chatbot.

Resolves query context using conversation history to create standalone queries.
For all analytics queries (both new and follow-ups), this node produces
a complete, self-contained query for SQL generation.
"""

import logging
from typing import Any

import logfire
from langchain_core.runnables import RunnableConfig

from app.agents.analytics_chatbot.prompts import CONTEXT_RESOLVER_PROMPT
from app.agents.analytics_chatbot.state import ChatbotState

logger = logging.getLogger(__name__)


def resolve_context(state: ChatbotState, config: RunnableConfig) -> dict[str, Any]:
    """Resolve query context using conversation history.

    For all analytics queries (both new and follow-ups), this node:
    1. Analyzes the current query in context of conversation history
    2. Produces a standalone, complete query for SQL generation
    3. For new topics or no history, returns the original query unchanged

    Args:
        state: Current chatbot state with user_query and conversation_history.
        config: RunnableConfig with llm_client in configurable.

    Returns:
        Dict with resolved_query and referenced_query_id fields.
    """
    with logfire.span(
        "resolve_context",
        current_query=state.get("user_query", "")[:100],
        intent=state.get("intent"),
    ):
        history = state.get("conversation_history", [])
        user_query = state.get("user_query", "")

        # Fast path: No history means no context resolution needed
        if not history:
            logfire.info("No history - returning original query")
            return {
                "resolved_query": user_query,
                "referenced_query_id": None,
            }

        # Format history for LLM
        history_text = "\n".join(
            [
                f"[Query {i + 1}] User: {turn['user']}\nBot: {turn['bot'][:300]}"
                for i, turn in enumerate(history[-5:])
            ]
        )

        with logfire.span("llm_context_resolution"):
            llm = config.get("configurable", {}).get("llm_client")
            chain = CONTEXT_RESOLVER_PROMPT | llm
            response = chain.invoke(
                {
                    "current_query": user_query,
                    "history": history_text,
                }
            )

        resolved = response.content.strip()

        # Track whether context was actually used
        context_used = resolved.lower() != user_query.lower()
        referenced_id = state.get("current_query_id") if context_used else None

        logfire.info(
            "Context resolved",
            original=user_query[:100],
            resolved=resolved[:100],
            context_used=context_used,
        )

        return {
            "resolved_query": resolved,
            "referenced_query_id": referenced_id,
        }
