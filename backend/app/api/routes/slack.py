"""Slack webhook routes."""

import logging

from fastapi import APIRouter, Header, HTTPException, Request, Response

from app.schemas.slack import SlackEventWrapper
from app.services.slack import slack_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/events", response_model=None)
async def slack_events(
    request: Request,
    x_slack_request_timestamp: str = Header(..., alias="X-Slack-Request-Timestamp"),
    x_slack_signature: str = Header(..., alias="X-Slack-Signature"),
) -> Response | dict:
    """Handle incoming Slack events.

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

    # Handle URL verification challenge
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
            logger.info(f"Processing message from user {event.user}: {event.text[:50]}...")

            # Generate AI response
            ai_response = await slack_service.generate_ai_response(
                message=event.text,
                user_id=event.user,
            )

            # Send response back to Slack
            await slack_service.send_message(
                channel=event.channel,
                text=ai_response,
                thread_ts=event.ts,
            )

    # Always return 200 to acknowledge receipt
    return Response(status_code=200)
