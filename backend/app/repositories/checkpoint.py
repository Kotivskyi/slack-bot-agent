"""Checkpoint repository for agent state persistence.

Contains database operations for AgentCheckpoint entity.
Used by PostgresCheckpointer to persist LangGraph state.
"""

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.checkpoint import AgentCheckpoint


class CheckpointRepository:
    """Repository for LangGraph checkpoint persistence.

    Follows Pattern 1: session passed to methods (not held in __init__).

    Usage:
        repo = CheckpointRepository()
        checkpoint = await repo.get(db, thread_id, checkpoint_id)
        await repo.put(db, thread_id=..., checkpoint_data=...)
    """

    async def get(
        self,
        db: AsyncSession,
        thread_id: str,
        checkpoint_id: str | None = None,
    ) -> AgentCheckpoint | None:
        """Get checkpoint by thread_id and optionally checkpoint_id.

        If checkpoint_id is not provided, returns the latest checkpoint for the thread.

        Args:
            db: Database session.
            thread_id: The thread ID to look up.
            checkpoint_id: Optional specific checkpoint ID.

        Returns:
            AgentCheckpoint if found, None otherwise.
        """
        if checkpoint_id:
            query = select(AgentCheckpoint).where(
                AgentCheckpoint.thread_id == thread_id,
                AgentCheckpoint.checkpoint_id == checkpoint_id,
            )
        else:
            query = (
                select(AgentCheckpoint)
                .where(AgentCheckpoint.thread_id == thread_id)
                .order_by(desc(AgentCheckpoint.created_at))
                .limit(1)
            )

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def put(
        self,
        db: AsyncSession,
        *,
        thread_id: str,
        checkpoint_id: str,
        parent_checkpoint_id: str | None,
        checkpoint_data: dict,
        metadata: dict | None = None,
    ) -> AgentCheckpoint:
        """Store a new checkpoint.

        Args:
            db: Database session.
            thread_id: The thread ID for this checkpoint.
            checkpoint_id: Unique identifier for this checkpoint.
            parent_checkpoint_id: ID of the parent checkpoint (for history).
            checkpoint_data: Serialized graph state.
            metadata: Optional metadata about the checkpoint.

        Returns:
            Created AgentCheckpoint instance.
        """
        checkpoint = AgentCheckpoint(
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id,
            checkpoint_data=checkpoint_data,
            metadata_=metadata,
        )
        db.add(checkpoint)
        await db.flush()
        await db.refresh(checkpoint)
        return checkpoint

    async def list(
        self,
        db: AsyncSession,
        thread_id: str,
        *,
        limit: int = 10,
    ) -> list[AgentCheckpoint]:
        """List checkpoints for a thread, ordered by creation time (newest first).

        Args:
            db: Database session.
            thread_id: The thread ID to list checkpoints for.
            limit: Maximum number of checkpoints to return.

        Returns:
            List of AgentCheckpoint instances.
        """
        query = (
            select(AgentCheckpoint)
            .where(AgentCheckpoint.thread_id == thread_id)
            .order_by(desc(AgentCheckpoint.created_at))
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def delete_thread(
        self,
        db: AsyncSession,
        thread_id: str,
    ) -> int:
        """Delete all checkpoints for a thread.

        Args:
            db: Database session.
            thread_id: The thread ID to delete checkpoints for.

        Returns:
            Number of deleted checkpoints.
        """
        query = delete(AgentCheckpoint).where(AgentCheckpoint.thread_id == thread_id)
        result = await db.execute(query)
        await db.flush()
        return result.rowcount
