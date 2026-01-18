"""Schemas for the evaluation framework.

Defines the input/output types for agent evaluation using pydantic-evals.
"""

from typing import Literal

from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    """Input for agent evaluation.

    Attributes:
        user_input: The user's message to the agent.
        thread_id: Optional thread ID for conversation context.
    """

    user_input: str = Field(description="The user's message to the agent")
    thread_id: str | None = Field(default=None, description="Thread ID for context")


class AgentOutput(BaseModel):
    """Output from agent evaluation.

    Attributes:
        response: The agent's response text.
        tool_calls: List of tools called during execution.
    """

    response: str = Field(description="The agent's response")
    tool_calls: list[dict] = Field(default_factory=list, description="Tools called")


class ExpectedOutput(BaseModel):
    """Expected output for evaluation.

    Attributes:
        contains: Substrings that should be in the response.
        tool_names: Tool names that should have been called.
    """

    contains: list[str] = Field(default_factory=list, description="Expected substrings")
    tool_names: list[str] = Field(default_factory=list, description="Expected tools")


# Analytics Chatbot Schemas


class AnalyticsInput(BaseModel):
    """Input for analytics chatbot evaluation.

    Attributes:
        user_query: The user's question or command.
        conversation_history: Previous Q&A pairs for follow-up context.
        thread_id: Optional thread ID for conversation tracking.
    """

    user_query: str = Field(description="The user's question or command")
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list, description="Previous conversation turns"
    )
    thread_id: str | None = Field(default=None, description="Thread ID for tracking")


class AnalyticsOutput(BaseModel):
    """Output from analytics chatbot evaluation.

    Attributes:
        text: The response text.
        intent: Classified intent of the query.
        generated_sql: SQL query if one was generated.
        response_format: Format of the response (simple, table, error).
        csv_content: CSV content if export was requested.
        has_slack_blocks: Whether Slack blocks were generated.
        assumptions: Any assumptions made during query processing.
    """

    text: str = Field(description="Response text")
    intent: str | None = Field(default=None, description="Classified intent")
    generated_sql: str | None = Field(default=None, description="Generated SQL query")
    response_format: str | None = Field(default=None, description="Response format type")
    csv_content: str | None = Field(default=None, description="CSV content if exported")
    has_slack_blocks: bool = Field(default=False, description="Whether blocks were generated")
    assumptions: list[str] = Field(default_factory=list, description="Assumptions made")


class AnalyticsExpected(BaseModel):
    """Expected output for analytics evaluation.

    Attributes:
        intent: Expected intent classification.
        should_generate_sql: Whether SQL should be generated.
        should_have_csv: Whether CSV content should be present.
        response_contains: Substrings expected in response.
        sql_contains: Substrings expected in SQL (if generated).
        response_format: Expected response format.
    """

    intent: Literal["analytics_query", "follow_up", "export_csv", "show_sql", "off_topic"] | None = (
        Field(default=None, description="Expected intent")
    )
    should_generate_sql: bool | None = Field(default=None, description="Should SQL be generated")
    should_have_csv: bool | None = Field(default=None, description="Should CSV be present")
    response_contains: list[str] = Field(
        default_factory=list, description="Expected response substrings"
    )
    sql_contains: list[str] = Field(default_factory=list, description="Expected SQL substrings")
    response_format: Literal["simple", "table", "error"] | None = Field(
        default=None, description="Expected response format"
    )
