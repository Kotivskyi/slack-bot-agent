"""Wrapper for running chatbot with prompt overrides.

Provides utilities for running the analytics chatbot with dynamically
injected prompts during training.
"""

import logging
from typing import Any
from unittest.mock import patch

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analytics_chatbot import AnalyticsChatbot
from app.repositories import AnalyticsRepository

logger = logging.getLogger(__name__)


def create_sql_prompt_from_template(template: str) -> ChatPromptTemplate:
    """Create a ChatPromptTemplate from a template string.

    Converts Jinja-style templates to LangChain format:
    - {{ variable }} -> {variable} (template variables)
    - { literal } -> {{ literal }} (escaped braces for JSON)

    Args:
        template: The system prompt template string (Jinja format).

    Returns:
        ChatPromptTemplate configured for SQL generation.
    """
    import re

    # Step 1: Temporarily replace Jinja variables {{ var }} with a placeholder
    # to protect them during the next step
    jinja_vars: list[str] = []

    def capture_jinja_var(match: re.Match) -> str:
        var_name = match.group(1).strip()
        jinja_vars.append(var_name)
        return f"__JINJA_VAR_{len(jinja_vars) - 1}__"

    temp = re.sub(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}", capture_jinja_var, template)

    # Step 2: Escape all remaining single braces for LangChain
    # { -> {{ and } -> }}
    temp = temp.replace("{", "{{").replace("}", "}}")

    # Step 3: Restore Jinja variables as LangChain variables
    for i, var_name in enumerate(jinja_vars):
        temp = temp.replace(f"__JINJA_VAR_{i}__", "{" + var_name + "}")

    return ChatPromptTemplate.from_messages(
        [
            ("system", temp),
            ("human", "Question: {query}"),
        ]
    )


async def run_chatbot_with_prompt_override(
    user_query: str,
    thread_id: str,
    conversation_history: list[dict[str, str]],
    analytics_db: AsyncSession,
    llm_client: ChatOpenAI,
    repository: AnalyticsRepository,
    sql_generator_prompt: str | None = None,
) -> dict[str, Any]:
    """Run the analytics chatbot with an optional prompt override.

    This function allows running the chatbot with a dynamically injected
    SQL generator prompt, which is useful for training with agent-lightning.

    Args:
        user_query: The user's question.
        thread_id: Unique identifier for the conversation thread.
        conversation_history: Previous Q&A pairs.
        analytics_db: Database session for SQL execution.
        llm_client: LLM client for all LLM operations.
        repository: Analytics repository for SQL execution.
        sql_generator_prompt: Optional custom SQL generator prompt template.

    Returns:
        Result dict from chatbot execution.
    """
    chatbot = AnalyticsChatbot(
        db=analytics_db,
        repository=repository,
        llm_client=llm_client,
    )

    # If no custom prompt, run normally
    if sql_generator_prompt is None:
        result = await chatbot.run(
            user_query=user_query,
            thread_id=thread_id,
            conversation_history=conversation_history,
        )
        return _normalize_result(result)

    # Run with patched prompt
    custom_prompt = create_sql_prompt_from_template(sql_generator_prompt)

    with patch(
        "app.agents.analytics_chatbot.nodes.sql_generator.SQL_GENERATOR_PROMPT",
        custom_prompt,
    ):
        result = await chatbot.run(
            user_query=user_query,
            thread_id=thread_id,
            conversation_history=conversation_history,
        )

    return _normalize_result(result)


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize chatbot result for reward calculation.

    Args:
        result: Raw result from chatbot.

    Returns:
        Normalized dict with expected keys.
    """
    normalized = {
        "text": result.get("response_text", ""),
        "intent": result.get("intent"),
        "generated_sql": result.get("generated_sql"),
        "sql_error": result.get("sql_error"),
        "query_results": result.get("query_results"),
        "response_format": result.get("response_format"),
        "csv_content": result.get("csv_content"),
        "assumptions": result.get("assumptions_made", []),
    }

    # Extract token usage from messages if available
    # LangGraph stores messages with response_metadata containing token usage
    token_usage = _extract_token_usage(result.get("messages", []))
    if token_usage:
        normalized["token_usage"] = token_usage

    return normalized


def _extract_token_usage(messages: list[Any]) -> dict[str, int] | None:
    """Extract token usage from LangChain messages.

    Args:
        messages: List of LangChain messages from the graph.

    Returns:
        Dict with input_tokens and output_tokens, or None if not available.
    """
    total_input = 0
    total_output = 0
    found_usage = False

    for msg in messages:
        # Check if message has response_metadata with token usage
        if hasattr(msg, "response_metadata"):
            metadata = msg.response_metadata
            if "token_usage" in metadata:
                usage = metadata["token_usage"]
                total_input += usage.get("prompt_tokens", 0)
                total_output += usage.get("completion_tokens", 0)
                found_usage = True
            elif "usage" in metadata:
                usage = metadata["usage"]
                total_input += usage.get("input_tokens", 0)
                total_output += usage.get("output_tokens", 0)
                found_usage = True

    if found_usage:
        return {"input_tokens": total_input, "output_tokens": total_output}
    return None


async def run_chatbot_simple(
    user_query: str,
    thread_id: str,
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Run the chatbot with default configuration.

    Convenience function for evaluation that handles database context
    and LLM client creation.

    Args:
        user_query: The user's question.
        thread_id: Unique identifier for the conversation thread.
        conversation_history: Previous Q&A pairs.

    Returns:
        Normalized result dict.
    """
    from app.db.session import get_analytics_db_context
    from app.services.llm import get_llm_client

    async with get_analytics_db_context() as analytics_db:
        llm_client = get_llm_client()
        repository = AnalyticsRepository()

        return await run_chatbot_with_prompt_override(
            user_query=user_query,
            thread_id=thread_id,
            conversation_history=conversation_history or [],
            analytics_db=analytics_db,
            llm_client=llm_client,
            repository=repository,
        )
