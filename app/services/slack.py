"""Slack service for handling Slack API interactions."""

import hashlib
import hmac
import logging
import time
from datetime import datetime
from typing import Any

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from app.core.config import settings

logger = logging.getLogger(__name__)


class SlackService:
    """Service for Slack-related operations."""

    def __init__(self) -> None:
        self.client = AsyncWebClient(token=settings.SLACK_BOT_TOKEN)
        self.signing_secret = settings.SLACK_SIGNING_SECRET

    def verify_request(
        self,
        body: bytes,
        timestamp: str,
        signature: str,
    ) -> bool:
        """Verify Slack request signature using HMAC-SHA256.

        Args:
            body: Raw request body bytes.
            timestamp: X-Slack-Request-Timestamp header.
            signature: X-Slack-Signature header.

        Returns:
            True if signature is valid, False otherwise.
        """
        if not self.signing_secret:
            logger.warning("No signing secret configured")
            return False

        # Check timestamp is within 5 minutes to prevent replay attacks
        current_time = int(time.time())
        if abs(current_time - int(timestamp)) > 60 * 5:
            logger.warning(f"Timestamp too old: {timestamp} vs {current_time}")
            return False

        # Compute expected signature
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected_signature = (
            "v0="
            + hmac.new(
                self.signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256,
            ).hexdigest()
        )

        is_valid = hmac.compare_digest(expected_signature, signature)
        if not is_valid:
            logger.warning(
                f"Signature mismatch: expected={expected_signature[:20]}... got={signature[:20]}..."
            )
        return is_valid

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        blocks: list[dict] | None = None,
    ) -> dict:
        """Send a message to a Slack channel.

        Args:
            channel: Channel ID to send message to.
            text: Message text (fallback for notifications).
            thread_ts: Optional thread timestamp for replies.
            blocks: Optional Block Kit blocks for rich formatting.

        Returns:
            Slack API response dict.

        Raises:
            SlackApiError: If the API call fails.
        """
        try:
            kwargs: dict[str, Any] = {
                "channel": channel,
                "text": text,
            }
            if thread_ts:
                kwargs["thread_ts"] = thread_ts
            if blocks:
                kwargs["blocks"] = blocks

            response = await self.client.chat_postMessage(**kwargs)
            return response.data
        except SlackApiError as e:
            raise e

    async def upload_file(
        self,
        channel: str,
        content: str,
        filename: str,
        title: str | None = None,
        thread_ts: str | None = None,
    ) -> dict:
        """Upload a file to a Slack channel.

        Args:
            channel: Channel ID to upload to.
            content: File content as string.
            filename: Name of the file.
            title: Optional title for the file.
            thread_ts: Optional thread timestamp for replies.

        Returns:
            Slack API response dict.

        Raises:
            SlackApiError: If the API call fails.
        """
        try:
            response = await self.client.files_upload_v2(
                channel=channel,
                content=content,
                filename=filename,
                title=title,
                thread_ts=thread_ts,
            )
            return response.data
        except SlackApiError as e:
            logger.error(f"File upload failed: {e}")
            raise e

    async def generate_ai_response(
        self,
        message: str,
        user_id: str,
        thread_ts: str | None = None,
    ) -> str:
        """Generate AI response using LangGraph agent.

        Args:
            message: The user's message.
            user_id: The Slack user ID.
            thread_ts: Optional thread timestamp for conversation continuity.

        Returns:
            Generated AI response.
        """
        from app.agents import AgentContext
        from app.services.agent import AgentService

        # Thread ID for conversation continuity
        thread_id = f"slack_thread_{thread_ts}" if thread_ts else f"slack_user_{user_id}"

        context: AgentContext = {
            "user_id": user_id,
            "metadata": {"source": "slack"},
        }

        try:
            agent_service = AgentService()
            output, _ = await agent_service.run(
                user_input=message,
                thread_id=thread_id,
                history=[],
                context=context,
            )
            return output or "I couldn't generate a response."
        except Exception:
            logger.exception(f"Error generating AI response for user {user_id}")
            return "Sorry, I encountered an error. Please try again."

    async def generate_analytics_response(
        self,
        message: str,
        user_id: str,
        channel_id: str,
        thread_ts: str | None = None,
    ) -> dict[str, Any]:
        """Generate analytics chatbot response.

        Args:
            message: The user's message.
            user_id: The Slack user ID.
            channel_id: The Slack channel ID.
            thread_ts: Optional thread timestamp for conversation continuity.

        Returns:
            Dict with text, blocks, and any file upload info.
        """
        from app.db.session import get_analytics_db_context, get_db_context
        from app.repositories import ConversationRepository, turns_to_history
        from app.services.agent import AnalyticsAgentService

        # Thread ID for conversation continuity
        thread_id = f"slack_thread_{thread_ts}" if thread_ts else f"slack_user_{user_id}"

        try:
            # 1. Load history from DB
            async with get_db_context() as db:
                repo = ConversationRepository()
                turns = await repo.get_recent_turns(db, thread_id, limit=10)
                conversation_history = turns_to_history(turns)

            # 2. Run analytics agent
            async with get_analytics_db_context() as analytics_db:
                analytics_service = AnalyticsAgentService(analytics_db=analytics_db)
                response = await analytics_service.run(
                    user_query=message,
                    thread_id=thread_id,
                    user_id=user_id,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    conversation_history=conversation_history,
                    query_cache={},  # Rebuilt per request through graph execution
                )

            # 3. Save new turn to DB
            async with get_db_context() as db:
                # Extract SQL from query_cache (most recent query)
                sql_query = None
                query_cache = response.query_cache or {}
                if query_cache:
                    # Get the most recent cache entry by timestamp
                    most_recent = max(
                        query_cache.values(), key=lambda x: x.get("timestamp", datetime.min)
                    )
                    sql_query = most_recent.get("sql")

                await repo.add_turn(
                    db,
                    thread_id=thread_id,
                    user_message=message,
                    bot_response=response.text,
                    intent=response.intent or "unknown",
                    sql_query=sql_query,
                )

            return {
                "text": response.text,
                "blocks": response.slack_blocks,
                "intent": response.intent,
                "csv_content": response.csv_content,
                "csv_filename": response.csv_filename,
                "csv_title": response.csv_title,
            }
        except Exception:
            logger.exception(f"Error generating analytics response for user {user_id}")
            return {
                "text": "Sorry, I encountered an error processing your analytics request. Please try again.",
                "blocks": None,
                "intent": "error",
            }

    async def handle_button_action(
        self,
        action_id: str,
        value: str,
        user_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> dict[str, Any]:
        """Handle button action from Slack interactive component.

        Args:
            action_id: The action ID (e.g., "export_csv", "show_sql").
            value: The button value (query_id).
            user_id: The Slack user ID.
            channel_id: The Slack channel ID.
            thread_ts: Thread timestamp for the message.

        Returns:
            Dict with response text and blocks.
        """
        from app.db.session import get_analytics_db_context, get_db_context
        from app.repositories import AnalyticsRepository, ConversationRepository, turns_to_history
        from app.services.agent import AnalyticsAgentService

        # Get the thread ID based on the original thread
        thread_id = f"slack_thread_{thread_ts}"

        # Create appropriate user query based on action
        if action_id == "export_csv":
            user_query = "export csv"
        elif action_id == "show_sql":
            user_query = "show sql"
        else:
            return {
                "text": f"Unknown action: {action_id}",
                "blocks": None,
            }

        try:
            # 1. Load history from DB
            async with get_db_context() as db:
                repo = ConversationRepository()
                turns = await repo.get_recent_turns(db, thread_id, limit=10)
                conversation_history = turns_to_history(turns)

            # 2. Rebuild query_cache by re-executing SQL for turns that have SQL
            # This is needed because CSV export requires the actual results data
            query_cache: dict[str, Any] = {}
            async with get_analytics_db_context() as analytics_db:
                analytics_repo = AnalyticsRepository()
                for i, turn in enumerate(turns):
                    if turn.sql_query:
                        try:
                            rows, _columns = await analytics_repo.execute_query(
                                analytics_db, turn.sql_query
                            )
                            # Use index-based key to allow referencing specific queries
                            query_id = f"turn_{i}"
                            query_cache[query_id] = {
                                "sql": turn.sql_query,
                                "results": rows,
                                "timestamp": turn.created_at,
                                "natural_query": turn.user_message,
                                "assumptions": [],
                            }
                        except Exception as e:
                            logger.warning(f"Failed to re-execute SQL for turn {i}: {e}")

                # 3. Run analytics agent
                analytics_service = AnalyticsAgentService(analytics_db=analytics_db)
                response = await analytics_service.run(
                    user_query=user_query,
                    thread_id=thread_id,
                    user_id=user_id,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    conversation_history=conversation_history,
                    query_cache=query_cache,
                )

            return {
                "text": response.text,
                "blocks": response.slack_blocks,
                "csv_content": response.csv_content,
                "csv_filename": response.csv_filename,
                "csv_title": response.csv_title,
            }
        except Exception:
            logger.exception(f"Error handling button action {action_id}")
            return {
                "text": "Sorry, I encountered an error. Please try again.",
                "blocks": None,
            }


# Service instance
slack_service = SlackService()
