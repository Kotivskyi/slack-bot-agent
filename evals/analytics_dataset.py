"""Dataset for analytics chatbot evaluation.

Defines test cases covering all requirements from AI_Engineer_Test_Task.md:
1. Simple analytics queries
2. Follow-up questions with context
3. Complex queries (table responses)
4. CSV export requests
5. SQL statement retrieval
6. Off-topic decline
7. Intent classification accuracy
"""

from pydantic_evals import Case, Dataset

from evals.evaluator import (
    CSVExport,
    IntentMatch,
    ResponseContains,
    ResponseFormatMatch,
    SQLContains,
    SQLGenerated,
    create_analytics_judge,
)
from evals.schemas import AnalyticsExpected, AnalyticsInput, AnalyticsOutput


def create_analytics_dataset() -> Dataset[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]:
    """Create the full analytics evaluation dataset.

    Returns:
        Dataset containing test cases for analytics chatbot evaluation.
    """
    dataset: Dataset[AnalyticsInput, AnalyticsOutput, AnalyticsExpected] = Dataset(
        cases=[
            # === 1. Simple Analytics Queries ===
            Case(
                name="simple_count_apps",
                inputs=AnalyticsInput(user_query="How many apps do we have?"),
                expected_output=AnalyticsExpected(
                    intent="analytics_query",
                    should_generate_sql=True,
                    sql_contains=["SELECT", "COUNT", "app_name"],
                    response_format="simple",
                ),
                metadata={"category": "simple_query"},
            ),
            Case(
                name="simple_android_count",
                inputs=AnalyticsInput(user_query="How many Android apps do we have?"),
                expected_output=AnalyticsExpected(
                    intent="analytics_query",
                    should_generate_sql=True,
                    sql_contains=["SELECT", "COUNT", "platform", "Android"],
                    response_format="simple",
                ),
                metadata={"category": "simple_query"},
            ),
            Case(
                name="simple_ios_count",
                inputs=AnalyticsInput(user_query="How many iOS apps do we have?"),
                expected_output=AnalyticsExpected(
                    intent="analytics_query",
                    should_generate_sql=True,
                    sql_contains=["SELECT", "COUNT", "platform", "iOS"],
                    response_format="simple",
                ),
                metadata={"category": "simple_query"},
            ),
            # === 2. Follow-up Questions ===
            Case(
                name="follow_up_ios_after_android",
                inputs=AnalyticsInput(
                    user_query="What about iOS?",
                    conversation_history=[
                        {"user": "How many Android apps do we have?", "bot": "We have 5 Android apps."},
                    ],
                ),
                expected_output=AnalyticsExpected(
                    intent="follow_up",
                    should_generate_sql=True,
                    sql_contains=["iOS"],
                ),
                metadata={"category": "follow_up"},
            ),
            Case(
                name="follow_up_last_month",
                inputs=AnalyticsInput(
                    user_query="And last month?",
                    conversation_history=[
                        {"user": "What was total revenue this month?", "bot": "Total revenue this month is $50,000."},
                    ],
                ),
                expected_output=AnalyticsExpected(
                    intent="follow_up",
                    should_generate_sql=True,
                ),
                metadata={"category": "follow_up"},
            ),
            # === 3. Complex Queries (Table Responses) ===
            Case(
                name="complex_top_revenue_country",
                inputs=AnalyticsInput(user_query="Which country generates the most revenue?"),
                expected_output=AnalyticsExpected(
                    intent="analytics_query",
                    should_generate_sql=True,
                    sql_contains=["SELECT", "country", "revenue", "ORDER BY"],
                    response_format="table",
                ),
                metadata={"category": "complex_query"},
            ),
            Case(
                name="complex_ios_apps_popularity",
                inputs=AnalyticsInput(user_query="List all iOS apps sorted by their popularity"),
                expected_output=AnalyticsExpected(
                    intent="analytics_query",
                    should_generate_sql=True,
                    sql_contains=["SELECT", "iOS", "ORDER BY"],
                    response_format="table",
                ),
                metadata={"category": "complex_query"},
            ),
            Case(
                name="complex_ua_spend_change",
                inputs=AnalyticsInput(
                    user_query="Which apps had the biggest change in UA spend comparing Jan 2025 to Dec 2024?"
                ),
                expected_output=AnalyticsExpected(
                    intent="analytics_query",
                    should_generate_sql=True,
                    sql_contains=["SELECT", "ua_cost"],
                    response_format="table",
                ),
                metadata={"category": "complex_query"},
            ),
            Case(
                name="complex_revenue_by_platform",
                inputs=AnalyticsInput(user_query="Show me total revenue by platform"),
                expected_output=AnalyticsExpected(
                    intent="analytics_query",
                    should_generate_sql=True,
                    sql_contains=["SELECT", "platform", "revenue", "GROUP BY"],
                    response_format="table",
                ),
                metadata={"category": "complex_query"},
            ),
            # === 4. CSV Export Requests ===
            Case(
                name="export_csv_keyword",
                inputs=AnalyticsInput(
                    user_query="export csv",
                    conversation_history=[
                        {"user": "How many apps do we have?", "bot": "We have 10 apps total."},
                    ],
                ),
                expected_output=AnalyticsExpected(
                    intent="export_csv",
                    should_generate_sql=False,  # Should reuse existing SQL
                    should_have_csv=True,
                ),
                metadata={"category": "csv_export"},
            ),
            Case(
                name="export_download_request",
                inputs=AnalyticsInput(
                    user_query="download the data",
                    conversation_history=[
                        {"user": "Show revenue by country", "bot": "Here is revenue by country..."},
                    ],
                ),
                expected_output=AnalyticsExpected(
                    intent="export_csv",
                    should_have_csv=True,
                ),
                metadata={"category": "csv_export"},
            ),
            # === 5. SQL Statement Retrieval ===
            Case(
                name="show_sql_keyword",
                inputs=AnalyticsInput(
                    user_query="show me the sql",
                    conversation_history=[
                        {"user": "How many apps do we have?", "bot": "We have 10 apps."},
                    ],
                ),
                expected_output=AnalyticsExpected(
                    intent="show_sql",
                    should_generate_sql=False,  # Should retrieve existing SQL
                    response_contains=["SELECT"],
                ),
                metadata={"category": "show_sql"},
            ),
            Case(
                name="show_sql_query_request",
                inputs=AnalyticsInput(
                    user_query="what sql query did you use?",
                    conversation_history=[
                        {"user": "Which country has most installs?", "bot": "USA has the most installs."},
                    ],
                ),
                expected_output=AnalyticsExpected(
                    intent="show_sql",
                    response_contains=["SELECT"],
                ),
                metadata={"category": "show_sql"},
            ),
            # === 6. Off-topic Decline ===
            Case(
                name="off_topic_weather",
                inputs=AnalyticsInput(user_query="What's the weather like today?"),
                expected_output=AnalyticsExpected(
                    intent="off_topic",
                    should_generate_sql=False,
                    response_contains=["app", "analytics"],  # Should mention what it can help with
                ),
                metadata={"category": "off_topic"},
            ),
            Case(
                name="off_topic_joke",
                inputs=AnalyticsInput(user_query="Tell me a joke"),
                expected_output=AnalyticsExpected(
                    intent="off_topic",
                    should_generate_sql=False,
                ),
                metadata={"category": "off_topic"},
            ),
            Case(
                name="off_topic_general_chat",
                inputs=AnalyticsInput(user_query="How are you doing?"),
                expected_output=AnalyticsExpected(
                    intent="off_topic",
                    should_generate_sql=False,
                ),
                metadata={"category": "off_topic"},
            ),
            # === 7. Additional Intent Classification ===
            Case(
                name="intent_total_installs",
                inputs=AnalyticsInput(user_query="What are total installs across all apps?"),
                expected_output=AnalyticsExpected(
                    intent="analytics_query",
                    should_generate_sql=True,
                    sql_contains=["SELECT", "installs"],
                ),
                metadata={"category": "intent_classification"},
            ),
            Case(
                name="intent_ads_revenue",
                inputs=AnalyticsInput(user_query="How much ads revenue did we make last month?"),
                expected_output=AnalyticsExpected(
                    intent="analytics_query",
                    should_generate_sql=True,
                    sql_contains=["SELECT", "ads_revenue"],
                ),
                metadata={"category": "intent_classification"},
            ),
        ]
    )

    # Add evaluators
    dataset.add_evaluator(IntentMatch())
    dataset.add_evaluator(SQLGenerated())
    dataset.add_evaluator(SQLContains())
    dataset.add_evaluator(ResponseContains())
    dataset.add_evaluator(CSVExport())
    dataset.add_evaluator(ResponseFormatMatch())
    dataset.add_evaluator(create_analytics_judge())

    return dataset


def create_quick_analytics_dataset() -> (
    Dataset[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]
):
    """Create a quick analytics dataset for fast iteration.

    Returns:
        Dataset with a subset of key test cases.
    """
    dataset: Dataset[AnalyticsInput, AnalyticsOutput, AnalyticsExpected] = Dataset(
        cases=[
            Case(
                name="simple_count_apps",
                inputs=AnalyticsInput(user_query="How many apps do we have?"),
                expected_output=AnalyticsExpected(
                    intent="analytics_query",
                    should_generate_sql=True,
                ),
                metadata={"category": "simple_query"},
            ),
            Case(
                name="off_topic_weather",
                inputs=AnalyticsInput(user_query="What's the weather?"),
                expected_output=AnalyticsExpected(
                    intent="off_topic",
                    should_generate_sql=False,
                ),
                metadata={"category": "off_topic"},
            ),
            Case(
                name="show_sql_keyword",
                inputs=AnalyticsInput(
                    user_query="show sql",
                    conversation_history=[
                        {"user": "How many apps?", "bot": "10 apps."},
                    ],
                ),
                expected_output=AnalyticsExpected(
                    intent="show_sql",
                ),
                metadata={"category": "show_sql"},
            ),
        ]
    )

    dataset.add_evaluator(IntentMatch())
    dataset.add_evaluator(SQLGenerated())
    dataset.add_evaluator(create_analytics_judge())

    return dataset
