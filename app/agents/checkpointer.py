"""PostgreSQL-based checkpoint saver for LangGraph.

Implements LangGraph's BaseCheckpointSaver interface to persist
agent state to PostgreSQL for conversation continuity.
"""

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_context
from app.repositories import CheckpointRepository

logger = logging.getLogger(__name__)


class PostgresCheckpointer(BaseCheckpointSaver):
    """Checkpoint saver that persists LangGraph state to PostgreSQL.

    This implementation stores checkpoints in the agent_checkpoints table,
    allowing conversation state to persist across server restarts.
    """

    def __init__(self, db: AsyncSession | None = None) -> None:
        """Initialize the checkpointer.

        Args:
            db: Optional database session. If not provided, will create
                new sessions for each operation using get_db_context().
        """
        super().__init__()
        self._db = db
        self._repository = CheckpointRepository()

    def _get_thread_id(self, config: RunnableConfig) -> str:
        """Extract thread_id from config."""
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id", "default")
        return str(thread_id)

    def _get_checkpoint_id(self, config: RunnableConfig) -> str | None:
        """Extract checkpoint_id from config if present."""
        configurable = config.get("configurable", {})
        return configurable.get("checkpoint_id")

    def _serialize_checkpoint(self, checkpoint: Checkpoint) -> dict:
        """Serialize checkpoint to JSON-compatible dict."""
        return self._serialize_value(dict(checkpoint))

    def _serialize_value(self, value: Any) -> Any:
        """Recursively serialize a value to JSON-compatible format."""
        from langchain_core.messages import BaseMessage
        from pydantic import BaseModel

        if value is None:
            return None
        elif isinstance(value, str | int | float | bool):
            return value
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list | tuple):
            return [self._serialize_value(item) for item in value]
        elif isinstance(value, BaseMessage | BaseModel) or hasattr(value, "model_dump"):
            return value.model_dump()
        elif hasattr(value, "__dict__"):
            return self._serialize_value(value.__dict__)
        else:
            # Fallback: convert to string
            return str(value)

    def _deserialize_checkpoint(self, data: dict) -> Checkpoint:
        """Deserialize checkpoint from stored dict."""
        return Checkpoint(
            v=data.get("v", 1),
            id=data.get("id", ""),
            ts=data.get("ts", ""),
            channel_values=self._deserialize_channel_values(data.get("channel_values", {})),
            channel_versions=data.get("channel_versions", {}),
            versions_seen=data.get("versions_seen", {}),
            pending_sends=data.get("pending_sends", []),
        )

    def _deserialize_channel_values(self, channel_values: dict) -> dict:
        """Deserialize channel values, converting dicts back to LangChain messages."""
        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            SystemMessage,
            ToolMessage,
        )

        message_types = {
            "human": HumanMessage,
            "ai": AIMessage,
            "system": SystemMessage,
            "tool": ToolMessage,
        }

        deserialized = {}
        for key, value in channel_values.items():
            if isinstance(value, list):
                messages = []
                for item in value:
                    if isinstance(item, dict) and "type" in item:
                        msg_type = item.get("type")
                        msg_class = message_types.get(msg_type)
                        if msg_class:
                            try:
                                messages.append(msg_class.model_validate(item))
                            except Exception:
                                messages.append(item)
                        else:
                            messages.append(item)
                    else:
                        messages.append(item)
                deserialized[key] = messages
            else:
                deserialized[key] = value
        return deserialized

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Get a checkpoint tuple from the database.

        Args:
            config: The config to use for getting the checkpoint.

        Returns:
            CheckpointTuple if found, None otherwise.
        """
        thread_id = self._get_thread_id(config)
        checkpoint_id = self._get_checkpoint_id(config)

        async def _get(db: AsyncSession) -> CheckpointTuple | None:
            checkpoint_record = await self._repository.get(db, thread_id, checkpoint_id)
            if not checkpoint_record:
                return None

            checkpoint = self._deserialize_checkpoint(checkpoint_record.checkpoint_data)
            metadata = CheckpointMetadata(**(checkpoint_record.metadata_ or {}))

            return CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": checkpoint_record.checkpoint_id,
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": checkpoint_record.parent_checkpoint_id,
                    }
                }
                if checkpoint_record.parent_checkpoint_id
                else None,
                pending_writes=[],
            )

        if self._db:
            return await _get(self._db)

        async with get_db_context() as db:
            return await _get(db)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Store a checkpoint in the database.

        Args:
            config: The config to associate with the checkpoint.
            checkpoint: The checkpoint to store.
            metadata: Metadata to store with the checkpoint.
            new_versions: New channel versions for this checkpoint.

        Returns:
            Config with the stored checkpoint ID.
        """
        thread_id = self._get_thread_id(config)
        checkpoint_id = checkpoint.get("id", "")
        parent_checkpoint_id = self._get_checkpoint_id(config)

        serialized = self._serialize_checkpoint(checkpoint)

        async def _put(db: AsyncSession) -> None:
            await self._repository.put(
                db,
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                parent_checkpoint_id=parent_checkpoint_id,
                checkpoint_data=serialized,
                metadata=dict(metadata) if metadata else None,
            )

        if self._db:
            await _put(self._db)
        else:
            async with get_db_context() as db:
                await _put(db)

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """List checkpoints from the database.

        Args:
            config: Optional config to filter by thread_id.
            filter: Optional additional filters (not implemented).
            before: Optional config to get checkpoints before (not implemented).
            limit: Maximum number of checkpoints to return.

        Yields:
            CheckpointTuple instances.
        """
        if not config:
            return

        thread_id = self._get_thread_id(config)

        async def _list(db: AsyncSession) -> list:
            return await self._repository.list(db, thread_id, limit=limit or 10)

        if self._db:
            checkpoints = await _list(self._db)
        else:
            async with get_db_context() as db:
                checkpoints = await _list(db)

        for record in checkpoints:
            checkpoint = self._deserialize_checkpoint(record.checkpoint_data)
            metadata = CheckpointMetadata(**(record.metadata_ or {}))

            yield CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": record.checkpoint_id,
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": record.parent_checkpoint_id,
                    }
                }
                if record.parent_checkpoint_id
                else None,
                pending_writes=[],
            )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Store intermediate writes (not implemented - uses in-memory for now)."""
        pass

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Sync version - not implemented, use async."""
        raise NotImplementedError("Use async version aget_tuple")

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Sync version - not implemented, use async."""
        raise NotImplementedError("Use async version aput")

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ):
        """Sync version - not implemented, use async."""
        raise NotImplementedError("Use async version alist")

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Sync version - not implemented, use async."""
        raise NotImplementedError("Use async version aput_writes")
