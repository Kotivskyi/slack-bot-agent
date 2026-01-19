"""Tests for conversation history persistence in analytics chatbot."""

from unittest.mock import MagicMock, patch

from app.agents.analytics_chatbot.nodes.csv_export import export_csv
from app.agents.analytics_chatbot.nodes.decline import polite_decline
from app.agents.analytics_chatbot.nodes.error_handler import handle_error
from app.agents.analytics_chatbot.nodes.response_formatter import format_slack_response
from app.agents.analytics_chatbot.nodes.sql_retrieval import retrieve_sql


class TestTerminalNodesUpdateHistory:
    """Test that all terminal nodes update conversation_history."""

    def test_format_slack_response_updates_history(self):
        """format_slack_response should append to conversation_history."""
        state = {
            "user_query": "How many apps do we have?",
            "conversation_history": [{"user": "previous question", "bot": "previous answer"}],
            "response_text": "You have 10 apps in total.",
            "response_format": "simple",
            "query_results": None,
            "assumptions_made": [],
            "current_query_id": None,
        }

        result = format_slack_response(state)

        assert "conversation_history" in result
        assert len(result["conversation_history"]) == 2
        assert result["conversation_history"][0] == {
            "user": "previous question",
            "bot": "previous answer",
        }
        assert result["conversation_history"][1]["user"] == "How many apps do we have?"
        assert result["conversation_history"][1]["bot"] == "You have 10 apps in total."

    def test_format_slack_response_creates_history_if_empty(self):
        """format_slack_response should create history if none exists."""
        state = {
            "user_query": "First question",
            "conversation_history": [],
            "response_text": "First answer",
            "response_format": "simple",
            "query_results": None,
            "assumptions_made": [],
            "current_query_id": None,
        }

        result = format_slack_response(state)

        assert len(result["conversation_history"]) == 1
        assert result["conversation_history"][0]["user"] == "First question"
        assert result["conversation_history"][0]["bot"] == "First answer"

    def test_polite_decline_updates_history(self):
        """polite_decline should append to conversation_history."""
        state = {
            "user_query": "What's the weather?",
            "conversation_history": [],
        }

        result = polite_decline(state)

        assert "conversation_history" in result
        assert len(result["conversation_history"]) == 1
        assert result["conversation_history"][0]["user"] == "What's the weather?"
        assert "app portfolio analytics" in result["conversation_history"][0]["bot"]

    def test_handle_error_updates_history(self):
        """handle_error should append to conversation_history."""
        state = {
            "user_query": "Show me invalid data",
            "sql_error": "Execution failed",
            "conversation_history": [{"user": "q1", "bot": "a1"}],
            "retry_count": 0,
        }

        result = handle_error(state)

        assert "conversation_history" in result
        assert len(result["conversation_history"]) == 2
        assert result["conversation_history"][1]["user"] == "Show me invalid data"
        assert "couldn't answer" in result["conversation_history"][1]["bot"]

    def test_export_csv_updates_history_no_results(self):
        """export_csv should update history even when no results available."""
        state = {
            "user_query": "export csv",
            "conversation_history": [],
            "query_results": None,
        }

        result = export_csv(state)

        assert "conversation_history" in result
        assert len(result["conversation_history"]) == 1
        assert result["conversation_history"][0]["user"] == "export csv"
        assert "No recent query results" in result["conversation_history"][0]["bot"]

    def test_export_csv_updates_history_with_results(self):
        """export_csv should update history when exporting data."""
        state = {
            "user_query": "export csv",
            "conversation_history": [],
            "query_results": [{"id": 1, "name": "App1"}],
            "resolved_query": "list all apps",
        }

        result = export_csv(state)

        assert "conversation_history" in result
        assert len(result["conversation_history"]) == 1
        assert "CSV Export Complete" in result["conversation_history"][0]["bot"]

    def test_retrieve_sql_updates_history_no_sql(self):
        """retrieve_sql should update history even when no SQL available."""
        state = {
            "user_query": "show sql",
            "conversation_history": [],
            "generated_sql": None,
        }

        result = retrieve_sql(state)

        assert "conversation_history" in result
        assert len(result["conversation_history"]) == 1
        assert "No SQL queries in history" in result["conversation_history"][0]["bot"]

    def test_retrieve_sql_updates_history_with_sql(self):
        """retrieve_sql should update history when showing SQL."""
        state = {
            "user_query": "show sql",
            "conversation_history": [],
            "generated_sql": "SELECT COUNT(*) FROM apps",
            "resolved_query": "count apps",
        }

        result = retrieve_sql(state)

        assert "conversation_history" in result
        assert len(result["conversation_history"]) == 1
        assert "SQL Query" in result["conversation_history"][0]["bot"]


class TestActionIdGeneration:
    """Test that action_id is properly generated for button actions."""

    def test_format_slack_response_generates_action_id_with_results(self):
        """format_slack_response should generate action_id UUID when query_results exist."""
        state = {
            "user_query": "How many apps?",
            "conversation_history": [],
            "response_text": "You have 10 apps.",
            "response_format": "table",
            "query_results": [{"count": 10}],
            "column_names": ["count"],
            "assumptions_made": [],
            "current_query_id": "some-hash",
        }

        result = format_slack_response(state)

        assert "action_id" in result
        assert result["action_id"] is not None
        # Verify it's a valid UUID format (36 chars with hyphens)
        assert len(result["action_id"]) == 36
        assert result["action_id"].count("-") == 4

    def test_format_slack_response_no_action_id_without_results(self):
        """format_slack_response should not generate action_id when no query_results."""
        state = {
            "user_query": "Hello",
            "conversation_history": [],
            "response_text": "Hi there!",
            "response_format": "simple",
            "query_results": None,
            "assumptions_made": [],
            "current_query_id": None,
        }

        result = format_slack_response(state)

        assert "action_id" in result
        assert result["action_id"] is None

    def test_format_slack_response_buttons_use_action_id(self):
        """format_slack_response should use action_id as button value."""
        state = {
            "user_query": "How many apps?",
            "conversation_history": [],
            "response_text": "You have 10 apps.",
            "response_format": "table",
            "query_results": [{"count": 10}],
            "column_names": ["count"],
            "assumptions_made": [],
            "current_query_id": "some-hash",
        }

        result = format_slack_response(state)

        # Find the actions block
        actions_block = None
        for block in result["slack_blocks"]:
            if block.get("type") == "actions":
                actions_block = block
                break

        assert actions_block is not None
        # Verify both buttons use the same action_id
        export_button = actions_block["elements"][0]
        show_sql_button = actions_block["elements"][1]

        assert export_button["value"] == result["action_id"]
        assert show_sql_button["value"] == result["action_id"]
        assert export_button["action_id"] == "export_csv"
        assert show_sql_button["action_id"] == "show_sql"

    def test_format_slack_response_unique_action_ids(self):
        """Each call to format_slack_response should generate a unique action_id."""
        state = {
            "user_query": "How many apps?",
            "conversation_history": [],
            "response_text": "You have 10 apps.",
            "response_format": "table",
            "query_results": [{"count": 10}],
            "column_names": ["count"],
            "assumptions_made": [],
            "current_query_id": "some-hash",
        }

        result1 = format_slack_response(state)
        result2 = format_slack_response(state)

        assert result1["action_id"] != result2["action_id"]


class TestHistoryTruncation:
    """Test that bot responses are truncated in history."""

    def test_long_response_truncated_in_history(self):
        """Bot responses longer than 500 chars should be truncated."""
        long_response = "A" * 1000
        state = {
            "user_query": "question",
            "conversation_history": [],
            "response_text": long_response,
            "response_format": "simple",
            "query_results": None,
            "assumptions_made": [],
            "current_query_id": None,
        }

        result = format_slack_response(state)

        assert len(result["conversation_history"][0]["bot"]) == 500


class TestHistoryPreservation:
    """Test that existing history is preserved when appending."""

    def test_existing_history_not_mutated(self):
        """Original history list should not be mutated."""
        original_history = [{"user": "q1", "bot": "a1"}]
        state = {
            "user_query": "q2",
            "conversation_history": original_history,
            "response_text": "a2",
            "response_format": "simple",
            "query_results": None,
            "assumptions_made": [],
            "current_query_id": None,
        }

        result = format_slack_response(state)

        # Original should be unchanged
        assert len(original_history) == 1
        # Result should have new entry
        assert len(result["conversation_history"]) == 2

    def test_history_accumulates_across_multiple_calls(self):
        """History should accumulate correctly across multiple node calls."""
        # Simulate first call
        state1 = {
            "user_query": "first question",
            "conversation_history": [],
            "response_text": "first answer",
            "response_format": "simple",
            "query_results": None,
            "assumptions_made": [],
            "current_query_id": None,
        }
        result1 = format_slack_response(state1)

        # Simulate second call with history from first
        state2 = {
            "user_query": "second question",
            "conversation_history": result1["conversation_history"],
            "response_text": "second answer",
            "response_format": "simple",
            "query_results": None,
            "assumptions_made": [],
            "current_query_id": None,
        }
        result2 = format_slack_response(state2)

        # Simulate third call
        state3 = {
            "user_query": "third question",
            "conversation_history": result2["conversation_history"],
            "response_text": "third answer",
            "response_format": "simple",
            "query_results": None,
            "assumptions_made": [],
            "current_query_id": None,
        }
        result3 = format_slack_response(state3)

        assert len(result3["conversation_history"]) == 3
        assert result3["conversation_history"][0]["user"] == "first question"
        assert result3["conversation_history"][1]["user"] == "second question"
        assert result3["conversation_history"][2]["user"] == "third question"


class TestIntentRouterUsesHistory:
    """Test that intent router properly uses conversation history."""

    @patch("app.agents.analytics_chatbot.nodes.intent_router.INTENT_CLASSIFIER_PROMPT")
    def test_intent_router_formats_history_for_llm(self, mock_prompt):
        """Intent router should format conversation history for LLM classification."""
        from app.agents.analytics_chatbot.nodes.intent_router import classify_intent

        # Create a mock response with proper content attribute
        mock_response = MagicMock()
        mock_response.content = '{"intent": "follow_up", "confidence": 0.9}'

        # Create a mock chain that captures the input
        captured_input = {}

        def capture_invoke(inputs):
            captured_input.update(inputs)
            return mock_response

        mock_chain = MagicMock()
        mock_chain.invoke = capture_invoke

        # Mock the prompt | llm chain creation
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)

        state = {
            "user_query": "also include country",  # Follow-up question
            "conversation_history": [
                {"user": "Show me revenue by app", "bot": "Here's the revenue breakdown..."},
                {"user": "What about last month?", "bot": "Last month's data shows..."},
            ],
        }

        # Create mock LLM and pass via config
        mock_llm = MagicMock()
        config = {"configurable": {"thread_id": "test-thread", "llm_client": mock_llm}}
        classify_intent(state, config)

        # Verify history was passed to LLM
        assert "history" in captured_input
        assert "Show me revenue by app" in captured_input["history"]
        assert "What about last month?" in captured_input["history"]

    def test_intent_router_handles_empty_history(self):
        """Intent router should handle empty conversation history gracefully."""
        from app.agents.analytics_chatbot.nodes.intent_router import classify_intent

        # This should trigger keyword match, not LLM
        state = {
            "user_query": "export csv",
            "conversation_history": [],
        }

        # Pass config with configurable (required by updated function signature)
        config = {"configurable": {"thread_id": "test-thread"}}
        result = classify_intent(state, config)

        assert result["intent"] == "export_csv"
        assert result["confidence"] == 0.95
