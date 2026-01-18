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

# Slack API limits
SLACK_MAX_TEXT_LENGTH = 40000  # Max chars for text field
SLACK_MAX_BLOCK_TEXT_LENGTH = 3000  # Max chars for section/context block text
SLACK_MAX_BLOCKS = 50  # Max blocks per message

# Truncation message
TRUNCATION_NOTICE = "\n\n_...table truncated. Click *Export CSV* for complete data._"


def _truncate_block_text(text: str, max_length: int = SLACK_MAX_BLOCK_TEXT_LENGTH) -> str:
    """Truncate block text to fit Slack limits.

    Intelligently truncates text, preferring to cut at line boundaries
    for code blocks (tables). Adds truncation notice.

    Args:
        text: The text to truncate.
        max_length: Maximum allowed length.

    Returns:
        Truncated text with notice if truncation occurred.
    """
    if len(text) <= max_length:
        return text

    # Reserve space for truncation notice
    available_length = max_length - len(TRUNCATION_NOTICE)

    # Check if this is a code block (table)
    if text.startswith("```"):
        # Find line boundaries to truncate cleanly
        lines = text.split("\n")
        truncated_lines = []
        current_length = 0

        for line in lines:
            # +1 for newline
            if current_length + len(line) + 1 > available_length - 10:  # Buffer for closing ```
                break
            truncated_lines.append(line)
            current_length += len(line) + 1

        # Ensure we close the code block
        truncated_text = "\n".join(truncated_lines)
        if not truncated_text.endswith("```"):
            truncated_text += "\n```"

        return truncated_text + TRUNCATION_NOTICE

    # For regular text, truncate at word boundary
    truncated = text[:available_length]
    last_space = truncated.rfind(" ")
    if last_space > available_length * 0.8:  # Only use word boundary if reasonable
        truncated = truncated[:last_space]

    return truncated + TRUNCATION_NOTICE


def _prepare_blocks_for_slack(blocks: list[dict] | None) -> list[dict] | None:
    """Prepare blocks for Slack by truncating oversized content.

    Args:
        blocks: List of Slack Block Kit blocks.

    Returns:
        Validated and truncated blocks, or None if input was None.
    """
    if not blocks:
        return blocks

    # Limit number of blocks
    if len(blocks) > SLACK_MAX_BLOCKS:
        logger.warning(f"Truncating blocks from {len(blocks)} to {SLACK_MAX_BLOCKS}")
        blocks = blocks[:SLACK_MAX_BLOCKS]

    # Process each block
    for block in blocks:
        block_type = block.get("type")

        # Handle section blocks
        if block_type == "section" and "text" in block:
            text_obj = block["text"]
            if isinstance(text_obj, dict) and "text" in text_obj:
                original_text = text_obj["text"]
                if len(original_text) > SLACK_MAX_BLOCK_TEXT_LENGTH:
                    logger.warning(
                        f"Truncating section block from {len(original_text)} to {SLACK_MAX_BLOCK_TEXT_LENGTH} chars"
                    )
                    text_obj["text"] = _truncate_block_text(original_text)

        # Handle context blocks
        elif block_type == "context" and "elements" in block:
            for element in block["elements"]:
                if isinstance(element, dict) and "text" in element:
                    original_text = element["text"]
                    if len(original_text) > SLACK_MAX_BLOCK_TEXT_LENGTH:
                        logger.warning(
                            f"Truncating context block from {len(original_text)} to {SLACK_MAX_BLOCK_TEXT_LENGTH} chars"
                        )
                        element["text"] = _truncate_block_text(original_text)

    return blocks


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

        Automatically truncates oversized content to fit Slack API limits.

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
            # Truncate text if too long
            if len(text) > SLACK_MAX_TEXT_LENGTH:
                logger.warning(
                    f"Truncating message text from {len(text)} to {SLACK_MAX_TEXT_LENGTH} chars"
                )
                text = text[: SLACK_MAX_TEXT_LENGTH - 3] + "..."

            # Validate and truncate blocks
            validated_blocks = _prepare_blocks_for_slack(blocks)

            kwargs: dict[str, Any] = {
                "channel": channel,
                "text": text,
            }
            if thread_ts:
                kwargs["thread_ts"] = thread_ts
            if validated_blocks:
                kwargs["blocks"] = validated_blocks

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
                )

            # 3. Handle text-based export if intent is export_csv but no results
            if response.intent == "export_csv" and not response.csv_content:
                export_response = await self.handle_text_export(
                    thread_id=thread_id,
                    user_id=user_id,
                    channel_id=channel_id,
                )
                # Save turn with export intent (no new SQL generated)
                async with get_db_context() as db:
                    await repo.add_turn(
                        db,
                        thread_id=thread_id,
                        user_message=message,
                        bot_response=export_response.get("text", ""),
                        intent="export_csv",
                        sql_query=None,
                        action_id=None,
                    )
                return export_response

            # 4. Handle text-based show_sql if intent is show_sql but no SQL in response
            if response.intent == "show_sql" and not response.generated_sql:
                show_sql_response = await self.handle_text_show_sql(
                    thread_id=thread_id,
                )
                # Save turn with show_sql intent
                async with get_db_context() as db:
                    await repo.add_turn(
                        db,
                        thread_id=thread_id,
                        user_message=message,
                        bot_response=show_sql_response.get("text", ""),
                        intent="show_sql",
                        sql_query=None,
                        action_id=None,
                    )
                return show_sql_response

            # 5. Save new turn to DB
            async with get_db_context() as db:
                await repo.add_turn(
                    db,
                    thread_id=thread_id,
                    user_message=message,
                    bot_response=response.text,
                    intent=response.intent or "unknown",
                    sql_query=response.generated_sql,
                    action_id=response.action_id,
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

    async def handle_text_export(
        self,
        thread_id: str,
        user_id: str,
        channel_id: str,
    ) -> dict[str, Any]:
        """Handle text-based CSV export request.

        Looks up the most recent SQL query from conversation history
        and re-executes it to generate CSV.

        Args:
            thread_id: Thread identifier for the conversation.
            user_id: The Slack user ID.
            channel_id: The Slack channel ID.

        Returns:
            Dict with text, blocks, csv_content, csv_filename.
        """
        import csv
        import io

        from app.db.session import get_analytics_db_context, get_db_context
        from app.repositories import AnalyticsRepository, ConversationRepository

        try:
            # Look up the most recent SQL query for this thread
            async with get_db_context() as db:
                repo = ConversationRepository()
                sql_query = await repo.get_most_recent_sql(db, thread_id)

            if not sql_query:
                return {
                    "text": "No recent query to export. Please ask a question first!",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "No recent query to export. Please ask a question first!",
                            },
                        }
                    ],
                    "intent": "export_csv",
                }

            # Re-execute the SQL to get results
            async with get_analytics_db_context() as analytics_db:
                analytics_repo = AnalyticsRepository()
                try:
                    rows, _columns = await analytics_repo.execute_query(analytics_db, sql_query)
                except Exception as e:
                    logger.warning(f"Failed to re-execute SQL for text export: {e}")
                    return {
                        "text": f"Failed to execute query: {e!s}",
                        "blocks": None,
                        "intent": "export_csv",
                    }

            if not rows:
                return {
                    "text": "The query returned no data to export.",
                    "blocks": None,
                    "intent": "export_csv",
                }

            # Generate CSV content
            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
            csv_content = csv_buffer.getvalue()

            filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

            response_text = f"*CSV Export Complete*\n_{len(rows)} rows exported_"
            return {
                "text": response_text,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": response_text,
                        },
                    }
                ],
                "intent": "export_csv",
                "csv_content": csv_content,
                "csv_filename": filename,
                "csv_title": "Export",
            }

        except Exception:
            logger.exception(f"Error handling text export for user {user_id}")
            return {
                "text": "Sorry, I encountered an error. Please try again.",
                "blocks": None,
                "intent": "export_csv",
            }

    async def handle_text_show_sql(
        self,
        thread_id: str,
    ) -> dict[str, Any]:
        """Handle text-based show SQL request.

        Looks up the most recent SQL query from conversation history.

        Args:
            thread_id: Thread identifier for the conversation.

        Returns:
            Dict with text, blocks, intent.
        """
        from app.db.session import get_db_context
        from app.repositories import ConversationRepository

        try:
            # Look up the most recent SQL query for this thread
            async with get_db_context() as db:
                repo = ConversationRepository()
                sql_query = await repo.get_most_recent_sql(db, thread_id)

            if not sql_query:
                return {
                    "text": "No SQL queries in history. Please ask a question first!",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "No SQL queries in history. Please ask a question first!",
                            },
                        }
                    ],
                    "intent": "show_sql",
                }

            response_text = "*SQL Query*"
            return {
                "text": response_text,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": response_text,
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"```sql\n{sql_query}\n```",
                        },
                    },
                ],
                "intent": "show_sql",
            }

        except Exception:
            logger.exception(f"Error handling text show_sql for thread {thread_id}")
            return {
                "text": "Sorry, I encountered an error. Please try again.",
                "blocks": None,
                "intent": "show_sql",
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

        Retrieves SQL and results from DB, handles directly without LLM calls.

        Args:
            action_id: The action ID (e.g., "export_csv", "show_sql").
            value: The button value (action_id UUID for the specific turn).
            user_id: The Slack user ID.
            channel_id: The Slack channel ID.
            thread_ts: Thread timestamp for the message.

        Returns:
            Dict with response text and blocks.
        """
        import csv
        import io

        from app.db.session import get_analytics_db_context, get_db_context
        from app.repositories import AnalyticsRepository, ConversationRepository

        try:
            # 1. Look up the specific conversation turn by action_id (the button value)
            async with get_db_context() as db:
                repo = ConversationRepository()
                turn = await repo.get_turn_by_action_id(db, value)

            if not turn:
                return {
                    "text": "Could not find the referenced query. It may have expired.",
                    "blocks": None,
                }

            sql_query = turn.sql_query
            if not sql_query:
                return {
                    "text": "No SQL query associated with this response.",
                    "blocks": None,
                }

            # 2. Handle action based on type
            if action_id == "show_sql":
                # Just return the SQL - no execution needed
                response_text = "*SQL Query*"
                return {
                    "text": response_text,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": response_text,
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"```sql\n{sql_query}\n```",
                            },
                        },
                    ],
                }

            elif action_id == "export_csv":
                # Re-execute the SQL to get fresh results
                async with get_analytics_db_context() as analytics_db:
                    analytics_repo = AnalyticsRepository()
                    try:
                        rows, _columns = await analytics_repo.execute_query(analytics_db, sql_query)
                    except Exception as e:
                        logger.warning(f"Failed to re-execute SQL for CSV export: {e}")
                        return {
                            "text": f"Failed to execute query: {e!s}",
                            "blocks": None,
                        }

                if not rows:
                    return {
                        "text": "The query returned no data to export.",
                        "blocks": None,
                    }

                # Generate CSV content
                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
                csv_content = csv_buffer.getvalue()

                filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

                response_text = f"*CSV Export Complete*\n_{len(rows)} rows exported_"
                return {
                    "text": response_text,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": response_text,
                            },
                        }
                    ],
                    "csv_content": csv_content,
                    "csv_filename": filename,
                    "csv_title": "Export",
                }

            else:
                return {
                    "text": f"Unknown action: {action_id}",
                    "blocks": None,
                }

        except Exception:
            logger.exception(f"Error handling button action {action_id}")
            return {
                "text": "Sorry, I encountered an error. Please try again.",
                "blocks": None,
            }

    async def process_message(
        self,
        channel: str,
        text: str,
        user_id: str,
        thread_ts: str | None,
    ) -> None:
        """Process a Slack message and send response.

        Orchestrates the full flow: analytics response → file upload (if CSV) → send message.
        Designed to be run as a background task.

        Args:
            channel: Channel ID to respond to.
            text: Message text from user.
            user_id: User ID who sent the message.
            thread_ts: Thread timestamp for replies.
        """
        logger.info(f"Processing analytics message from user {user_id}: {text[:50]}...")

        try:
            response = await self.generate_analytics_response(
                message=text,
                user_id=user_id,
                channel_id=channel,
                thread_ts=thread_ts,
            )

            # Handle CSV export if present
            if response.get("csv_content") and response.get("csv_filename"):
                await self.upload_file(
                    channel=channel,
                    content=response["csv_content"],
                    filename=response["csv_filename"],
                    title=response.get("csv_title"),
                    thread_ts=thread_ts,
                )

            # Send response back to Slack
            await self.send_message(
                channel=channel,
                text=response.get("text", ""),
                thread_ts=thread_ts,
                blocks=response.get("blocks"),
            )
        except Exception:
            logger.exception(f"Error processing message from user {user_id}")
            await self._send_error_message(channel, thread_ts)

    async def process_button_click(
        self,
        action_id: str,
        value: str,
        user_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> None:
        """Process a button click and send response.

        Orchestrates: button action handling → file upload (if CSV) → send message.
        Designed to be run as a background task.

        Args:
            action_id: The action ID (e.g., "export_csv", "show_sql").
            value: The button value (action_id UUID for the specific turn).
            user_id: The Slack user ID.
            channel_id: The Slack channel ID.
            thread_ts: Thread timestamp for the message.
        """
        logger.info(f"Processing button action {action_id} from user {user_id}")

        try:
            response = await self.handle_button_action(
                action_id=action_id,
                value=value,
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
            )

            # Handle CSV export if present
            if response.get("csv_content") and response.get("csv_filename"):
                await self.upload_file(
                    channel=channel_id,
                    content=response["csv_content"],
                    filename=response["csv_filename"],
                    title=response.get("csv_title"),
                    thread_ts=thread_ts,
                )

            # Send response back to Slack
            await self.send_message(
                channel=channel_id,
                text=response.get("text", ""),
                thread_ts=thread_ts,
                blocks=response.get("blocks"),
            )
        except Exception:
            logger.exception(f"Error processing button action {action_id}")

    async def _send_error_message(self, channel: str, thread_ts: str | None) -> None:
        """Send error message to user.

        Args:
            channel: Channel ID to send error to.
            thread_ts: Thread timestamp for replies.
        """
        try:
            await self.send_message(
                channel=channel,
                text="Sorry, I encountered an error. Please try again.",
                thread_ts=thread_ts,
            )
        except Exception:
            logger.exception("Failed to send error message")


# Service instance
slack_service = SlackService()
