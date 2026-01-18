"""Slack webhook routes."""

import json
import logging
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, Response

from app.schemas.slack import SlackEventWrapper
from app.services.slack import slack_service

logger = logging.getLogger(__name__)

router = APIRouter()


async def process_slack_message(channel: str, text: str, user: str, thread_ts: str | None) -> None:
    """Process a Slack message in the background using analytics chatbot.

    Args:
        channel: Channel ID to respond to.
        text: Message text from user.
        user: User ID who sent the message.
        thread_ts: Thread timestamp for replies.
    """
    logger.info(f"Processing analytics message from user {user}: {text[:50]}...")

    try:
        # Generate analytics response
        response = await slack_service.generate_analytics_response(
            message=text,
            user_id=user,
            channel_id=channel,
            thread_ts=thread_ts,
        )

        # Handle CSV export if present
        if response.get("csv_content") and response.get("csv_filename"):
            await slack_service.upload_file(
                channel=channel,
                content=response["csv_content"],
                filename=response["csv_filename"],
                title=response.get("csv_title"),
                thread_ts=thread_ts,
            )

        # Send response back to Slack
        await slack_service.send_message(
            channel=channel,
            text=response.get("text", ""),
            thread_ts=thread_ts,
            blocks=response.get("blocks"),
        )
    except Exception:
        logger.exception(f"Error processing message from user {user}")
        # Send error message
        try:
            await slack_service.send_message(
                channel=channel,
                text="Sorry, I encountered an error. Please try again.",
                thread_ts=thread_ts,
            )
        except Exception:
            logger.exception("Failed to send error message")


async def process_button_action(
    action_id: str,
    value: str,
    user_id: str,
    channel_id: str,
    thread_ts: str,
) -> None:
    """Process a button action in the background.

    Args:
        action_id: The action ID (e.g., "export_csv", "show_sql").
        value: The button value (query_id).
        user_id: The Slack user ID.
        channel_id: The Slack channel ID.
        thread_ts: Thread timestamp for the message.
    """
    logger.info(f"Processing button action {action_id} from user {user_id}")

    try:
        response = await slack_service.handle_button_action(
            action_id=action_id,
            value=value,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )

        # Handle CSV export if present
        if response.get("csv_content") and response.get("csv_filename"):
            await slack_service.upload_file(
                channel=channel_id,
                content=response["csv_content"],
                filename=response["csv_filename"],
                title=response.get("csv_title"),
                thread_ts=thread_ts,
            )

        # Send response back to Slack
        await slack_service.send_message(
            channel=channel_id,
            text=response.get("text", ""),
            thread_ts=thread_ts,
            blocks=response.get("blocks"),
        )
    except Exception:
        logger.exception(f"Error processing button action {action_id}")


@router.post("/events", response_model=None)
async def slack_events(
    request: Request,
    background_tasks: BackgroundTasks,
    x_slack_request_timestamp: str = Header(..., alias="X-Slack-Request-Timestamp"),
    x_slack_signature: str = Header(..., alias="X-Slack-Signature"),
) -> Response | dict:
    """Handle incoming Slack events.

    Immediately acknowledges the request and processes messages in the background.
    This prevents Slack from retrying (Slack expects response within 3 seconds).

    This endpoint handles:
    - URL verification challenges from Slack
    - Message events (app_mention, message)
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify request signature
    if not slack_service.verify_request(body, x_slack_request_timestamp, x_slack_signature):
        logger.warning("Invalid Slack request signature")
        raise HTTPException(status_code=401, detail="Invalid request signature")

    # Parse event
    event_wrapper = SlackEventWrapper.model_validate_json(body)

    # Handle URL verification challenge (must respond synchronously)
    if event_wrapper.type == "url_verification":
        return {"challenge": event_wrapper.challenge}

    # Handle event callbacks
    if event_wrapper.type == "event_callback" and event_wrapper.event:
        event = event_wrapper.event

        # Skip bot messages to prevent loops
        if event.bot_id:
            logger.debug("Skipping bot message")
            return Response(status_code=200)

        # Handle message events
        # - app_mention: when bot is @mentioned in channels
        # - message with channel_type "im": direct messages to the bot
        # Skip regular channel messages to avoid double-responding (Slack sends both
        # app_mention and message events when bot is mentioned)
        is_direct_message = event.type == "message" and event.channel_type == "im"
        is_mention = event.type == "app_mention"

        if (is_direct_message or is_mention) and event.channel and event.text and event.user:
            # Use thread_ts if this is a reply in a thread, otherwise use ts
            # This ensures all messages in a thread share the same thread_id
            thread_ts = event.thread_ts or event.ts
            # Process message in background to respond quickly to Slack
            background_tasks.add_task(
                process_slack_message,
                channel=event.channel,
                text=event.text,
                user=event.user,
                thread_ts=thread_ts,
            )

    # Always return 200 immediately to acknowledge receipt
    return Response(status_code=200)


@router.post("/interactions", response_model=None)
async def slack_interactions(
    request: Request,
    background_tasks: BackgroundTasks,
    x_slack_request_timestamp: str = Header(..., alias="X-Slack-Request-Timestamp"),
    x_slack_signature: str = Header(..., alias="X-Slack-Signature"),
) -> Response:
    """Handle Slack interactive components (button clicks, etc.).

    Slack sends interactive component payloads as form-encoded data
    with a 'payload' field containing JSON.

    This endpoint handles:
    - Button clicks (export_csv, show_sql)
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify request signature
    if not slack_service.verify_request(body, x_slack_request_timestamp, x_slack_signature):
        logger.warning("Invalid Slack request signature for interaction")
        raise HTTPException(status_code=401, detail="Invalid request signature")

    # Parse form-encoded payload
    try:
        form_data = parse_qs(body.decode("utf-8"))
        payload_str = form_data.get("payload", [""])[0]
        payload = json.loads(payload_str)
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse interaction payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload format") from e

    # Handle block actions (button clicks)
    if payload.get("type") == "block_actions":
        actions = payload.get("actions", [])
        user = payload.get("user", {})
        channel = payload.get("channel", {})
        message = payload.get("message", {})

        for action in actions:
            action_id = action.get("action_id")
            value = action.get("value", "")

            if action_id in ("export_csv", "show_sql"):
                # Process in background
                background_tasks.add_task(
                    process_button_action,
                    action_id=action_id,
                    value=value,
                    user_id=user.get("id", ""),
                    channel_id=channel.get("id", ""),
                    thread_ts=message.get("ts", ""),
                )

    # Always acknowledge immediately
    return Response(status_code=200)
