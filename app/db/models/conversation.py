"""Conversation turn database model for persistent chat history."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.models.base import Base


class ConversationTurn(Base):
    """Conversation turn model for storing chat history.

    Each turn represents one user message and bot response pair,
    along with metadata for context retrieval.
    """

    __tablename__ = "conversation_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    bot_response: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(50), nullable=False)
    sql_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_conversation_turns_thread_recent", "thread_id", created_at.desc()),
    )

    def __repr__(self) -> str:
        return f"<ConversationTurn(thread_id={self.thread_id}, intent={self.intent})>"
