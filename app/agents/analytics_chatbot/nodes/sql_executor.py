"""SQL executor node for the analytics chatbot.

Executes SQL and returns results or errors for retry routing.
No LLM calls - pure database operations via repository.
"""

import hashlib
import logging
from typing import Any

import logfire
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analytics_chatbot.state import ChatbotState
from app.repositories import AnalyticsRepository

logger = logging.getLogger(__name__)


async def execute_sql(
    state: ChatbotState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Execute SQL query and return results.

    On success, returns results with sql_error=None.
    On failure, returns sql_error for retry routing.

    Dependencies are read from config["configurable"]:
    - analytics_db: Database session for query execution.
    - analytics_repo: Analytics repository for query execution.

    Args:
        state: Current chatbot state with generated_sql.
        config: RunnableConfig with configurable dependencies.

    Returns:
        Dict with query_results, row_count, column_names, current_query_id,
        and sql_error (None on success, error message on failure).
    """
    # Get dependencies from config
    configurable = config.get("configurable", {})
    db: AsyncSession = configurable["analytics_db"]
    repository: AnalyticsRepository = configurable["analytics_repo"]

    sql = state.get("generated_sql", "")
    sql_hash = hashlib.md5(sql.encode()).hexdigest()[:8]

    with logfire.span("execute_sql", sql_hash=sql_hash):
        try:
            # Execute query via the repository
            rows, columns = await repository.execute_query(db, sql)

            # Generate query ID from SQL hash (useful for button references)
            query_id = sql_hash

            logfire.info(
                "Query executed successfully",
                query_id=query_id,
                row_count=len(rows),
                columns=columns,
            )

            return {
                "query_results": rows,
                "row_count": len(rows),
                "column_names": columns,
                "current_query_id": query_id,
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
