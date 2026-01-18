"""Graph definition for the assistant agent.

Contains the graph building function that creates the compiled LangGraph.
"""

from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.assistant.nodes import agent_node, create_model, should_continue, tools_node
from app.agents.assistant.prompts import DEFAULT_SYSTEM_PROMPT
from app.agents.assistant.state import AgentState
from app.core.config import settings


def build_assistant_graph(
    model_name: str | None = None,
    temperature: float | None = None,
    system_prompt: str | None = None,
) -> CompiledStateGraph:
    """Build and compile the assistant graph.

    Creates a ReAct-style agent graph with:
    - An agent node that processes messages and decides actions
    - A tools node that executes tool calls
    - Conditional edges that loop back for tool execution or end

    Args:
        model_name: Optional model name override (defaults to settings).
        temperature: Optional temperature override (defaults to settings).
        system_prompt: Optional system prompt override.

    Returns:
        Compiled StateGraph ready for invocation.
    """
    # Build model ONCE at graph creation (not per invocation)
    model = create_model(
        model_name or settings.AI_MODEL,
        temperature if temperature is not None else settings.AI_TEMPERATURE,
    )

    # Bind model and prompt to agent_node
    bound_agent_node = partial(
        agent_node,
        model=model,
        system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
    )

    # Build the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent", bound_agent_node)
    workflow.add_node("tools", tools_node)

    # Add edges
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "__end__": END},
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile()
