"""Slack webhook routes."""

import json
import logging
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, Response

from app.api.deps import SlackServiceDep
from app.schemas.slack import SlackEventWrapper

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/events", response_model=None)
async def slack_events(
    request: Request,
    background_tasks: BackgroundTasks,
    slack_service: SlackServiceDep,
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
    body = await request.body()

    if not slack_service.verify_request(body, x_slack_request_timestamp, x_slack_signature):
        logger.warning("Invalid Slack request signature")
        raise HTTPException(status_code=401, detail="Invalid request signature")

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
                slack_service.process_message,
                channel=event.channel,
                text=event.text,
                user_id=event.user,
                thread_ts=thread_ts,
            )

    # Always return 200 immediately to acknowledge receipt
    return Response(status_code=200)


@router.post("/interactions", response_model=None)
async def slack_interactions(
    request: Request,
    background_tasks: BackgroundTasks,
    slack_service: SlackServiceDep,
    x_slack_request_timestamp: str = Header(..., alias="X-Slack-Request-Timestamp"),
    x_slack_signature: str = Header(..., alias="X-Slack-Signature"),
) -> Response:
    """Handle Slack interactive components (button clicks, etc.).

    Slack sends interactive component payloads as form-encoded data
    with a 'payload' field containing JSON.

    This endpoint handles:
    - Button clicks (export_csv, show_sql)
    """
    body = await request.body()

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
                    slack_service.process_button_click,
                    action_id=action_id,
                    value=value,
                    user_id=user.get("id", ""),
                    channel_id=channel.get("id", ""),
                    thread_ts=message.get("ts", ""),
                )

    # Always acknowledge immediately
    return Response(status_code=200)
