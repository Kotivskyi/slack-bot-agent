"""Schemas for the evaluation framework.

Defines the input/output types for agent evaluation using pydantic-evals.
"""

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
