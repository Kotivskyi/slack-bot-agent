"""Agent service for managing AI agent interactions.

Provides a high-level interface for running and streaming agent responses,
handling conversation history and tool execution.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import AgentContext, build_assistant_graph
from app.agents.analytics_chatbot import AnalyticsChatbot

if TYPE_CHECKING:
    from app.repositories import AnalyticsRepository

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """Event emitted during agent streaming.

    Attributes:
        type: Event type (text_delta, tool_call, tool_result, final_result, etc.)
        data: Event data payload.
    """

    type: str
    data: dict = field(default_factory=dict)


@dataclass
class AnalyticsResponse:
    """Response from the analytics chatbot.

    Attributes:
        text: Response text for Slack message.
        slack_blocks: Slack Block Kit blocks for rich formatting.
        intent: Classified intent of the user query.
        conversation_history: Updated conversation history.
        generated_sql: The SQL query if one was generated.
        action_id: UUID for button action lookups.
        csv_content: CSV content if export was requested.
        csv_filename: Filename for CSV export.
        csv_title: Title for CSV file.
    """

    text: str
    slack_blocks: list[dict] | None = None
    intent: str | None = None
    conversation_history: list[dict] | None = None
    generated_sql: str | None = None
    action_id: str | None = None
    csv_content: str | None = None
    csv_filename: str | None = None
    csv_title: str | None = None


class AgentService:
    """Service for AI agent interactions.

    Provides high-level methods for running agents with
    conversation history management, and streaming support.

    Usage:
        agent_service = AgentService()
        output, tool_events = await agent_service.run(
            user_input="Hello",
            thread_id="thread-123",
        )

        # Or with streaming:
        async for event in agent_service.stream(user_input, thread_id):
            if event.type == "text_delta":
                print(event.data["content"], end="")
    """

    def __init__(
        self,
        *,
        model_name: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ):
        """Initialize the agent service.

        Args:
            model_name: Optional model name override.
            temperature: Optional temperature override.
            system_prompt: Optional system prompt override.
        """
        self._model_name = model_name
        self._temperature = temperature
        self._system_prompt = system_prompt
        self._graph: CompiledStateGraph | None = None

    @property
    def graph(self) -> CompiledStateGraph:
        """Get or create the compiled graph instance."""
        if self._graph is None:
            self._graph = build_assistant_graph(
                model_name=self._model_name,
                temperature=self._temperature,
                system_prompt=self._system_prompt,
            )
        return self._graph

    @staticmethod
    def _convert_history(
        history: list[dict[str, str]] | None,
    ) -> list[HumanMessage | AIMessage]:
        """Convert conversation history to LangChain message format.

        Args:
            history: List of message dicts with 'role' and 'content'.

        Returns:
            List of LangChain message objects.
        """
        messages: list[HumanMessage | AIMessage] = []

        for msg in history or []:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

        return messages

    async def run(
        self,
        user_input: str,
        thread_id: str,
        *,
        history: list[dict[str, str]] | None = None,
        context: AgentContext | None = None,
    ) -> tuple[str, list[Any]]:
        """Run the agent and return the final output.

        Args:
            user_input: The user's message.
            thread_id: Thread ID for conversation continuity.
            history: Optional conversation history.
            context: Optional runtime context with user info.

        Returns:
            Tuple of (output_text, tool_events).
        """
        messages = self._convert_history(history)
        messages.append(HumanMessage(content=user_input))

        agent_context: AgentContext = context if context is not None else {}

        logger.info(f"Running agent with user input: {user_input[:100]}...")

        config = {
            "configurable": {
                "thread_id": thread_id,
                **agent_context,
            }
        }

        result = await self.graph.ainvoke({"messages": messages}, config=config)

        output = ""
        tool_events: list[Any] = []

        for message in result.get("messages", []):
            if isinstance(message, AIMessage):
                if message.content:
                    output = (
                        message.content
                        if isinstance(message.content, str)
                        else str(message.content)
                    )
                if hasattr(message, "tool_calls") and message.tool_calls:
                    tool_events.extend(message.tool_calls)

        logger.info(f"Agent run complete. Output length: {len(output)} chars")

        return output, tool_events

    async def stream(
        self,
        user_input: str,
        thread_id: str,
        *,
        history: list[dict[str, str]] | None = None,
        context: AgentContext | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream agent execution with events for each step.

        Yields StreamEvent objects for:
        - text_delta: Streaming text chunks from the model
        - tool_call: When a tool is called
        - tool_result: When a tool returns a result
        - final_result: The final output text

        Args:
            user_input: The user's message.
            thread_id: Thread ID for conversation continuity.
            history: Optional conversation history.
            context: Optional runtime context with user info.

        Yields:
            StreamEvent instances.
        """
        messages = self._convert_history(history)
        messages.append(HumanMessage(content=user_input))

        agent_context: AgentContext = context if context is not None else {}

        config = {
            "configurable": {
                "thread_id": thread_id,
                **agent_context,
            }
        }

        logger.info(f"Starting stream for user input: {user_input[:100]}...")

        final_output = ""
        seen_tool_call_ids: set[str] = set()

        async for stream_mode, data in self.graph.astream(
            {"messages": messages},
            config=config,
            stream_mode=["messages", "updates"],
        ):
            if stream_mode == "messages":
                chunk, _metadata = data

                if isinstance(chunk, AIMessageChunk):
                    # Handle text content
                    if chunk.content:
                        text_content = self._extract_text_content(chunk.content)
                        if text_content:
                            yield StreamEvent(
                                type="text_delta",
                                data={"content": text_content},
                            )
                            final_output += text_content

                    # Handle tool call chunks
                    if chunk.tool_call_chunks:
                        for tc_chunk in chunk.tool_call_chunks:
                            tc_id = tc_chunk.get("id")
                            tc_name = tc_chunk.get("name")
                            if tc_id and tc_name and tc_id not in seen_tool_call_ids:
                                seen_tool_call_ids.add(tc_id)
                                yield StreamEvent(
                                    type="tool_call",
                                    data={
                                        "tool_name": tc_name,
                                        "args": {},
                                        "tool_call_id": tc_id,
                                    },
                                )

            elif stream_mode == "updates":
                for node_name, update in data.items():
                    if node_name == "tools":
                        for msg in update.get("messages", []):
                            if isinstance(msg, ToolMessage):
                                yield StreamEvent(
                                    type="tool_result",
                                    data={
                                        "tool_call_id": msg.tool_call_id,
                                        "content": msg.content,
                                    },
                                )
                    elif node_name == "agent":
                        for msg in update.get("messages", []):
                            if isinstance(msg, AIMessage) and msg.tool_calls:
                                for tc in msg.tool_calls:
                                    tc_id = tc.get("id", "")
                                    if tc_id not in seen_tool_call_ids:
                                        seen_tool_call_ids.add(tc_id)
                                        yield StreamEvent(
                                            type="tool_call",
                                            data={
                                                "tool_name": tc.get("name", ""),
                                                "args": tc.get("args", {}),
                                                "tool_call_id": tc_id,
                                            },
                                        )

        yield StreamEvent(
            type="final_result",
            data={"output": final_output},
        )

    @staticmethod
    def _extract_text_content(content: str | list) -> str:
        """Extract text content from message content.

        Args:
            content: Either a string or a list of content blocks.

        Returns:
            Extracted text content.
        """
        if isinstance(content, str):
            return content

        text_parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif isinstance(block, str):
                text_parts.append(block)

        return "".join(text_parts)


class AnalyticsAgentService:
    """Service for analytics chatbot interactions.

    Provides a high-level interface for running the analytics chatbot
    with SQL generation, caching, and Slack Block Kit formatting.

    Usage:
        analytics_service = AnalyticsAgentService(analytics_db=analytics_db)
        response = await analytics_service.run(
            user_query="How many apps do we have?",
            thread_id="thread-123",
            user_id="U12345",
            channel_id="C12345",
        )
    """

    def __init__(
        self,
        analytics_db: AsyncSession,
    ):
        """Initialize the analytics agent service.

        Args:
            analytics_db: Database session for analytics SQL queries (read-only).
        """
        self._analytics_db = analytics_db
        self._analytics_repository: AnalyticsRepository | None = None
        self._chatbot: AnalyticsChatbot | None = None

    @property
    def analytics_repository(self) -> "AnalyticsRepository":
        """Get or create the AnalyticsRepository instance.

        Pattern 1: Repository created without session.
        Session is passed to methods at call time.
        """
        if self._analytics_repository is None:
            from app.repositories import AnalyticsRepository

            self._analytics_repository = AnalyticsRepository()
        return self._analytics_repository

    @property
    def chatbot(self) -> AnalyticsChatbot:
        """Get or create the AnalyticsChatbot instance."""
        if self._chatbot is None:
            self._chatbot = AnalyticsChatbot(
                db=self._analytics_db,
                repository=self.analytics_repository,
            )
        return self._chatbot

    async def run(
        self,
        user_query: str,
        thread_id: str,
        *,
        user_id: str = "",
        channel_id: str = "",
        thread_ts: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AnalyticsResponse:
        """Run the analytics chatbot for a user query.

        Args:
            user_query: The user's question or command.
            thread_id: Unique identifier for the conversation thread.
            user_id: Slack user ID.
            channel_id: Slack channel ID.
            thread_ts: Slack thread timestamp.
            conversation_history: Previous Q&A pairs in session.

        Returns:
            AnalyticsResponse with text, blocks, and updated state.
        """
        logger.info(f"Running analytics chatbot: {user_query[:100]}...")

        result = await self.chatbot.run(
            user_query=user_query,
            thread_id=thread_id,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            conversation_history=conversation_history,
        )

        # Use conversation_history from graph result (updated by terminal nodes)
        response = AnalyticsResponse(
            text=result.get("response_text", ""),
            slack_blocks=result.get("slack_blocks"),
            intent=result.get("intent"),
            conversation_history=result.get("conversation_history", []),
            generated_sql=result.get("generated_sql"),
            action_id=result.get("action_id"),
            csv_content=result.get("csv_content"),
            csv_filename=result.get("csv_filename"),
            csv_title=result.get("csv_title"),
        )

        logger.info(
            f"Analytics chatbot complete. Intent: {response.intent}, "
            f"Response length: {len(response.text)} chars"
        )

        return response
