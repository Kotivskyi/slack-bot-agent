"""Reward functions for agent-lightning training.

Converts existing pydantic-evals evaluators to reward functions
that can be used by agent-lightning's APO algorithm.
"""

from typing import Any


def intent_classification_reward(result: dict[str, Any], expected: dict[str, Any]) -> float:
    """Reward for correct intent classification.

    Args:
        result: The chatbot output containing 'intent' key.
        expected: Expected values containing 'intent' key.

    Returns:
        1.0 if intent matches, 0.0 otherwise.
    """
    if expected.get("intent") is None:
        return 1.0

    return 1.0 if result.get("intent") == expected.get("intent") else 0.0


def sql_generated_reward(result: dict[str, Any], expected: dict[str, Any]) -> float:
    """Reward for SQL generation matching expectation.

    Args:
        result: The chatbot output containing 'generated_sql' key.
        expected: Expected values containing 'should_generate_sql' key.

    Returns:
        1.0 if SQL presence matches expectation, 0.0 otherwise.
    """
    if expected.get("should_generate_sql") is None:
        return 1.0

    has_sql = result.get("generated_sql") is not None and len(result.get("generated_sql", "")) > 0
    return 1.0 if has_sql == expected.get("should_generate_sql") else 0.0


def sql_contains_reward(result: dict[str, Any], expected: dict[str, Any]) -> float:
    """Reward for SQL containing expected keywords/clauses.

    Args:
        result: The chatbot output containing 'generated_sql' key.
        expected: Expected values containing 'sql_contains' list.

    Returns:
        Score between 0 and 1 based on substring matches.
    """
    sql_keywords = expected.get("sql_contains", [])
    if not sql_keywords:
        return 1.0

    generated_sql = result.get("generated_sql", "")
    if not generated_sql:
        return 0.0

    sql_upper = generated_sql.upper()
    matches = sum(1 for kw in sql_keywords if kw.upper() in sql_upper)
    return matches / len(sql_keywords)


def response_contains_reward(result: dict[str, Any], expected: dict[str, Any]) -> float:
    """Reward for response containing expected substrings.

    Args:
        result: The chatbot output containing 'text' key.
        expected: Expected values containing 'response_contains' list.

    Returns:
        Score between 0 and 1 based on substring matches.
    """
    response_keywords = expected.get("response_contains", [])
    if not response_keywords:
        return 1.0

    response_text = result.get("text", "")
    response_lower = response_text.lower()
    matches = sum(1 for kw in response_keywords if kw.lower() in response_lower)
    return matches / len(response_keywords)


def sql_execution_reward(result: dict[str, Any], expected: dict[str, Any]) -> float:
    """Reward for successful SQL execution.

    This provides a bonus for SQL that executed without errors
    and returned results.

    Args:
        result: The chatbot output with 'sql_error' and 'query_results' keys.
        expected: Expected values (not used but kept for signature consistency).

    Returns:
        1.0 if SQL executed successfully with results, 0.5 if no results, 0.0 if error.
    """
    # If there was an SQL error, return 0
    if result.get("sql_error"):
        return 0.0

    # If no SQL was expected/generated, full reward
    if result.get("generated_sql") is None:
        return 1.0

    # If SQL executed with results, full reward
    if result.get("query_results") is not None:
        return 1.0

    # SQL generated but no results (could be empty or not executed)
    return 0.5


def csv_export_reward(result: dict[str, Any], expected: dict[str, Any]) -> float:
    """Reward for CSV export matching expectation.

    Args:
        result: The chatbot output containing 'csv_content' key.
        expected: Expected values containing 'should_have_csv' key.

    Returns:
        1.0 if CSV presence matches expectation, 0.0 otherwise.
    """
    if expected.get("should_have_csv") is None:
        return 1.0

    has_csv = result.get("csv_content") is not None and len(result.get("csv_content", "")) > 0
    return 1.0 if has_csv == expected.get("should_have_csv") else 0.0


def response_format_reward(result: dict[str, Any], expected: dict[str, Any]) -> float:
    """Reward for response format matching expectation.

    Args:
        result: The chatbot output containing 'response_format' key.
        expected: Expected values containing 'response_format' key.

    Returns:
        1.0 if format matches, 0.0 otherwise.
    """
    if expected.get("response_format") is None:
        return 1.0

    return 1.0 if result.get("response_format") == expected.get("response_format") else 0.0


def sql_generator_reward(result: dict[str, Any], expected: dict[str, Any]) -> float:
    """Composite reward function for SQL generator prompt optimization.

    Combines multiple reward signals to provide a comprehensive score
    for SQL generation quality. Focuses on:
    - SQL keyword presence (semantic correctness)
    - SQL execution success (syntactic correctness)
    - Response format (output quality)

    Args:
        result: The chatbot output.
        expected: Expected values.

    Returns:
        Weighted composite score between 0 and 1.
    """
    # Weight distribution:
    # - SQL contains: 40% (semantic correctness)
    # - SQL execution: 30% (syntactic correctness)
    # - SQL generated: 20% (followed instructions)
    # - Response format: 10% (output quality)

    sql_contains = sql_contains_reward(result, expected)
    sql_execution = sql_execution_reward(result, expected)
    sql_generated = sql_generated_reward(result, expected)
    response_format = response_format_reward(result, expected)

    return (
        (sql_contains * 0.4)
        + (sql_execution * 0.3)
        + (sql_generated * 0.2)
        + (response_format * 0.1)
    )


def end_to_end_reward(result: dict[str, Any], expected: dict[str, Any]) -> float:
    """Full pipeline reward combining all signals.

    Use this for end-to-end optimization across the entire chatbot.

    Args:
        result: The chatbot output.
        expected: Expected values.

    Returns:
        Weighted composite score between 0 and 1.
    """
    # Weight distribution for end-to-end:
    # - Intent classification: 15%
    # - SQL generation: 40% (most important)
    # - Response quality: 25%
    # - Export/format: 20%

    intent_score = intent_classification_reward(result, expected) * 0.15
    sql_score = sql_generator_reward(result, expected) * 0.40
    response_score = response_contains_reward(result, expected) * 0.25
    format_score = (
        (csv_export_reward(result, expected) + response_format_reward(result, expected)) / 2 * 0.20
    )

    return intent_score + sql_score + response_score + format_score
