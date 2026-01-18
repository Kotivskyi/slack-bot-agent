"""Repository for conversation history persistence.

Provides methods to store and retrieve conversation turns
from the database for persistent chat history.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import ConversationTurn

# Maximum length for bot_response to prevent storing huge outputs
MAX_BOT_RESPONSE_LENGTH = 500


class ConversationRepository:
    """Repository for conversation turn operations.

    Follows Pattern 1: session passed to methods (not held in __init__).
    """

    async def add_turn(
        self,
        db: AsyncSession,
        thread_id: str,
        user_message: str,
        bot_response: str,
        intent: str,
        sql_query: str | None = None,
    ) -> ConversationTurn:
        """Add a new conversation turn.

        Args:
            db: Async database session.
            thread_id: Thread identifier for the conversation.
            user_message: The user's message.
            bot_response: The bot's response (truncated to MAX_BOT_RESPONSE_LENGTH).
            intent: The classified intent of the query.
            sql_query: Optional SQL query if one was generated.

        Returns:
            The created ConversationTurn model.
        """
        # Truncate bot_response to prevent storing huge outputs
        truncated_response = bot_response[:MAX_BOT_RESPONSE_LENGTH]
        if len(bot_response) > MAX_BOT_RESPONSE_LENGTH:
            truncated_response += "..."

        turn = ConversationTurn(
            thread_id=thread_id,
            user_message=user_message,
            bot_response=truncated_response,
            intent=intent,
            sql_query=sql_query,
        )
        db.add(turn)
        await db.flush()
        await db.refresh(turn)
        return turn

    async def get_recent_turns(
        self,
        db: AsyncSession,
        thread_id: str,
        limit: int = 10,
    ) -> list[ConversationTurn]:
        """Get recent conversation turns for a thread in chronological order.

        Args:
            db: Async database session.
            thread_id: Thread identifier for the conversation.
            limit: Maximum number of turns to retrieve.

        Returns:
            List of ConversationTurn models, oldest first.
        """
        # Query for most recent turns, then reverse to get chronological order
        result = await db.execute(
            select(ConversationTurn)
            .where(ConversationTurn.thread_id == thread_id)
            .order_by(ConversationTurn.created_at.desc())
            .limit(limit)
        )
        turns = list(result.scalars().all())
        # Reverse to get oldest first (chronological order)
        turns.reverse()
        return turns

    async def get_most_recent_sql(
        self,
        db: AsyncSession,
        thread_id: str,
    ) -> str | None:
        """Get the most recent SQL query for a thread.

        Args:
            db: Async database session.
            thread_id: Thread identifier for the conversation.

        Returns:
            The most recent SQL query string, or None if not found.
        """
        result = await db.execute(
            select(ConversationTurn.sql_query)
            .where(ConversationTurn.thread_id == thread_id)
            .where(ConversationTurn.sql_query.isnot(None))
            .order_by(ConversationTurn.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row

    async def find_sql_by_keyword(
        self,
        db: AsyncSession,
        thread_id: str,
        keyword: str,
    ) -> str | None:
        """Find SQL query by keyword in user message.

        Args:
            db: Async database session.
            thread_id: Thread identifier for the conversation.
            keyword: Keyword to search for in user messages.

        Returns:
            The SQL query string if found, or None.
        """
        result = await db.execute(
            select(ConversationTurn.sql_query)
            .where(ConversationTurn.thread_id == thread_id)
            .where(ConversationTurn.sql_query.isnot(None))
            .where(ConversationTurn.user_message.ilike(f"%{keyword}%"))
            .order_by(ConversationTurn.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row

    async def cleanup_old_turns(
        self,
        db: AsyncSession,
        max_age_hours: int = 24,
    ) -> int:
        """Delete conversation turns older than max_age_hours.

        Args:
            db: Async database session.
            max_age_hours: Maximum age in hours for turns to keep.

        Returns:
            Number of deleted turns.
        """
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        result = await db.execute(
            delete(ConversationTurn).where(ConversationTurn.created_at < cutoff)
        )
        await db.flush()
        return result.rowcount


def turns_to_history(turns: list[ConversationTurn]) -> list[dict]:
    """Convert ConversationTurn models to history dict format.

    Args:
        turns: List of ConversationTurn models.

    Returns:
        List of history dicts with keys: user, bot, intent, sql, timestamp.
    """
    return [
        {
            "user": turn.user_message,
            "bot": turn.bot_response,
            "intent": turn.intent,
            "sql": turn.sql_query,
            "timestamp": turn.created_at.isoformat() if turn.created_at else None,
        }
        for turn in turns
    ]
