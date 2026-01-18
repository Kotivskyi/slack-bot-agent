"""AI Agents module using LangGraph.

This module contains a ReAct agent built with LangGraph.
The assistant subpackage contains the refactored agent implementation.
"""

from app.agents.assistant import (
    DEFAULT_SYSTEM_PROMPT,
    AgentContext,
    AgentState,
    build_assistant_graph,
)

# Legacy imports for backwards compatibility (deprecated)
from app.agents.langgraph_assistant import LangGraphAssistant, get_agent

__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "AgentContext",
    "AgentState",
    "LangGraphAssistant",
    "build_assistant_graph",
    "get_agent",
]
