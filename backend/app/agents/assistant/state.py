"""Agent state definitions for the assistant graph.

Contains TypedDict definitions for agent state that flows through the graph.
"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentContext(TypedDict, total=False):
    """Runtime context for the agent.

    Passed via config parameter to the graph.
    Contains user-specific information and metadata.
    """

    user_id: str | None
    user_name: str | None
    metadata: dict[str, Any]


class AgentState(TypedDict):
    """State for the LangGraph agent.

    This is what flows through the agent graph.
    The messages field uses add_messages reducer to properly
    append new messages to the conversation history.
    """

    messages: Annotated[list[BaseMessage], add_messages]
