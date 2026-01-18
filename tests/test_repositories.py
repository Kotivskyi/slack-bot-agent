"""Tests for repository layer."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.repositories import AnalyticsRepository
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


class TestConversationRepository:
    """Tests for ConversationRepository.

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
        from app.repositories import ConversationRepository

        return ConversationRepository()

    @pytest.mark.anyio
    async def test_add_turn_truncates_long_bot_response(self, repository, mock_session):
        """Test add_turn truncates bot_response to 500 chars."""
        long_response = "A" * 1000

        await repository.add_turn(
            mock_session,
            thread_id="thread-1",
            user_message="question",
            bot_response=long_response,
            intent="analytics_query",
        )

        # Verify the model was added with truncated response
        mock_session.add.assert_called_once()
        added_turn = mock_session.add.call_args[0][0]
        assert len(added_turn.bot_response) == 503  # 500 + "..."
        assert added_turn.bot_response.endswith("...")

    @pytest.mark.anyio
    async def test_add_turn_does_not_truncate_short_response(self, repository, mock_session):
        """Test add_turn does not truncate responses under 500 chars."""
        short_response = "A" * 100

        await repository.add_turn(
            mock_session,
            thread_id="thread-1",
            user_message="question",
            bot_response=short_response,
            intent="analytics_query",
        )

        added_turn = mock_session.add.call_args[0][0]
        assert len(added_turn.bot_response) == 100
        assert not added_turn.bot_response.endswith("...")

    @pytest.mark.anyio
    async def test_add_turn_stores_sql_query(self, repository, mock_session):
        """Test add_turn stores SQL query when provided."""
        sql = "SELECT * FROM apps"

        await repository.add_turn(
            mock_session,
            thread_id="thread-1",
            user_message="list apps",
            bot_response="Here are your apps",
            intent="analytics_query",
            sql_query=sql,
        )

        added_turn = mock_session.add.call_args[0][0]
        assert added_turn.sql_query == sql

    @pytest.mark.anyio
    async def test_add_turn_stores_action_id(self, repository, mock_session):
        """Test add_turn stores action_id when provided."""
        action_id = "550e8400-e29b-41d4-a716-446655440000"

        await repository.add_turn(
            mock_session,
            thread_id="thread-1",
            user_message="list apps",
            bot_response="Here are your apps",
            intent="analytics_query",
            sql_query="SELECT * FROM apps",
            action_id=action_id,
        )

        added_turn = mock_session.add.call_args[0][0]
        assert added_turn.action_id == action_id

    @pytest.mark.anyio
    async def test_add_turn_without_action_id(self, repository, mock_session):
        """Test add_turn stores None for action_id when not provided."""
        await repository.add_turn(
            mock_session,
            thread_id="thread-1",
            user_message="list apps",
            bot_response="Here are your apps",
            intent="analytics_query",
        )

        added_turn = mock_session.add.call_args[0][0]
        assert added_turn.action_id is None

    @pytest.mark.anyio
    async def test_get_recent_turns_returns_chronological_order(self, repository, mock_session):
        """Test get_recent_turns returns turns oldest first."""
        from app.db.models.conversation import ConversationTurn

        # Mock turns returned in descending order (most recent first)
        turn1 = ConversationTurn(
            id=1,
            thread_id="thread-1",
            user_message="first",
            bot_response="response1",
            intent="analytics_query",
            created_at=datetime(2024, 1, 1, 10, 0),
        )
        turn2 = ConversationTurn(
            id=2,
            thread_id="thread-1",
            user_message="second",
            bot_response="response2",
            intent="analytics_query",
            created_at=datetime(2024, 1, 1, 11, 0),
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [turn2, turn1]  # DESC order
        mock_session.execute.return_value = mock_result

        turns = await repository.get_recent_turns(mock_session, "thread-1", limit=10)

        # Should be reversed to chronological (oldest first)
        assert len(turns) == 2
        assert turns[0].user_message == "first"
        assert turns[1].user_message == "second"

    @pytest.mark.anyio
    async def test_get_most_recent_sql_returns_sql(self, repository, mock_session):
        """Test get_most_recent_sql returns the SQL query."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "SELECT COUNT(*) FROM apps"
        mock_session.execute.return_value = mock_result

        sql = await repository.get_most_recent_sql(mock_session, "thread-1")

        assert sql == "SELECT COUNT(*) FROM apps"

    @pytest.mark.anyio
    async def test_get_most_recent_sql_returns_none_when_no_sql(self, repository, mock_session):
        """Test get_most_recent_sql returns None when no SQL found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        sql = await repository.get_most_recent_sql(mock_session, "thread-1")

        assert sql is None

    @pytest.mark.anyio
    async def test_find_sql_by_keyword_returns_matching_sql(self, repository, mock_session):
        """Test find_sql_by_keyword returns SQL for matching user message."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "SELECT * FROM apps WHERE country = 'US'"
        mock_session.execute.return_value = mock_result

        sql = await repository.find_sql_by_keyword(mock_session, "thread-1", "country")

        assert sql == "SELECT * FROM apps WHERE country = 'US'"

    @pytest.mark.anyio
    async def test_find_sql_by_keyword_returns_none_when_no_match(self, repository, mock_session):
        """Test find_sql_by_keyword returns None when no match found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        sql = await repository.find_sql_by_keyword(mock_session, "thread-1", "nonexistent")

        assert sql is None

    @pytest.mark.anyio
    async def test_get_turn_by_action_id_returns_turn(self, repository, mock_session):
        """Test get_turn_by_action_id returns the conversation turn."""
        from app.db.models.conversation import ConversationTurn

        action_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_turn = ConversationTurn(
            id=1,
            thread_id="thread-1",
            user_message="list apps",
            bot_response="Here are your apps",
            intent="analytics_query",
            sql_query="SELECT * FROM apps",
            action_id=action_id,
            created_at=datetime(2024, 1, 1, 10, 0),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_turn
        mock_session.execute.return_value = mock_result

        turn = await repository.get_turn_by_action_id(mock_session, action_id)

        assert turn is not None
        assert turn.action_id == action_id
        assert turn.sql_query == "SELECT * FROM apps"

    @pytest.mark.anyio
    async def test_get_turn_by_action_id_returns_none_when_not_found(
        self, repository, mock_session
    ):
        """Test get_turn_by_action_id returns None when no turn found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        turn = await repository.get_turn_by_action_id(mock_session, "nonexistent-action-id")

        assert turn is None

    @pytest.mark.anyio
    async def test_cleanup_old_turns_deletes_and_returns_count(self, repository, mock_session):
        """Test cleanup_old_turns deletes old turns and returns count."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        deleted = await repository.cleanup_old_turns(mock_session, max_age_hours=24)

        assert deleted == 5
        mock_session.flush.assert_called_once()


class TestTurnsToHistory:
    """Tests for turns_to_history helper function."""

    def test_turns_to_history_converts_correctly(self):
        """Test turns_to_history converts turns to history dict format."""
        from app.db.models.conversation import ConversationTurn
        from app.repositories import turns_to_history

        turns = [
            ConversationTurn(
                id=1,
                thread_id="thread-1",
                user_message="question 1",
                bot_response="answer 1",
                intent="analytics_query",
                sql_query="SELECT 1",
                created_at=datetime(2024, 1, 1, 10, 0),
            ),
            ConversationTurn(
                id=2,
                thread_id="thread-1",
                user_message="question 2",
                bot_response="answer 2",
                intent="follow_up",
                sql_query=None,
                created_at=datetime(2024, 1, 1, 11, 0),
            ),
        ]

        history = turns_to_history(turns)

        assert len(history) == 2
        assert history[0]["user"] == "question 1"
        assert history[0]["bot"] == "answer 1"
        assert history[0]["intent"] == "analytics_query"
        assert history[0]["sql"] == "SELECT 1"
        assert history[0]["timestamp"] == "2024-01-01T10:00:00"

        assert history[1]["user"] == "question 2"
        assert history[1]["bot"] == "answer 2"
        assert history[1]["intent"] == "follow_up"
        assert history[1]["sql"] is None

    def test_turns_to_history_empty_list(self):
        """Test turns_to_history handles empty list."""
        from app.repositories import turns_to_history

        history = turns_to_history([])

        assert history == []
