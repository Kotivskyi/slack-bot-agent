"""Analytics chatbot evaluation framework using pydantic-evals.

Provides tools for evaluating analytics chatbot responses against defined metrics.

Usage:
    uv run python -m evals.main              # Full evaluation (18 cases)
    uv run python -m evals.main --quick      # Quick evaluation (3 cases)
"""

from evals.analytics_dataset import create_analytics_dataset, create_quick_analytics_dataset
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

__all__ = [
    "AnalyticsExpected",
    "AnalyticsInput",
    "AnalyticsOutput",
    "CSVExport",
    "IntentMatch",
    "ResponseContains",
    "ResponseFormatMatch",
    "SQLContains",
    "SQLGenerated",
    "create_analytics_dataset",
    "create_analytics_judge",
    "create_quick_analytics_dataset",
]
