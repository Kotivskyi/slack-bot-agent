"""Slack webhook endpoint tests."""

import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


def generate_slack_signature(body: str, timestamp: str, signing_secret: str) -> str:
    """Generate a valid Slack request signature."""
    sig_basestring = f"v0:{timestamp}:{body}"
    signature = hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"v0={signature}"


@pytest.fixture
def slack_signing_secret() -> str:
    """Test signing secret."""
    return "test-signing-secret"


@pytest.fixture
def slack_timestamp() -> str:
    """Current timestamp for Slack requests."""
    return str(int(time.time()))


@pytest.mark.anyio
async def test_url_verification(
    client: AsyncClient, slack_signing_secret: str, slack_timestamp: str
):
    """Test Slack URL verification challenge."""
    body = json.dumps({"type": "url_verification", "challenge": "test-challenge-123"})
    signature = generate_slack_signature(body, slack_timestamp, slack_signing_secret)

    with patch("app.services.slack.settings") as mock_settings:
        mock_settings.SLACK_BOT_TOKEN = "xoxb-test"
        mock_settings.SLACK_SIGNING_SECRET = slack_signing_secret

        # Need to reload the service to pick up mocked settings
        with patch("app.services.slack.slack_service.signing_secret", slack_signing_secret):
            response = await client.post(
                "/slack/events",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Slack-Request-Timestamp": slack_timestamp,
                    "X-Slack-Signature": signature,
                },
            )

    assert response.status_code == 200
    assert response.json() == {"challenge": "test-challenge-123"}


@pytest.mark.anyio
async def test_invalid_signature_rejected(client: AsyncClient, slack_timestamp: str):
    """Test that invalid signatures are rejected."""
    body = json.dumps({"type": "url_verification", "challenge": "test"})

    response = await client.post(
        "/slack/events",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": slack_timestamp,
            "X-Slack-Signature": "v0=invalid-signature",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid request signature"


@pytest.mark.anyio
async def test_old_timestamp_rejected(client: AsyncClient, slack_signing_secret: str):
    """Test that requests with old timestamps are rejected."""
    old_timestamp = str(int(time.time()) - 600)  # 10 minutes ago
    body = json.dumps({"type": "url_verification", "challenge": "test"})
    signature = generate_slack_signature(body, old_timestamp, slack_signing_secret)

    with patch("app.services.slack.slack_service.signing_secret", slack_signing_secret):
        response = await client.post(
            "/slack/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": old_timestamp,
                "X-Slack-Signature": signature,
            },
        )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_direct_message_triggers_response(
    client: AsyncClient, slack_signing_secret: str, slack_timestamp: str
):
    """Test that direct messages trigger analytics response."""
    body = json.dumps(
        {
            "type": "event_callback",
            "event": {
                "type": "message",
                "user": "U123456",
                "text": "Hello bot!",
                "channel": "D123456",
                "channel_type": "im",
                "ts": "1234567890.123456",
            },
        }
    )
    signature = generate_slack_signature(body, slack_timestamp, slack_signing_secret)

    with (
        patch("app.services.slack.slack_service.signing_secret", slack_signing_secret),
        patch(
            "app.services.slack.slack_service.generate_analytics_response", new_callable=AsyncMock
        ) as mock_generate,
        patch("app.services.slack.slack_service.send_message", new_callable=AsyncMock) as mock_send,
    ):
        mock_generate.return_value = {
            "text": "AI response to: Hello bot!",
            "blocks": None,
            "intent": "off_topic",
        }
        mock_send.return_value = {"ok": True}

        response = await client.post(
            "/slack/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": slack_timestamp,
                "X-Slack-Signature": signature,
            },
        )

        assert response.status_code == 200
        mock_generate.assert_called_once_with(
            message="Hello bot!",
            user_id="U123456",
            channel_id="D123456",
            thread_ts="1234567890.123456",
        )
        mock_send.assert_called_once_with(
            channel="D123456",
            text="AI response to: Hello bot!",
            thread_ts="1234567890.123456",
            blocks=None,
        )


@pytest.mark.anyio
async def test_channel_message_ignored(
    client: AsyncClient, slack_signing_secret: str, slack_timestamp: str
):
    """Test that regular channel messages (not mentions) are ignored."""
    body = json.dumps(
        {
            "type": "event_callback",
            "event": {
                "type": "message",
                "user": "U123456",
                "text": "Hello everyone!",
                "channel": "C123456",
                "channel_type": "channel",
                "ts": "1234567890.123456",
            },
        }
    )
    signature = generate_slack_signature(body, slack_timestamp, slack_signing_secret)

    with (
        patch("app.services.slack.slack_service.signing_secret", slack_signing_secret),
        patch("app.services.slack.slack_service.send_message", new_callable=AsyncMock) as mock_send,
    ):
        response = await client.post(
            "/slack/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": slack_timestamp,
                "X-Slack-Signature": signature,
            },
        )

        assert response.status_code == 200
        mock_send.assert_not_called()


@pytest.mark.anyio
async def test_bot_message_ignored(
    client: AsyncClient, slack_signing_secret: str, slack_timestamp: str
):
    """Test that bot messages are ignored to prevent loops."""
    body = json.dumps(
        {
            "type": "event_callback",
            "event": {
                "type": "message",
                "bot_id": "B123456",
                "text": "I am a bot",
                "channel": "C123456",
                "ts": "1234567890.123456",
            },
        }
    )
    signature = generate_slack_signature(body, slack_timestamp, slack_signing_secret)

    with (
        patch("app.services.slack.slack_service.signing_secret", slack_signing_secret),
        patch("app.services.slack.slack_service.send_message", new_callable=AsyncMock) as mock_send,
    ):
        response = await client.post(
            "/slack/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": slack_timestamp,
                "X-Slack-Signature": signature,
            },
        )

        assert response.status_code == 200
        mock_send.assert_not_called()


@pytest.mark.anyio
async def test_app_mention_event(
    client: AsyncClient, slack_signing_secret: str, slack_timestamp: str
):
    """Test that app_mention events are handled."""
    body = json.dumps(
        {
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "user": "U123456",
                "text": "<@U987654> help me",
                "channel": "C123456",
                "ts": "1234567890.123456",
            },
        }
    )
    signature = generate_slack_signature(body, slack_timestamp, slack_signing_secret)

    with (
        patch("app.services.slack.slack_service.signing_secret", slack_signing_secret),
        patch(
            "app.services.slack.slack_service.generate_analytics_response", new_callable=AsyncMock
        ) as mock_generate,
        patch("app.services.slack.slack_service.send_message", new_callable=AsyncMock) as mock_send,
    ):
        mock_generate.return_value = {
            "text": "AI response",
            "blocks": None,
            "intent": "off_topic",
        }
        mock_send.return_value = {"ok": True}

        response = await client.post(
            "/slack/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": slack_timestamp,
                "X-Slack-Signature": signature,
            },
        )

        assert response.status_code == 200
        mock_generate.assert_called_once_with(
            message="<@U987654> help me",
            user_id="U123456",
            channel_id="C123456",
            thread_ts="1234567890.123456",
        )
        mock_send.assert_called_once()
