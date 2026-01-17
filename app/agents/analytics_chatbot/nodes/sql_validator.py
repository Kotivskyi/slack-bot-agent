"""SQL validator node for the analytics chatbot.

Validates SQL syntax and ensures safety (no write operations).
No LLM calls - pure programmatic validation.
"""

import logging
from typing import Any

import logfire
import sqlparse

from app.agents.analytics_chatbot.state import ChatbotState

logger = logging.getLogger(__name__)

# Keywords that indicate dangerous write operations
DANGEROUS_KEYWORDS = [
    "DROP",
    "DELETE",
    "UPDATE",
    "INSERT",
    "TRUNCATE",
    "ALTER",
    "CREATE",
    "GRANT",
    "REVOKE",
    "EXEC",
    "EXECUTE",
]


def validate_sql(state: ChatbotState) -> dict[str, Any]:
    """Validate SQL for syntax correctness and safety.

    No LLM calls - pure programmatic validation.
    Checks for:
    1. Presence of SQL query
    2. No dangerous write operations
    3. Valid SQL syntax via sqlparse

    Args:
        state: Current chatbot state with generated_sql.

    Returns:
        Dict with sql_valid and sql_error fields.
    """
    sql = state.get("generated_sql")

    with logfire.span("validate_sql", sql_length=len(sql) if sql else 0):
        if not sql:
            logfire.warn("No SQL query to validate")
            return {
                "sql_valid": False,
                "sql_error": "No SQL query generated",
            }

        # ===== Safety Check: No write operations =====
        sql_upper = sql.upper()
        for keyword in DANGEROUS_KEYWORDS:
            # Check for keyword as a whole word (not part of another word)
            if f" {keyword} " in f" {sql_upper} " or sql_upper.startswith(f"{keyword} "):
                logfire.error("Dangerous keyword detected", keyword=keyword)
                return {
                    "sql_valid": False,
                    "sql_error": f"Write operation '{keyword}' not allowed. Only SELECT queries are permitted.",
                }

        # ===== Verify it's a SELECT statement =====
        if not sql_upper.strip().startswith("SELECT") and not sql_upper.strip().startswith("WITH"):
            logfire.error("Query is not a SELECT statement")
            return {
                "sql_valid": False,
                "sql_error": "Only SELECT queries are permitted.",
            }

        # ===== Syntax Validation via sqlparse =====
        try:
            parsed = sqlparse.parse(sql)
            if not parsed or not parsed[0].tokens:
                logfire.error("SQL parse failed - no tokens")
                return {
                    "sql_valid": False,
                    "sql_error": "Failed to parse SQL query",
                }
        except Exception as e:
            logfire.error("SQL parse exception", error=str(e))
            return {
                "sql_valid": False,
                "sql_error": f"SQL parse error: {e!s}",
            }

        # Note: Database-level validation via EXPLAIN would require async DB access
        # For now, we trust sqlparse validation. The executor will catch any runtime errors.

        logfire.info("SQL validation passed")
        return {"sql_valid": True, "sql_error": None}
