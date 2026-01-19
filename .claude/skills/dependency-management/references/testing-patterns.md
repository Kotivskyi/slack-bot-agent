# Testing Patterns

## Testing Nodes (Unit)

Mock the repository and pass it via config:

```python
# tests/agents/test_sql_executor.py
import pytest
from unittest.mock import AsyncMock

from app.agents.analytics_chatbot.nodes.sql_executor import execute_and_cache


@pytest.mark.asyncio
async def test_execute_and_cache_success():
    # Mock repository
    mock_repo = AsyncMock()
    mock_repo.execute_raw_sql.return_value = [{"count": 42}]

    # Create state and config
    state = {"sql": "SELECT COUNT(*) as count FROM apps"}
    config = {"configurable": {"metrics_repo": mock_repo}}

    # Execute node
    result = await execute_and_cache(state, config)

    # Assert
    assert result["results"] == [{"count": 42}]
    assert result["error"] is None
    mock_repo.execute_raw_sql.assert_called_once_with(state["sql"])


@pytest.mark.asyncio
async def test_execute_and_cache_handles_error():
    # Mock repository that raises
    mock_repo = AsyncMock()
    mock_repo.execute_raw_sql.side_effect = Exception("Connection failed")

    state = {"sql": "SELECT * FROM apps"}
    config = {"configurable": {"metrics_repo": mock_repo}}

    result = await execute_and_cache(state, config)

    assert result["results"] == []
    assert "Connection failed" in result["error"]
```

---

## Testing Services (Integration)

Use real db session, mock external clients:

```python
# tests/services/test_agent_service.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import MagicMock

from app.services.agent import AnalyticsAgentService


@pytest.fixture
def mock_slack():
    return MagicMock()


@pytest.mark.asyncio
async def test_analytics_service_run(db_session: AsyncSession, mock_slack):
    service = AnalyticsAgentService(db=db_session, slack_client=mock_slack)

    response = await service.run(
        user_query="How many apps do we have?",
        thread_id="thread-123",
        channel_id="C123",
        user_id="U123",
    )

    assert "apps" in response.lower()


@pytest.mark.asyncio
async def test_analytics_service_handles_error(db_session: AsyncSession, mock_slack):
    service = AnalyticsAgentService(db=db_session, slack_client=mock_slack)

    # Test with invalid query that should be handled gracefully
    response = await service.run(
        user_query="",  # Empty query
        thread_id="thread-123",
        channel_id="C123",
        user_id="U123",
    )

    # Should not raise, should return error message
    assert response is not None
```

---

## Testing Repositories (Unit)

```python
# tests/repositories/test_metrics.py
import pytest
from app.repositories.metrics import MetricsRepository


@pytest.mark.asyncio
async def test_execute_raw_sql(db_session):
    repo = MetricsRepository(db_session)

    results = await repo.execute_raw_sql("SELECT 1 as value")

    assert results == [{"value": 1}]


@pytest.mark.asyncio
async def test_get_schema_info(db_session):
    repo = MetricsRepository(db_session)

    schema = await repo.get_schema_info()

    assert "apps" in schema  # Assuming apps table exists
```

---

## Test Fixtures

```python
# conftest.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.db.session import async_session_maker


@pytest.fixture
async def db_session() -> AsyncSession:
    """Provides a test database session with automatic rollback."""
    async with async_session_maker() as session:
        yield session
        await session.rollback()
```

---

## Testing Strategy Summary

| Layer | Test Type | Mock | Real |
|-------|-----------|------|------|
| Nodes | Unit | Repositories, clients | State, config structure |
| Services | Integration | External clients | DB session, repositories |
| Repositories | Unit | - | DB session |
| Routes | E2E | - | Everything |
