# Testing Guide

## Running Tests

```bash
# Run all tests (recommended)
make test

# Run with coverage
make test-cov

# Or directly with uv
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/api/test_slack.py -v

# Run specific test class
uv run pytest tests/services/test_slack_service.py::TestHandleButtonAction -v

# Run specific test
uv run pytest tests/api/test_health.py::test_health_check -v

# Stop on first failure
uv run pytest -x

# Run with print output
uv run pytest -s
```

## Running Evaluations

The project includes an evaluation framework for testing the analytics chatbot:

```bash
# Run full evaluation suite (18 test cases)
make evals

# Run quick evaluation (3 test cases)
make evals-quick

# Run directly with options
uv run python -m evals.main --no-report


## Test Structure

```
tests/
├── conftest.py                  # Shared fixtures (client, mock_db_session)
├── api/                         # API endpoint tests
│   ├── test_health.py           # Health check endpoints
│   ├── test_slack.py            # Slack webhook endpoints
│   └── test_exceptions.py       # Exception handlers
├── services/                    # Service layer tests
│   └── test_slack_service.py    # SlackService tests
├── test_repositories.py         # Repository tests
├── test_conversation_history.py # Conversation history tests
├── test_commands.py             # CLI command tests
├── test_core.py                 # Config and middleware tests
└── test_pipelines.py            # Pipeline tests
```

## Key Fixtures (`conftest.py`)

```python
# Async backend for anyio
@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

# Mock database session
@pytest.fixture
async def mock_db_session() -> AsyncGenerator[AsyncMock, None]:
    mock = AsyncMock()
    mock.execute = AsyncMock()
    mock.commit = AsyncMock()
    mock.rollback = AsyncMock()
    yield mock

# Async HTTP client
@pytest.fixture
async def client(mock_db_session) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db_session] = lambda: mock_db_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
```

## Writing Tests

### API Endpoint Test

```python
import pytest
from httpx import AsyncClient

@pytest.mark.anyio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

### Slack Webhook Test

```python
@pytest.mark.anyio
async def test_url_verification(client: AsyncClient):
    """Test Slack URL verification challenge."""
    payload = {
        "type": "url_verification",
        "challenge": "test-challenge-token",
    }
    response = await client.post(
        "/slack/events",
        json=payload,
        headers=make_slack_headers(payload),
    )
    assert response.status_code == 200
    assert response.json()["challenge"] == "test-challenge-token"
```

### Service Test with Mocking

```python
@pytest.mark.anyio
async def test_handle_button_action():
    """Test button click handling."""
    with patch.object(ConversationRepository, "get_turn_by_action_id") as mock:
        mock.return_value = ConversationTurn(
            sql_query="SELECT * FROM users",
            # ...
        )
        result = await slack_service.handle_button_action(
            action_id="show_sql",
            value="test-action-id",
            user_id="U123",
            channel_id="C123",
            thread_ts="123.456",
        )
        assert "SELECT * FROM users" in result["blocks"][1]["text"]["text"]
```

### Repository Test

```python
class TestConversationRepository:
    @pytest.mark.anyio
    async def test_add_turn_stores_sql_query(self):
        mock_db = AsyncMock()
        repo = ConversationRepository()

        await repo.add_turn(
            mock_db,
            thread_id="test-thread",
            user_message="How many users?",
            bot_response="There are 100 users.",
            intent="analytics",
            sql_query="SELECT COUNT(*) FROM users",
        )

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
```

## Running Evaluations

The project includes an evaluation framework for testing the analytics chatbot:

```bash
# Run full evaluation suite (18 test cases)
make evals

# Run quick evaluation (3 test cases)
make evals-quick

# Run directly with options
uv run python -m evals.main --no-report
```

Evaluations test:
- Intent classification accuracy
- SQL generation correctness
- Response quality (via LLM judge)
- CSV export functionality

See `evals/` directory for test cases and evaluators.

## Test Conventions

1. **Use `@pytest.mark.anyio`** for async tests (not `@pytest.mark.asyncio`)
2. **Mock external dependencies** - Don't call real APIs in tests
3. **Use fixtures** for common setup (client, mock_db_session)
4. **Test edge cases** - Empty inputs, errors, boundary conditions
5. **Keep tests isolated** - Each test should be independent

## Mocking Slack Signatures

For Slack webhook tests, use the helper to generate valid signatures:

```python
def make_slack_headers(payload: dict, timestamp: str | None = None) -> dict:
    """Generate valid Slack request headers with signature."""
    ts = timestamp or str(int(time.time()))
    body = json.dumps(payload)
    sig_basestring = f"v0:{ts}:{body}"
    signature = "v0=" + hmac.new(
        settings.SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": signature,
        "Content-Type": "application/json",
    }
```
