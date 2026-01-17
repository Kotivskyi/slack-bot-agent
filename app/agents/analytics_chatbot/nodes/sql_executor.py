"""SQL executor node for the analytics chatbot.

Executes validated SQL and caches results for later retrieval.
No LLM calls - pure database operations via repository.
"""

import hashlib
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

import logfire
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analytics_chatbot.state import CacheEntry, ChatbotState

if TYPE_CHECKING:
    from app.repositories import AnalyticsRepository

logger = logging.getLogger(__name__)


async def execute_and_cache(
    state: ChatbotState,
    db: AsyncSession,
    repository: "AnalyticsRepository",
) -> dict[str, Any]:
    """Execute SQL query and cache results.

    Caching enables cost-effective CSV export and SQL retrieval
    without regenerating queries.

    Args:
        state: Current chatbot state with generated_sql.
        db: Database session for query execution.
        repository: Analytics repository for query execution.

    Returns:
        Dict with query_results, row_count, column_names, current_query_id,
        and updated query_cache.
    """
    sql = state.get("generated_sql", "")
    sql_hash = hashlib.md5(sql.encode()).hexdigest()[:8]

    with logfire.span("execute_and_cache", sql_hash=sql_hash):
        try:
            # Execute query via the repository
            rows, columns = await repository.execute_query(db, sql)

            # Generate cache key from SQL hash
            query_id = sql_hash

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
