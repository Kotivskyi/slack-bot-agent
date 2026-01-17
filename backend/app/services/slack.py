"""Slack service for handling Slack API interactions."""

import hashlib
import hmac
import time

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from app.core.config import settings


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
        import logging

        logger = logging.getLogger(__name__)

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
            logger.warning(f"Signature mismatch: expected={expected_signature[:20]}... got={signature[:20]}...")
        return is_valid

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
    ) -> dict:
        """Send a message to a Slack channel.

        Args:
            channel: Channel ID to send message to.
            text: Message text.
            thread_ts: Optional thread timestamp for replies.

        Returns:
            Slack API response dict.

        Raises:
            SlackApiError: If the API call fails.
        """
        try:
            response = await self.client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts,
            )
            return response.data
        except SlackApiError as e:
            raise e

    async def generate_ai_response(self, message: str, user_id: str) -> str:
        """Generate AI response for a message.

        This is a mock implementation. Replace with LangGraph agent later.

        To integrate LangGraph:
            from app.agents.langgraph_assistant import get_agent
            agent = get_agent()
            output, _, _ = await agent.run(message, history=[], thread_id=user_id)
            return output

        Args:
            message: The user's message.
            user_id: The Slack user ID.

        Returns:
            Generated AI response.
        """
        return f"Mock response to: {message[:100]}"


# Service instance
slack_service = SlackService()
