"""Agent evaluation framework using pydantic-evals.

Provides tools for evaluating agent responses against defined metrics.

Usage:
    uv run python -m evals.main              # Full evaluation
    uv run python -m evals.main --quick      # Quick evaluation
"""

from evals.dataset import create_dataset, create_quick_dataset
from evals.evaluator import (
    ContainsExpected,
    ToolsUsed,
    create_accuracy_judge,
    create_helpfulness_judge,
)
from evals.schemas import AgentInput, AgentOutput, ExpectedOutput

__all__ = [
    "AgentInput",
    "AgentOutput",
    "ContainsExpected",
    "ExpectedOutput",
    "ToolsUsed",
    "create_accuracy_judge",
    "create_dataset",
    "create_helpfulness_judge",
    "create_quick_dataset",
]
