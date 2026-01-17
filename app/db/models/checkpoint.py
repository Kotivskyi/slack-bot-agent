"""Agent checkpoint database model for LangGraph state persistence."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class AgentCheckpoint(Base):
    """Agent checkpoint model for persisting LangGraph graph state.

    Stores checkpoints for conversation continuity across sessions.
    Each checkpoint contains serialized graph state that can be
    restored when resuming a conversation.
    """

    __tablename__ = "agent_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    checkpoint_id: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checkpoint_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<AgentCheckpoint(thread_id={self.thread_id}, checkpoint_id={self.checkpoint_id})>"
