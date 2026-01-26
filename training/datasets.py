"""Dataset management for agent-lightning training.

Provides utilities for loading, augmenting, and splitting evaluation
datasets for use with agent-lightning training.
"""

import random
from typing import Any

from agentlightning import Task


def load_base_dataset() -> list[dict[str, Any]]:
    """Load the base evaluation dataset.

    Converts pydantic-evals test cases into dictionaries suitable
    for agent-lightning training.

    Returns:
        List of task dictionaries with user_query and expected values.
    """
    from evals.analytics_dataset import create_analytics_dataset

    dataset = create_analytics_dataset()
    tasks = []

    for case in dataset.cases:
        task = {
            "id": case.name,
            "user_query": case.inputs.user_query,
            "conversation_history": case.inputs.conversation_history,
            "expected": {},
            "metadata": case.metadata or {},
        }

        # Extract expected values
        if case.expected_output:
            exp = case.expected_output
            task["expected"] = {
                "intent": exp.intent,
                "should_generate_sql": exp.should_generate_sql,
                "should_have_csv": exp.should_have_csv,
                "response_contains": exp.response_contains,
                "sql_contains": exp.sql_contains,
                "response_format": exp.response_format,
            }

        tasks.append(task)

    return tasks


def augment_dataset(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Augment the dataset with variations.

    Creates additional test cases by:
    - Generating question rephrasings
    - Adding SQL query variations
    - Adding aggregation, time-based, and comparison queries
    - Creating follow-up chain variations

    Args:
        tasks: Original task list.

    Returns:
        Augmented task list (includes originals).
    """
    augmented = list(tasks)

    # Rephrasings for simple queries
    rephrasings = {
        "How many apps do we have?": [
            "What's the total number of apps?",
            "Count all apps",
            "Total app count?",
            "How many applications exist?",
        ],
        "How many Android apps do we have?": [
            "Count Android apps",
            "What's the Android app count?",
            "Number of Android applications?",
        ],
        "How many iOS apps do we have?": [
            "Count iOS apps",
            "What's the iOS app count?",
            "Number of iPhone apps?",
        ],
        "Which country generates the most revenue?": [
            "Top revenue country?",
            "What country has highest revenue?",
            "Best performing country by revenue?",
            "Country with maximum revenue?",
        ],
        "List all iOS apps sorted by their popularity": [
            "Show iOS apps by popularity",
            "iOS apps ranked by downloads",
            "Most popular iOS apps?",
        ],
    }

    for task in tasks:
        query = task["user_query"]
        if query in rephrasings:
            for rephrased in rephrasings[query]:
                new_task = task.copy()
                new_task["id"] = f"{task['id']}_rephrased_{len(augmented)}"
                new_task["user_query"] = rephrased
                augmented.append(new_task)

    # === EXPANDED SQL GENERATION CASES ===

    # Aggregation queries
    aggregation_cases = [
        {
            "id": "agg_total_revenue",
            "user_query": "What's the total revenue including both in-app and ads?",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["SUM", "revenue"],
            },
            "metadata": {"category": "aggregation"},
        },
        {
            "id": "agg_average_installs",
            "user_query": "What's the average daily installs across all apps?",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["AVG", "installs"],
            },
            "metadata": {"category": "aggregation"},
        },
        {
            "id": "agg_max_revenue_day",
            "user_query": "What was our highest revenue day?",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["MAX", "revenue"],
            },
            "metadata": {"category": "aggregation"},
        },
        {
            "id": "agg_min_installs",
            "user_query": "What app has the fewest installs?",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["MIN", "installs"],
            },
            "metadata": {"category": "aggregation"},
        },
        {
            "id": "agg_sum_ua_cost",
            "user_query": "Total UA spend across all apps",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["SUM", "ua_cost"],
            },
            "metadata": {"category": "aggregation"},
        },
        {
            "id": "agg_count_countries",
            "user_query": "How many countries do we have data for?",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["COUNT", "DISTINCT", "country"],
            },
            "metadata": {"category": "aggregation"},
        },
    ]
    augmented.extend(aggregation_cases)

    # Time-based queries
    time_cases = [
        {
            "id": "time_this_month",
            "user_query": "Show me revenue for this month",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["revenue", "date"],
            },
            "metadata": {"category": "time_based"},
        },
        {
            "id": "time_last_week",
            "user_query": "Installs from last week",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["installs", "date"],
            },
            "metadata": {"category": "time_based"},
        },
        {
            "id": "time_date_range",
            "user_query": "Show installs from January 1st to January 15th 2025",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["date", "2025"],
            },
            "metadata": {"category": "time_based"},
        },
        {
            "id": "time_yesterday",
            "user_query": "How many installs did we get yesterday?",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["installs", "date"],
            },
            "metadata": {"category": "time_based"},
        },
        {
            "id": "time_year_to_date",
            "user_query": "Year to date revenue",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["revenue", "date"],
            },
            "metadata": {"category": "time_based"},
        },
        {
            "id": "time_q4_2024",
            "user_query": "Q4 2024 performance metrics",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["date", "2024"],
            },
            "metadata": {"category": "time_based"},
        },
    ]
    augmented.extend(time_cases)

    # Comparison queries
    comparison_cases = [
        {
            "id": "compare_platforms",
            "user_query": "Compare iOS and Android revenue",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["platform", "GROUP BY"],
            },
            "metadata": {"category": "comparison"},
        },
        {
            "id": "compare_apps",
            "user_query": "Compare installs between Game A and Game B",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["app_name", "installs"],
            },
            "metadata": {"category": "comparison"},
        },
        {
            "id": "compare_months",
            "user_query": "Compare January vs December revenue",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["revenue", "date"],
            },
            "metadata": {"category": "comparison"},
        },
        {
            "id": "compare_countries_installs",
            "user_query": "USA vs UK installs comparison",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["country", "installs"],
            },
            "metadata": {"category": "comparison"},
        },
    ]
    augmented.extend(comparison_cases)

    # Ranking/Top-N queries
    ranking_cases = [
        {
            "id": "rank_top5_installs",
            "user_query": "Top 5 apps by installs",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["LIMIT", "ORDER BY", "installs"],
            },
            "metadata": {"category": "ranking"},
        },
        {
            "id": "rank_top10_revenue",
            "user_query": "Top 10 revenue generating apps",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["LIMIT", "ORDER BY", "revenue"],
            },
            "metadata": {"category": "ranking"},
        },
        {
            "id": "rank_bottom5_ua",
            "user_query": "5 apps with lowest UA cost",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["LIMIT", "ORDER BY", "ua_cost"],
            },
            "metadata": {"category": "ranking"},
        },
        {
            "id": "rank_top_countries",
            "user_query": "Top 3 countries by revenue",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["LIMIT", "country", "revenue"],
            },
            "metadata": {"category": "ranking"},
        },
        {
            "id": "rank_best_performing",
            "user_query": "Best performing app this month",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["ORDER BY", "LIMIT"],
            },
            "metadata": {"category": "ranking"},
        },
    ]
    augmented.extend(ranking_cases)

    # Filter/specific queries
    filter_cases = [
        {
            "id": "filter_specific_app",
            "user_query": "Show me all metrics for Paint app",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["app_name", "Paint"],
            },
            "metadata": {"category": "filter"},
        },
        {
            "id": "filter_country_usa",
            "user_query": "Revenue from USA only",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["country", "USA", "revenue"],
            },
            "metadata": {"category": "filter"},
        },
        {
            "id": "filter_android_games",
            "user_query": "All Android apps with more than 1000 installs",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["Android", "installs", "1000"],
            },
            "metadata": {"category": "filter"},
        },
        {
            "id": "filter_high_revenue",
            "user_query": "Apps with revenue over $10000",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["revenue", "10000"],
            },
            "metadata": {"category": "filter"},
        },
        {
            "id": "filter_multiple",
            "user_query": "iOS apps in USA with positive revenue",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["iOS", "USA", "revenue"],
            },
            "metadata": {"category": "filter"},
        },
    ]
    augmented.extend(filter_cases)

    # Group by queries
    groupby_cases = [
        {
            "id": "group_by_country",
            "user_query": "Revenue breakdown by country",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["country", "GROUP BY", "revenue"],
            },
            "metadata": {"category": "groupby"},
        },
        {
            "id": "group_by_platform",
            "user_query": "Installs by platform",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["platform", "GROUP BY", "installs"],
            },
            "metadata": {"category": "groupby"},
        },
        {
            "id": "group_by_app",
            "user_query": "Total revenue per app",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["app_name", "GROUP BY", "revenue"],
            },
            "metadata": {"category": "groupby"},
        },
        {
            "id": "group_by_date",
            "user_query": "Daily installs trend",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["date", "GROUP BY", "installs"],
            },
            "metadata": {"category": "groupby"},
        },
        {
            "id": "group_by_month",
            "user_query": "Monthly revenue breakdown",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["GROUP BY", "revenue"],
            },
            "metadata": {"category": "groupby"},
        },
    ]
    augmented.extend(groupby_cases)

    # Net/calculated metrics
    calculated_cases = [
        {
            "id": "calc_net_revenue",
            "user_query": "Show me net revenue after UA costs",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["revenue", "ua_cost"],
            },
            "metadata": {"category": "calculated"},
        },
        {
            "id": "calc_roi",
            "user_query": "What's the ROI for each app?",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["revenue", "ua_cost"],
            },
            "metadata": {"category": "calculated"},
        },
        {
            "id": "calc_revenue_per_install",
            "user_query": "Revenue per install by app",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["revenue", "installs"],
            },
            "metadata": {"category": "calculated"},
        },
        {
            "id": "calc_ads_percentage",
            "user_query": "What percentage of revenue comes from ads?",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["ads_revenue", "revenue"],
            },
            "metadata": {"category": "calculated"},
        },
    ]
    augmented.extend(calculated_cases)

    # Simple/basic queries
    basic_cases = [
        {
            "id": "basic_list_apps",
            "user_query": "List all apps",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["SELECT", "app_name"],
            },
            "metadata": {"category": "basic"},
        },
        {
            "id": "basic_list_countries",
            "user_query": "What countries do we operate in?",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["SELECT", "country"],
            },
            "metadata": {"category": "basic"},
        },
        {
            "id": "basic_total_installs",
            "user_query": "Total installs",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["SUM", "installs"],
            },
            "metadata": {"category": "basic"},
        },
        {
            "id": "basic_all_revenue",
            "user_query": "Show all revenue",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["SELECT", "revenue"],
            },
            "metadata": {"category": "basic"},
        },
    ]
    augmented.extend(basic_cases)

    # Complex/multi-part queries
    complex_cases = [
        {
            "id": "complex_top_app_per_country",
            "user_query": "Which app is most popular in each country?",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["country", "app_name", "installs"],
            },
            "metadata": {"category": "complex"},
        },
        {
            "id": "complex_growth_analysis",
            "user_query": "Which apps had the biggest change in UA spend comparing Jan 2025 to Dec 2024?",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["ua_cost", "2025", "2024"],
            },
            "metadata": {"category": "complex"},
        },
        {
            "id": "complex_market_share",
            "user_query": "What's our market share by platform?",
            "expected": {
                "intent": "analytics_query",
                "should_generate_sql": True,
                "sql_contains": ["platform", "GROUP BY"],
            },
            "metadata": {"category": "complex"},
        },
    ]
    augmented.extend(complex_cases)

    # Off-topic variations
    off_topic_cases = [
        {
            "id": "off_topic_stock",
            "user_query": "What's Apple's stock price?",
            "expected": {
                "intent": "off_topic",
                "should_generate_sql": False,
            },
            "metadata": {"category": "off_topic"},
        },
        {
            "id": "off_topic_coding",
            "user_query": "Write me a Python script",
            "expected": {
                "intent": "off_topic",
                "should_generate_sql": False,
            },
            "metadata": {"category": "off_topic"},
        },
        {
            "id": "off_topic_news",
            "user_query": "What's happening in the news?",
            "expected": {
                "intent": "off_topic",
                "should_generate_sql": False,
            },
            "metadata": {"category": "off_topic"},
        },
        {
            "id": "off_topic_recipe",
            "user_query": "How do I make pasta?",
            "expected": {
                "intent": "off_topic",
                "should_generate_sql": False,
            },
            "metadata": {"category": "off_topic"},
        },
        {
            "id": "off_topic_translate",
            "user_query": "Translate hello to Spanish",
            "expected": {
                "intent": "off_topic",
                "should_generate_sql": False,
            },
            "metadata": {"category": "off_topic"},
        },
    ]
    augmented.extend(off_topic_cases)

    return augmented


def split_dataset(
    tasks: list[dict[str, Any]],
    train_ratio: float = 0.7,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split dataset into training and validation sets.

    Args:
        tasks: Full task list.
        train_ratio: Fraction of data for training (default 0.7).
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (train_tasks, val_tasks).
    """
    random.seed(seed)
    shuffled = tasks.copy()
    random.shuffle(shuffled)

    split_idx = int(len(shuffled) * train_ratio)
    return shuffled[:split_idx], shuffled[split_idx:]


def load_training_data(
    augment: bool = True,
    train_ratio: float = 0.7,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load and prepare training data.

    Convenience function that loads base dataset, optionally augments it,
    and splits into train/validation sets.

    Args:
        augment: Whether to augment the dataset.
        train_ratio: Fraction of data for training.
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (train_data, val_data).
    """
    tasks = load_base_dataset()

    if augment:
        tasks = augment_dataset(tasks)

    return split_dataset(tasks, train_ratio, seed)


def tasks_to_agl_format(tasks: list[dict[str, Any]]) -> list[Task]:
    """Convert tasks to agent-lightning Task format.

    Args:
        tasks: List of task dictionaries.

    Returns:
        List of agent-lightning Task objects.
    """
    agl_tasks = []
    for task in tasks:
        agl_task = Task(
            task_id=task["id"],
            sample=task,
            mode="train",
        )
        agl_tasks.append(agl_task)
    return agl_tasks


def get_sql_focused_dataset() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Get a dataset focused on SQL generation cases.

    Filters to only include analytics_query and follow_up intents
    where SQL generation is expected.

    Returns:
        Tuple of (train_data, val_data) with SQL-focused cases.
    """
    train_data, val_data = load_training_data(augment=True)

    def is_sql_case(task: dict) -> bool:
        expected = task.get("expected", {})
        return expected.get("should_generate_sql", False) is True

    train_sql = [t for t in train_data if is_sql_case(t)]
    val_sql = [t for t in val_data if is_sql_case(t)]

    return train_sql, val_sql
