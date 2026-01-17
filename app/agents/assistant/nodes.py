"""Node functions for the assistant graph.

Contains the agent node, tools node, and conditional edge functions.
"""

import logging
from functools import lru_cache
from typing import Literal

from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.agents.assistant.state import AgentState
from app.agents.assistant.tools import TOOLS, TOOLS_BY_NAME
from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def create_model(
    model_name: str,
    temperature: float,
) -> ChatOpenAI:
    """Create and cache the LLM model with tools bound.

    Uses lru_cache to ensure the model is created only once per configuration,
    avoiding repeated initialization on each graph invocation.

    Args:
        model_name: The OpenAI model name.
        temperature: The temperature setting for generation.

    Returns:
        ChatOpenAI instance with tools bound.
    """
    model = ChatOpenAI(
        model=model_name,
        temperature=temperature,
        api_key=settings.OPENAI_API_KEY,
        streaming=True,
    )
    return model.bind_tools(TOOLS)


def agent_node(
    state: AgentState,
    *,
    model: ChatOpenAI,
    system_prompt: str,
) -> dict[str, list[BaseMessage]]:
    """Agent node that processes messages and decides whether to call tools.

    This is the main reasoning node in the ReAct pattern.

    Args:
        state: Current agent state with messages.
        model: The LLM model with tools bound.
        system_prompt: System prompt to use for the agent.

    Returns:
        Dict with messages to add to state.
    """
    messages = [SystemMessage(content=system_prompt), *state["messages"]]
    response = model.invoke(messages)

    tool_count = len(response.tool_calls) if hasattr(response, "tool_calls") else 0
    logger.info(f"Agent processed message - Tool calls: {tool_count}")

    return {"messages": [response]}


def tools_node(state: AgentState) -> dict[str, list[ToolMessage]]:
    """Tools node that executes tool calls from the agent.

    Processes each tool call from the last message and returns results.

    Args:
        state: Current agent state with messages.

    Returns:
        Dict with tool result messages to add to state.
    """
    messages = state["messages"]
    last_message = messages[-1]

    tool_results = []

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            logger.info(f"Executing tool: {tool_name} with args: {tool_args}")

            try:
                tool_fn = TOOLS_BY_NAME.get(tool_name)
                if tool_fn:
                    result = tool_fn.invoke(tool_args)
                    tool_results.append(
                        ToolMessage(
                            content=str(result),
                            tool_call_id=tool_id,
                            name=tool_name,
                        )
                    )
                    logger.info(f"Tool {tool_name} completed successfully")
                else:
                    error_msg = f"Unknown tool: {tool_name}"
                    logger.error(error_msg)
                    tool_results.append(
                        ToolMessage(
                            content=error_msg,
                            tool_call_id=tool_id,
                            name=tool_name,
                        )
                    )
            except Exception as e:
                error_msg = f"Error executing {tool_name}: {e!s}"
                logger.exception(error_msg)
                tool_results.append(
                    ToolMessage(
                        content=error_msg,
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )

    return {"messages": tool_results}


def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    """Conditional edge that decides whether to continue to tools or end.

    Args:
        state: Current agent state.

    Returns:
        "tools" if the agent made tool calls, "__end__" otherwise.
    """
    messages = state["messages"]
    last_message = messages[-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        logger.info(f"Continuing to tools - {len(last_message.tool_calls)} tool(s) to execute")
        return "tools"

    logger.info("No tool calls - ending conversation")
    return "__end__"
