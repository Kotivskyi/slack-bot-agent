"""Tests for conversation history persistence in analytics chatbot."""

from datetime import datetime
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

    def test_export_csv_updates_history_no_cache(self):
        """export_csv should update history even when no cache available."""
        state = {
            "user_query": "export csv",
            "conversation_history": [],
            "query_cache": {},
        }

        result = export_csv(state)

        assert "conversation_history" in result
        assert len(result["conversation_history"]) == 1
        assert result["conversation_history"][0]["user"] == "export csv"
        assert "No recent query results" in result["conversation_history"][0]["bot"]

    def test_export_csv_updates_history_with_cache(self):
        """export_csv should update history when exporting data."""
        state = {
            "user_query": "export csv",
            "conversation_history": [],
            "query_cache": {
                "query-1": {
                    "sql": "SELECT * FROM apps",
                    "results": [{"id": 1, "name": "App1"}],
                    "timestamp": datetime.now(),
                    "natural_query": "list all apps",
                    "assumptions": [],
                }
            },
            "current_query_id": "query-1",
            "referenced_query_id": None,
        }

        result = export_csv(state)

        assert "conversation_history" in result
        assert len(result["conversation_history"]) == 1
        assert "CSV Export Complete" in result["conversation_history"][0]["bot"]

    def test_retrieve_sql_updates_history_no_cache(self):
        """retrieve_sql should update history even when no cache available."""
        state = {
            "user_query": "show sql",
            "conversation_history": [],
            "query_cache": {},
        }

        result = retrieve_sql(state)

        assert "conversation_history" in result
        assert len(result["conversation_history"]) == 1
        assert "No SQL queries in history" in result["conversation_history"][0]["bot"]

    def test_retrieve_sql_updates_history_with_cache(self):
        """retrieve_sql should update history when showing SQL."""
        state = {
            "user_query": "show sql",
            "conversation_history": [],
            "query_cache": {
                "query-1": {
                    "sql": "SELECT COUNT(*) FROM apps",
                    "results": [{"count": 10}],
                    "timestamp": datetime.now(),
                    "natural_query": "count apps",
                    "assumptions": [],
                }
            },
            "referenced_query_id": "query-1",
        }

        result = retrieve_sql(state)

        assert "conversation_history" in result
        assert len(result["conversation_history"]) == 1
        assert "SQL Query" in result["conversation_history"][0]["bot"]


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

    @patch("app.agents.analytics_chatbot.nodes.intent_router.ChatOpenAI")
    @patch("app.agents.analytics_chatbot.nodes.intent_router.INTENT_CLASSIFIER_PROMPT")
    def test_intent_router_formats_history_for_llm(self, mock_prompt, mock_llm_class):
        """Intent router should format conversation history for LLM classification."""
        from app.agents.analytics_chatbot.nodes.intent_router import classify_intent

        # Mock LLM and chain
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm

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

        classify_intent(state)

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

        result = classify_intent(state)

        assert result["intent"] == "export_csv"
        assert result["confidence"] == 0.95
