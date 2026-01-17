"""Analytics repository for executing read-only SQL queries.

Provides a clean interface for the analytics chatbot to execute
user-generated SQL queries against the database.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

import logfire
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class AnalyticsRepository:
    """Repository for executing analytics SQL queries.

    Follows Pattern 1: session passed to methods (not held in __init__).

    Usage:
        repo = AnalyticsRepository()
        rows, columns = await repo.execute_query(db, "SELECT * FROM users")
    """

    async def execute_query(
        self,
        db: AsyncSession,
        sql: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Execute a read-only SQL query and return results.

        Args:
            db: Async database session (should be read-only).
            sql: SQL query string to execute.

        Returns:
            Tuple of (rows as list of dicts, column names).

        Raises:
            Exception: If query execution fails.
        """
        with logfire.span("AnalyticsRepository.execute_query", sql_preview=sql[:100]):
            result = await db.execute(text(sql))
            columns = list(result.keys())
            rows_raw = result.fetchall()

            # Convert to list of dicts with JSON-serializable values
            rows = [
                {col: self._serialize_value(row[i]) for i, col in enumerate(columns)}
                for row in rows_raw
            ]

            logfire.info(
                "Query executed",
                row_count=len(rows),
                column_count=len(columns),
            )

            return rows, columns

    @staticmethod
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
