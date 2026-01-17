"""SQL generator node for the analytics chatbot.

Converts natural language questions into SQL queries.
"""

import json
import logging
from typing import Any

import logfire
from langchain_openai import ChatOpenAI

from app.agents.analytics_chatbot.prompts import (
    DB_SCHEMA,
    FEW_SHOT_EXAMPLES,
    SQL_GENERATOR_PROMPT,
    SQL_RETRY_PROMPT,
)
from app.agents.analytics_chatbot.state import ChatbotState
from app.core.config import settings

logger = logging.getLogger(__name__)


def generate_sql(state: ChatbotState) -> dict[str, Any]:
    """Generate SQL from natural language query.

    Uses the resolved query if available (for follow-ups).
    On retry, includes the previous error for context.

    Args:
        state: Current chatbot state with user_query or resolved_query.

    Returns:
        Dict with generated_sql, assumptions_made, and retry_count fields.
    """
    query = state.get("resolved_query") or state.get("user_query", "")
    retry_count = state.get("retry_count", 0)
    previous_sql = state.get("generated_sql")
    sql_error = state.get("sql_error")

    with logfire.span("generate_sql", query=query[:100], retry_count=retry_count):
        llm = ChatOpenAI(
            model=settings.AI_MODEL,
            temperature=0,
            api_key=settings.OPENAI_API_KEY,
        )

        # Use retry prompt if this is a retry with previous error
        if retry_count > 0 and previous_sql and sql_error:
            with logfire.span("llm_sql_retry"):
                chain = SQL_RETRY_PROMPT | llm
                response = chain.invoke(
                    {
                        "schema": DB_SCHEMA,
                        "query": query,
                        "previous_sql": previous_sql,
                        "error": sql_error,
                    }
                )
        else:
            with logfire.span("llm_sql_generation"):
                chain = SQL_GENERATOR_PROMPT | llm
                response = chain.invoke(
                    {
                        "schema": DB_SCHEMA,
                        "examples": FEW_SHOT_EXAMPLES,
                        "query": query,
                    }
                )

        try:
            result = json.loads(response.content)
            logfire.info(
                "SQL generated successfully",
                sql_length=len(result.get("sql", "")),
                assumptions_count=len(result.get("assumptions", [])),
            )
            return {
                "generated_sql": result.get("sql", ""),
                "assumptions_made": result.get("assumptions", []),
                "retry_count": retry_count + 1,
                "sql_error": None,  # Clear previous error on success
            }
        except json.JSONDecodeError:
            # Try to extract SQL from response
            content = response.content
            if "SELECT" in content.upper():
                # Extract SQL between first SELECT and semicolon or end
                start = content.upper().find("SELECT")
                end = content.find(";", start)
                if end == -1:
                    end = len(content)
                sql = content[start : end + 1] if content[end : end + 1] == ";" else content[start:]

                logfire.warn("Parsed SQL from non-JSON response")
                return {
                    "generated_sql": sql.strip(),
                    "assumptions_made": [],
                    "retry_count": retry_count + 1,
                    "sql_error": None,
                }

            logfire.error("Failed to generate valid SQL", response=content[:200])
            return {
                "generated_sql": None,
                "assumptions_made": [],
                "retry_count": retry_count + 1,
                "sql_error": "Failed to generate valid SQL from LLM response",
            }
