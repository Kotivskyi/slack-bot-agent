"""Tests for SlackService button action handling with action_id."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from slack_sdk.web.async_client import AsyncWebClient

from app.services.slack import (
    SLACK_MAX_BLOCK_TEXT_LENGTH,
    TRUNCATION_NOTICE,
    SlackService,
    _prepare_blocks_for_slack,
    _truncate_block_text,
)


@pytest.fixture
def mock_slack_client() -> MagicMock:
    """Create a mock Slack client for testing."""
    mock = MagicMock(spec=AsyncWebClient)
    mock.chat_postMessage = AsyncMock(return_value=MagicMock(data={"ok": True}))
    mock.files_upload_v2 = AsyncMock(return_value=MagicMock(data={"ok": True}))
    return mock


class TestHandleButtonAction:
    """Tests for handle_button_action method using action_id lookups."""

    @pytest.fixture
    def slack_service(self, mock_slack_client):
        """Create a SlackService instance."""
        return SlackService(
            slack_client=mock_slack_client,
            signing_secret="test-secret",
        )

    @pytest.mark.anyio
    async def test_show_sql_action_id_lookup(self, slack_service):
        """Test show_sql retrieves SQL from specific turn by action_id."""
        action_id_value = "550e8400-e29b-41d4-a716-446655440000"
        expected_sql = "SELECT COUNT(*) FROM apps"

        # Create mock turn
        mock_turn = MagicMock()
        mock_turn.sql_query = expected_sql
        mock_turn.action_id = action_id_value

        # Create mock repository
        mock_repo = MagicMock()
        mock_repo.get_turn_by_action_id = AsyncMock(return_value=mock_turn)

        # Create mock db session
        mock_db = AsyncMock()

        @asynccontextmanager
        async def mock_get_db_context():
            yield mock_db

        with (
            patch("app.db.session.get_db_context", mock_get_db_context),
            patch("app.repositories.ConversationRepository", return_value=mock_repo),
        ):
            result = await slack_service.handle_button_action(
                action_id="show_sql",
                value=action_id_value,
                user_id="U123",
                channel_id="C123",
                thread_ts="1234567890.123456",
            )

        assert "blocks" in result
        assert result["text"] == "*SQL Query*"
        sql_block = result["blocks"][1]
        assert expected_sql in sql_block["text"]["text"]

    @pytest.mark.anyio
    async def test_export_csv_action_id_lookup(self, slack_service):
        """Test export_csv retrieves SQL from specific turn by action_id."""
        action_id_value = "550e8400-e29b-41d4-a716-446655440000"
        expected_sql = "SELECT * FROM apps LIMIT 10"

        # Create mock turn
        mock_turn = MagicMock()
        mock_turn.sql_query = expected_sql
        mock_turn.action_id = action_id_value

        # Create mock repositories
        mock_conv_repo = MagicMock()
        mock_conv_repo.get_turn_by_action_id = AsyncMock(return_value=mock_turn)

        mock_analytics_repo = MagicMock()
        mock_analytics_repo.execute_query = AsyncMock(
            return_value=([{"id": 1, "name": "App1"}], ["id", "name"])
        )

        # Create mock db sessions
        mock_db = AsyncMock()
        mock_analytics_db = AsyncMock()

        @asynccontextmanager
        async def mock_get_db_context():
            yield mock_db

        @asynccontextmanager
        async def mock_get_analytics_db_context():
            yield mock_analytics_db

        with (
            patch("app.db.session.get_db_context", mock_get_db_context),
            patch(
                "app.db.session.get_analytics_db_context",
                mock_get_analytics_db_context,
            ),
            patch(
                "app.repositories.ConversationRepository",
                return_value=mock_conv_repo,
            ),
            patch(
                "app.repositories.AnalyticsRepository",
                return_value=mock_analytics_repo,
            ),
        ):
            result = await slack_service.handle_button_action(
                action_id="export_csv",
                value=action_id_value,
                user_id="U123",
                channel_id="C123",
                thread_ts="1234567890.123456",
            )

        assert "csv_content" in result
        assert "csv_filename" in result
        assert "1 rows exported" in result["text"]
        mock_analytics_repo.execute_query.assert_called_once_with(mock_analytics_db, expected_sql)

    @pytest.mark.anyio
    async def test_invalid_action_id_returns_error(self, slack_service):
        """Test that invalid action_id returns appropriate error message."""
        mock_repo = MagicMock()
        mock_repo.get_turn_by_action_id = AsyncMock(return_value=None)

        mock_db = AsyncMock()

        @asynccontextmanager
        async def mock_get_db_context():
            yield mock_db

        with (
            patch("app.db.session.get_db_context", mock_get_db_context),
            patch(
                "app.repositories.ConversationRepository",
                return_value=mock_repo,
            ),
        ):
            result = await slack_service.handle_button_action(
                action_id="show_sql",
                value="nonexistent-action-id",
                user_id="U123",
                channel_id="C123",
                thread_ts="1234567890.123456",
            )

        assert "Could not find the referenced query" in result["text"]
        assert result["blocks"] is None

    @pytest.mark.anyio
    async def test_turn_without_sql_returns_error(self, slack_service):
        """Test that action on turn with no SQL returns appropriate error."""
        action_id_value = "550e8400-e29b-41d4-a716-446655440000"

        # Create mock turn with no SQL
        mock_turn = MagicMock()
        mock_turn.sql_query = None
        mock_turn.action_id = action_id_value

        mock_repo = MagicMock()
        mock_repo.get_turn_by_action_id = AsyncMock(return_value=mock_turn)

        mock_db = AsyncMock()

        @asynccontextmanager
        async def mock_get_db_context():
            yield mock_db

        with (
            patch("app.db.session.get_db_context", mock_get_db_context),
            patch(
                "app.repositories.ConversationRepository",
                return_value=mock_repo,
            ),
        ):
            result = await slack_service.handle_button_action(
                action_id="show_sql",
                value=action_id_value,
                user_id="U123",
                channel_id="C123",
                thread_ts="1234567890.123456",
            )

        assert "No SQL query associated" in result["text"]
        assert result["blocks"] is None

    @pytest.mark.anyio
    async def test_unknown_action_returns_error(self, slack_service):
        """Test that unknown action_id returns error."""
        action_id_value = "550e8400-e29b-41d4-a716-446655440000"

        mock_turn = MagicMock()
        mock_turn.sql_query = "SELECT 1"
        mock_turn.action_id = action_id_value

        mock_repo = MagicMock()
        mock_repo.get_turn_by_action_id = AsyncMock(return_value=mock_turn)

        mock_db = AsyncMock()

        @asynccontextmanager
        async def mock_get_db_context():
            yield mock_db

        with (
            patch("app.db.session.get_db_context", mock_get_db_context),
            patch(
                "app.repositories.ConversationRepository",
                return_value=mock_repo,
            ),
        ):
            result = await slack_service.handle_button_action(
                action_id="unknown_action",
                value=action_id_value,
                user_id="U123",
                channel_id="C123",
                thread_ts="1234567890.123456",
            )

        assert "Unknown action" in result["text"]


class TestGenerateAnalyticsResponseSavesActionId:
    """Tests for generate_analytics_response saving action_id."""

    @pytest.fixture
    def slack_service(self, mock_slack_client):
        """Create a SlackService instance."""
        return SlackService(
            slack_client=mock_slack_client,
            signing_secret="test-secret",
        )

    @pytest.mark.anyio
    async def test_saves_action_id_from_response(self, slack_service):
        """Test that action_id from analytics response is saved to DB."""
        action_id = "550e8400-e29b-41d4-a716-446655440000"

        # Create mock repositories
        mock_conv_repo = MagicMock()
        mock_conv_repo.get_recent_turns = AsyncMock(return_value=[])
        mock_conv_repo.add_turn = AsyncMock()

        # Mock analytics response with action_id
        mock_response = MagicMock()
        mock_response.text = "You have 10 apps"
        mock_response.slack_blocks = [{"type": "section"}]
        mock_response.intent = "analytics_query"
        mock_response.generated_sql = "SELECT COUNT(*) FROM apps"
        mock_response.action_id = action_id
        mock_response.csv_content = None
        mock_response.csv_filename = None
        mock_response.csv_title = None

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_response)

        # Mock db sessions
        mock_db = AsyncMock()
        mock_analytics_db = AsyncMock()

        @asynccontextmanager
        async def mock_get_db_context():
            yield mock_db

        @asynccontextmanager
        async def mock_get_analytics_db_context():
            yield mock_analytics_db

        with (
            patch("app.db.session.get_db_context", mock_get_db_context),
            patch(
                "app.db.session.get_analytics_db_context",
                mock_get_analytics_db_context,
            ),
            patch(
                "app.repositories.ConversationRepository",
                return_value=mock_conv_repo,
            ),
            patch("app.repositories.turns_to_history", return_value=[]),
            patch("app.services.agent.AnalyticsAgentService", return_value=mock_agent),
        ):
            await slack_service.generate_analytics_response(
                message="How many apps?",
                user_id="U123",
                channel_id="C123",
                thread_ts="1234567890.123456",
            )

            # Verify add_turn was called with action_id
            mock_conv_repo.add_turn.assert_called_once()
            call_args = mock_conv_repo.add_turn.call_args
            # Check the action_id was passed (it's in kwargs)
            assert call_args[1].get("action_id") == action_id
            assert call_args[1].get("sql_query") == "SELECT COUNT(*) FROM apps"
            assert call_args[1].get("intent") == "analytics_query"


class TestTruncateBlockText:
    """Tests for _truncate_block_text helper function."""

    def test_no_truncation_needed(self):
        """Text under limit should not be truncated."""
        text = "Short text"
        result = _truncate_block_text(text)
        assert result == text
        assert TRUNCATION_NOTICE not in result

    def test_truncates_long_text(self):
        """Long text should be truncated with notice."""
        text = "A" * 4000  # Exceeds 3000 limit
        result = _truncate_block_text(text)
        assert len(result) <= SLACK_MAX_BLOCK_TEXT_LENGTH
        assert TRUNCATION_NOTICE in result

    def test_truncates_code_block_at_line_boundary(self):
        """Code blocks should be truncated at line boundaries."""
        lines = ["```"] + [f"row {i}: " + "x" * 50 for i in range(100)] + ["```"]
        text = "\n".join(lines)  # Large code block
        result = _truncate_block_text(text)

        assert len(result) <= SLACK_MAX_BLOCK_TEXT_LENGTH
        assert TRUNCATION_NOTICE in result
        # Should still be valid code block (ends with ```)
        assert "```" in result

    def test_truncates_regular_text_at_word_boundary(self):
        """Regular text should be truncated at word boundaries when possible."""
        words = ["word"] * 1000
        text = " ".join(words)  # Long text with spaces
        result = _truncate_block_text(text)

        assert len(result) <= SLACK_MAX_BLOCK_TEXT_LENGTH
        assert TRUNCATION_NOTICE in result


class TestPrepareBlocksForSlack:
    """Tests for _prepare_blocks_for_slack helper function."""

    def test_none_input_returns_none(self):
        """None input should return None."""
        assert _prepare_blocks_for_slack(None) is None

    def test_empty_list_returns_empty(self):
        """Empty list should return empty list."""
        assert _prepare_blocks_for_slack([]) == []

    def test_blocks_under_limit_unchanged(self):
        """Blocks under limits should not be modified."""
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": "Short text"}},
            {"type": "actions", "elements": []},
        ]
        result = _prepare_blocks_for_slack(blocks)
        assert result == blocks

    def test_truncates_oversized_section_block(self):
        """Section blocks exceeding limit should be truncated."""
        long_text = "A" * 4000
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": long_text}}]

        result = _prepare_blocks_for_slack(blocks)

        assert len(result[0]["text"]["text"]) <= SLACK_MAX_BLOCK_TEXT_LENGTH
        assert TRUNCATION_NOTICE in result[0]["text"]["text"]

    def test_truncates_oversized_context_block(self):
        """Context blocks exceeding limit should be truncated."""
        long_text = "A" * 4000
        blocks = [{"type": "context", "elements": [{"type": "mrkdwn", "text": long_text}]}]

        result = _prepare_blocks_for_slack(blocks)

        assert len(result[0]["elements"][0]["text"]) <= SLACK_MAX_BLOCK_TEXT_LENGTH
        assert TRUNCATION_NOTICE in result[0]["elements"][0]["text"]

    def test_limits_block_count(self):
        """Should limit to 50 blocks maximum."""
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"Block {i}"}} for i in range(60)
        ]

        result = _prepare_blocks_for_slack(blocks)

        assert len(result) == 50

    def test_preserves_non_text_blocks(self):
        """Non-text blocks (actions, dividers) should be preserved."""
        blocks = [
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [{"type": "button", "text": {"type": "plain_text", "text": "Click"}}],
            },
        ]

        result = _prepare_blocks_for_slack(blocks)

        assert result == blocks


class TestSendMessageTruncation:
    """Tests for send_message truncation behavior."""

    @pytest.fixture
    def slack_service(self, mock_slack_client):
        """Create a SlackService instance."""
        return SlackService(
            slack_client=mock_slack_client,
            signing_secret="test-secret",
        )

    @pytest.mark.anyio
    async def test_send_message_truncates_long_blocks(self, slack_service):
        """send_message should truncate oversized blocks before sending."""
        long_text = "A" * 4000
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": long_text}}]

        with patch.object(
            slack_service.client, "chat_postMessage", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = MagicMock(data={"ok": True})

            await slack_service.send_message(
                channel="C123",
                text="fallback",
                blocks=blocks,
            )

            # Verify the blocks were truncated before sending
            call_kwargs = mock_post.call_args[1]
            sent_blocks = call_kwargs["blocks"]
            assert len(sent_blocks[0]["text"]["text"]) <= SLACK_MAX_BLOCK_TEXT_LENGTH

    @pytest.mark.anyio
    async def test_send_message_truncates_long_text(self, slack_service):
        """send_message should truncate oversized text field."""
        long_text = "A" * 50000  # Exceeds 40000 limit

        with patch.object(
            slack_service.client, "chat_postMessage", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = MagicMock(data={"ok": True})

            await slack_service.send_message(
                channel="C123",
                text=long_text,
            )

            call_kwargs = mock_post.call_args[1]
            assert len(call_kwargs["text"]) <= 40000
            assert call_kwargs["text"].endswith("...")
