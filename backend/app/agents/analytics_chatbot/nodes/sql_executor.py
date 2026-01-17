"""SQL executor node for the analytics chatbot.

Executes validated SQL and caches results for later retrieval.
No LLM calls - pure database operations.
"""

import hashlib
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

import logfire
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analytics_chatbot.state import CacheEntry, ChatbotState

logger = logging.getLogger(__name__)


def _serialize_value(value: Any) -> Any:
    """Convert database values to JSON-serializable format."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):  # date, time, etc.
        return value.isoformat()
    return value


async def execute_and_cache(state: ChatbotState, db: AsyncSession) -> dict[str, Any]:
    """Execute SQL query and cache results.

    Caching enables cost-effective CSV export and SQL retrieval
    without regenerating queries.

    Args:
        state: Current chatbot state with generated_sql.
        db: Async database session for query execution.

    Returns:
        Dict with query_results, row_count, column_names, current_query_id,
        and updated query_cache.
    """
    sql = state.get("generated_sql", "")

    with logfire.span("execute_and_cache", sql_hash=hashlib.md5(sql.encode()).hexdigest()[:8]):
        try:
            # Execute query
            result = await db.execute(text(sql))
            columns = list(result.keys())
            rows_raw = result.fetchall()

            # Convert to list of dicts with JSON-serializable values
            rows = [
                {col: _serialize_value(row[i]) for i, col in enumerate(columns)} for row in rows_raw
            ]

            # Generate cache key from SQL hash
            query_id = hashlib.md5(sql.encode()).hexdigest()[:8]

            # Build cache entry
            cache_entry: CacheEntry = {
                "sql": sql,
                "results": rows,
                "timestamp": datetime.now(),
                "natural_query": state.get("resolved_query") or state.get("user_query", ""),
                "assumptions": state.get("assumptions_made", []),
            }

            # Update cache (keep last 10 queries per session)
            updated_cache = dict(state.get("query_cache", {}))
            updated_cache[query_id] = cache_entry

            # Prune old entries if cache too large
            if len(updated_cache) > 10:
                oldest_key = min(updated_cache, key=lambda k: updated_cache[k]["timestamp"])
                del updated_cache[oldest_key]

            logfire.info(
                "Query executed and cached",
                query_id=query_id,
                row_count=len(rows),
                columns=columns,
            )

            return {
                "query_results": rows,
                "row_count": len(rows),
                "column_names": columns,
                "current_query_id": query_id,
                "query_cache": updated_cache,
                "sql_error": None,
            }

        except Exception as e:
            logfire.error("Query execution failed", error=str(e))
            return {
                "query_results": None,
                "sql_error": f"Execution failed: {e!s}",
                "row_count": 0,
                "column_names": [],
            }


def execute_and_cache_sync(state: ChatbotState) -> dict[str, Any]:
    """Synchronous wrapper that returns a partial state requiring async execution.

    This is used when the graph is invoked synchronously.
    The actual execution happens via the graph's async invoke.

    Note: In practice, the graph should always be invoked with ainvoke()
    to support async database operations.
    """
    # This node requires async execution
    # Return error if called synchronously
    logfire.warn("execute_and_cache called synchronously, returning error")
    return {
        "query_results": None,
        "sql_error": "SQL execution requires async context. Use ainvoke() to run the graph.",
        "row_count": 0,
        "column_names": [],
    }
