"""Tools for the assistant agent.

Contains tool definitions and utilities for the agent.
"""

from datetime import UTC, datetime

from langchain_core.tools import tool


@tool
def current_datetime() -> str:
    """Get the current date and time.

    Use this tool when you need to know the current date or time.
    Returns the current datetime in ISO format with timezone.
    """
    return datetime.now(UTC).isoformat()


# List of all available tools for the assistant
TOOLS = [current_datetime]

# Dictionary for quick tool lookup by name
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
