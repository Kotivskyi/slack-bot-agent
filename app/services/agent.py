"""Agent service for managing AI agent interactions.

Provides a high-level interface for running the analytics chatbot.
"""

import logging
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analytics_chatbot import AnalyticsChatbot
from app.repositories import AnalyticsRepository

logger = logging.getLogger(__name__)


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


class AnalyticsAgentService:
    """Service for analytics chatbot interactions.

    Provides a high-level interface for running the analytics chatbot
    with SQL generation, caching, and Slack Block Kit formatting.

    All dependencies are injected via constructor.

    Usage:
        analytics_service = AnalyticsAgentService(
            analytics_db=analytics_db,
            analytics_repo=AnalyticsRepository(),
            llm_client=llm_client,
        )
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
        llm_client: ChatOpenAI,
        analytics_repo: AnalyticsRepository | None = None,
    ):
        """Initialize the analytics agent service.

        Args:
            analytics_db: Database session for analytics SQL queries (read-only).
            llm_client: LLM client for all LLM operations.
            analytics_repo: Repository for analytics queries. Defaults to new instance.
        """
        self._analytics_db = analytics_db
        self._analytics_repo = analytics_repo or AnalyticsRepository()
        self._llm_client = llm_client
        self._chatbot: AnalyticsChatbot | None = None

    @property
    def chatbot(self) -> AnalyticsChatbot:
        """Get or create the AnalyticsChatbot instance."""
        if self._chatbot is None:
            self._chatbot = AnalyticsChatbot(
                db=self._analytics_db,
                repository=self._analytics_repo,
                llm_client=self._llm_client,
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
