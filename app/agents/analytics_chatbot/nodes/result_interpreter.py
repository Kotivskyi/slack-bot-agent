"""Result interpreter node for the analytics chatbot.

Interprets query results and decides on response format (simple text vs table).
"""

import logging
from typing import Any

import logfire
from langchain_openai import ChatOpenAI

from app.agents.analytics_chatbot.prompts import INTERPRETER_PROMPT
from app.agents.analytics_chatbot.state import ChatbotState
from app.core.config import settings

logger = logging.getLogger(__name__)


def interpret_results(state: ChatbotState) -> dict[str, Any]:
    """Interpret query results and decide presentation format.

    Determines if results should be shown as simple text or table format
    based on row count and column structure.

    Args:
        state: Current chatbot state with query_results, column_names, and row_count.

    Returns:
        Dict with response_format and response_text fields.
    """
    results = state.get("query_results", [])
    columns = state.get("column_names", [])
    row_count = state.get("row_count", 0)

    with logfire.span("interpret_results", row_count=row_count, column_count=len(columns)):
        # Handle empty results
        if not results or row_count == 0:
            logfire.info("No results to interpret")
            return {
                "response_format": "simple",
                "response_text": "The query returned no results. This might mean there's no data matching your criteria, or the filters might be too restrictive.",
            }

        # ===== Determine response format =====
        # Simple format: single row with 1-2 numeric columns
        is_simple = (
            row_count == 1
            and len(columns) <= 2
            and all(isinstance(results[0].get(c), int | float | str | None) for c in columns)
        )

        response_format = "simple" if is_simple else "table"
        logfire.info("Response format determined", format=response_format)

        # ===== Generate interpretation =====
        sample_data = results[:5] if results else []

        with logfire.span("llm_interpretation"):
            llm = ChatOpenAI(
                model=settings.AI_MODEL,
                temperature=0.3,  # Slightly more creative for interpretations
                api_key=settings.OPENAI_API_KEY,
            )
            chain = INTERPRETER_PROMPT | llm
            response = chain.invoke(
                {
                    "query": state.get("resolved_query") or state.get("user_query", ""),
                    "assumptions": ", ".join(state.get("assumptions_made", [])) or "None",
                    "row_count": row_count,
                    "columns": ", ".join(columns),
                    "sample_data": str(sample_data),
                }
            )

        return {
            "response_format": response_format,
            "response_text": response.content.strip(),
        }
