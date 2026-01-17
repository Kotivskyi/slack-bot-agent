"""Slack webhook routes."""

import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, Response

from app.schemas.slack import SlackEventWrapper
from app.services.slack import slack_service

logger = logging.getLogger(__name__)

router = APIRouter()


async def process_slack_message(channel: str, text: str, user: str, thread_ts: str | None) -> None:
    """Process a Slack message in the background.

    Args:
        channel: Channel ID to respond to.
        text: Message text from user.
        user: User ID who sent the message.
        thread_ts: Thread timestamp for replies.
    """
    logger.info(f"Processing message from user {user}: {text[:50]}...")

    try:
        # Generate AI response
        ai_response = await slack_service.generate_ai_response(
            message=text,
            user_id=user,
            thread_ts=thread_ts,
        )

        # Send response back to Slack
        await slack_service.send_message(
            channel=channel,
            text=ai_response,
            thread_ts=thread_ts,
        )
    except Exception:
        logger.exception(f"Error processing message from user {user}")


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
            # Process message in background to respond quickly to Slack
            background_tasks.add_task(
                process_slack_message,
                channel=event.channel,
                text=event.text,
                user=event.user,
                thread_ts=event.ts,
            )

    # Always return 200 immediately to acknowledge receipt
    return Response(status_code=200)
