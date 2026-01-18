"""Slack webhook schemas."""

from typing import Any

from pydantic import BaseModel, Field


class SlackEvent(BaseModel):
    """Slack event payload."""

    type: str
    user: str | None = None
    text: str | None = None
    channel: str | None = None
    ts: str | None = None
    thread_ts: str | None = None  # Thread root timestamp (for replies in a thread)
    bot_id: str | None = None
    channel_type: str | None = None


class SlackEventWrapper(BaseModel):
    """Incoming Slack event wrapper."""

    token: str | None = None
    team_id: str | None = None
    type: str
    challenge: str | None = None
    event: SlackEvent | None = None
    event_id: str | None = None
    event_time: int | None = None
    authorizations: list[dict[str, Any]] | None = None


class SlackMessageResponse(BaseModel):
    """Outgoing Slack message response."""

    channel: str = Field(..., description="Channel ID to send message to")
    text: str = Field(..., description="Message text")
    thread_ts: str | None = Field(default=None, description="Thread timestamp for replies")
