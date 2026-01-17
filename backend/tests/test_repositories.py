"""Tests for repository layer."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.repositories import AnalyticsRepository, CheckpointRepository
from app.repositories.base import BaseRepository


class MockModel:
    """Mock SQLAlchemy model for testing."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid4())
        for key, value in kwargs.items():
            setattr(self, key, value)


class MockCreateSchema(BaseModel):
    """Mock create schema."""

    name: str


class MockUpdateSchema(BaseModel):
    """Mock update schema."""

    name: str | None = None


class TestBaseRepository:
    """Tests for BaseRepository."""

    @pytest.fixture
    def repository(self):
        """Create a test repository."""
        return BaseRepository[MockModel, MockCreateSchema, MockUpdateSchema](MockModel)

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = MagicMock()
        session.get = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.delete = AsyncMock()
        return session

    @pytest.mark.anyio
    async def test_get_returns_model(self, repository, mock_session):
        """Test get returns a model by ID."""
        mock_obj = MockModel(name="test")
        mock_session.get.return_value = mock_obj

        result = await repository.get(mock_session, mock_obj.id)

        assert result == mock_obj
        mock_session.get.assert_called_once_with(MockModel, mock_obj.id)

    @pytest.mark.anyio
    async def test_get_returns_none_when_not_found(self, repository, mock_session):
        """Test get returns None when not found."""
        mock_session.get.return_value = None

        result = await repository.get(mock_session, uuid4())

        assert result is None

    # Note: test_get_multi_returns_list is skipped because it requires a real
    # SQLAlchemy model. The select() function cannot work with a mock class.
    # For proper integration testing, use actual SQLAlchemy models with a test DB.

    @pytest.mark.anyio
    async def test_create_adds_and_returns_model(self, repository, mock_session):
        """Test create adds a new model."""
        create_data = MockCreateSchema(name="new item")

        # Mock the model creation
        async def refresh_side_effect(obj):
            obj.id = uuid4()

        mock_session.refresh.side_effect = refresh_side_effect

        result = await repository.create(mock_session, obj_in=create_data)

        assert result.name == "new item"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.anyio
    async def test_update_with_schema(self, repository, mock_session):
        """Test update with Pydantic schema."""
        db_obj = MockModel(name="old name")
        update_data = MockUpdateSchema(name="new name")

        result = await repository.update(mock_session, db_obj=db_obj, obj_in=update_data)

        assert result.name == "new name"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.anyio
    async def test_update_with_dict(self, repository, mock_session):
        """Test update with dictionary."""
        db_obj = MockModel(name="old name")
        update_data = {"name": "new name"}

        result = await repository.update(mock_session, db_obj=db_obj, obj_in=update_data)

        assert result.name == "new name"

    @pytest.mark.anyio
    async def test_delete_removes_and_returns_model(self, repository, mock_session):
        """Test delete removes and returns model."""
        mock_obj = MockModel(name="to delete")
        mock_session.get.return_value = mock_obj

        result = await repository.delete(mock_session, id=mock_obj.id)

        assert result == mock_obj
        mock_session.delete.assert_called_once_with(mock_obj)
        mock_session.flush.assert_called_once()

    @pytest.mark.anyio
    async def test_delete_returns_none_when_not_found(self, repository, mock_session):
        """Test delete returns None when not found."""
        mock_session.get.return_value = None

        result = await repository.delete(mock_session, id=uuid4())

        assert result is None
        mock_session.delete.assert_not_called()


class TestAnalyticsRepository:
    """Tests for AnalyticsRepository.

    Pattern 1: session passed to methods (not held in __init__).
    """

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def repository(self):
        """Create a test repository (no session in init)."""
        return AnalyticsRepository()

    @pytest.mark.anyio
    async def test_execute_query_returns_rows_and_columns(self, repository, mock_session):
        """Test execute_query returns rows and column names."""
        # Mock the result
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "name", "count"]
        mock_result.fetchall.return_value = [
            (1, "app1", 10),
            (2, "app2", 20),
        ]
        mock_session.execute.return_value = mock_result

        rows, columns = await repository.execute_query(mock_session, "SELECT * FROM apps")

        assert columns == ["id", "name", "count"]
        assert len(rows) == 2
        assert rows[0] == {"id": 1, "name": "app1", "count": 10}
        assert rows[1] == {"id": 2, "name": "app2", "count": 20}

    @pytest.mark.anyio
    async def test_execute_query_serializes_decimal(self, repository, mock_session):
        """Test execute_query converts Decimal to float."""
        mock_result = MagicMock()
        mock_result.keys.return_value = ["amount"]
        mock_result.fetchall.return_value = [(Decimal("123.45"),)]
        mock_session.execute.return_value = mock_result

        rows, _columns = await repository.execute_query(mock_session, "SELECT amount FROM totals")

        assert rows[0]["amount"] == 123.45
        assert isinstance(rows[0]["amount"], float)

    @pytest.mark.anyio
    async def test_execute_query_serializes_datetime(self, repository, mock_session):
        """Test execute_query converts datetime to ISO format."""
        test_dt = datetime(2024, 1, 15, 10, 30, 0)
        mock_result = MagicMock()
        mock_result.keys.return_value = ["created_at"]
        mock_result.fetchall.return_value = [(test_dt,)]
        mock_session.execute.return_value = mock_result

        rows, _columns = await repository.execute_query(
            mock_session, "SELECT created_at FROM events"
        )

        assert rows[0]["created_at"] == "2024-01-15T10:30:00"

    @pytest.mark.anyio
    async def test_execute_query_handles_none(self, repository, mock_session):
        """Test execute_query handles None values."""
        mock_result = MagicMock()
        mock_result.keys.return_value = ["name"]
        mock_result.fetchall.return_value = [(None,)]
        mock_session.execute.return_value = mock_result

        rows, _columns = await repository.execute_query(mock_session, "SELECT name FROM users")

        assert rows[0]["name"] is None

    @pytest.mark.anyio
    async def test_execute_query_empty_result(self, repository, mock_session):
        """Test execute_query with empty result."""
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "name"]
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        rows, columns = await repository.execute_query(mock_session, "SELECT * FROM empty_table")

        assert columns == ["id", "name"]
        assert rows == []

    @pytest.mark.anyio
    async def test_execute_query_raises_on_error(self, repository, mock_session):
        """Test execute_query propagates database errors."""
        mock_session.execute.side_effect = Exception("Table not found")

        with pytest.raises(Exception, match="Table not found"):
            await repository.execute_query(mock_session, "SELECT * FROM nonexistent")


class TestCheckpointRepository:
    """Tests for CheckpointRepository.

    Pattern 1: session passed to methods (not held in __init__).
    """

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def repository(self):
        """Create a test repository (no session in init)."""
        return CheckpointRepository()

    @pytest.fixture
    def mock_checkpoint(self):
        """Create a mock checkpoint record."""
        checkpoint = MagicMock()
        checkpoint.id = uuid4()
        checkpoint.thread_id = "thread-123"
        checkpoint.checkpoint_id = "cp-456"
        checkpoint.parent_checkpoint_id = "cp-455"
        checkpoint.checkpoint_data = {"state": "test"}
        checkpoint.metadata_ = {"source": "test"}
        checkpoint.created_at = datetime.now()
        return checkpoint

    @pytest.mark.anyio
    async def test_get_returns_checkpoint_by_thread_and_id(
        self, repository, mock_session, mock_checkpoint
    ):
        """Test get returns checkpoint when found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_checkpoint
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, "thread-123", "cp-456")

        assert result == mock_checkpoint
        mock_session.execute.assert_called_once()

    @pytest.mark.anyio
    async def test_get_returns_latest_when_no_checkpoint_id(
        self, repository, mock_session, mock_checkpoint
    ):
        """Test get returns latest checkpoint when checkpoint_id not provided."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_checkpoint
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, "thread-123")

        assert result == mock_checkpoint

    @pytest.mark.anyio
    async def test_get_returns_none_when_not_found(self, repository, mock_session):
        """Test get returns None when checkpoint not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, "nonexistent-thread")

        assert result is None

    @pytest.mark.anyio
    async def test_put_creates_checkpoint(self, repository, mock_session):
        """Test put creates a new checkpoint."""
        checkpoint_data = {"state": "test", "messages": []}

        await repository.put(
            mock_session,
            thread_id="thread-123",
            checkpoint_id="cp-456",
            parent_checkpoint_id="cp-455",
            checkpoint_data=checkpoint_data,
            metadata={"source": "test"},
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once()

        # Verify the checkpoint was created with correct data
        added_checkpoint = mock_session.add.call_args[0][0]
        assert added_checkpoint.thread_id == "thread-123"
        assert added_checkpoint.checkpoint_id == "cp-456"
        assert added_checkpoint.parent_checkpoint_id == "cp-455"
        assert added_checkpoint.checkpoint_data == checkpoint_data

    @pytest.mark.anyio
    async def test_put_without_metadata(self, repository, mock_session):
        """Test put works without metadata."""
        await repository.put(
            mock_session,
            thread_id="thread-123",
            checkpoint_id="cp-456",
            parent_checkpoint_id=None,
            checkpoint_data={"state": "test"},
        )

        mock_session.add.assert_called_once()
        added_checkpoint = mock_session.add.call_args[0][0]
        assert added_checkpoint.metadata_ is None

    @pytest.mark.anyio
    async def test_list_returns_checkpoints(self, repository, mock_session, mock_checkpoint):
        """Test list returns checkpoints for thread."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_checkpoint]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list(mock_session, "thread-123", limit=10)

        assert len(result) == 1
        assert result[0] == mock_checkpoint

    @pytest.mark.anyio
    async def test_list_returns_empty_when_no_checkpoints(self, repository, mock_session):
        """Test list returns empty list when no checkpoints."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repository.list(mock_session, "empty-thread")

        assert result == []

    @pytest.mark.anyio
    async def test_delete_thread_removes_checkpoints(self, repository, mock_session):
        """Test delete_thread removes all checkpoints for thread."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        count = await repository.delete_thread(mock_session, "thread-123")

        assert count == 5
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.anyio
    async def test_delete_thread_returns_zero_when_none_deleted(self, repository, mock_session):
        """Test delete_thread returns 0 when no checkpoints to delete."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        count = await repository.delete_thread(mock_session, "nonexistent-thread")

        assert count == 0
