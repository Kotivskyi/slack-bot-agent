"""Evaluation and comparison for training workflow.

Provides functions to:
- Run baseline evaluation before training
- Run evaluation after training
- Compare and report improvements
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from training.budget import BudgetConfig, BudgetTracker, TokenUsage, get_model_from_settings
from training.datasets import get_sql_focused_dataset
from training.prompts import get_sql_generator_template
from training.rewards import (
    intent_classification_reward,
    response_contains_reward,
    sql_contains_reward,
    sql_execution_reward,
    sql_generated_reward,
)
from training.rollouts import AnalyticsChatbotAgent

logger = logging.getLogger(__name__)

# Directory for storing evaluation results
EVAL_RESULTS_DIR = Path(__file__).parent.parent / "training_results"


@dataclass
class EvaluationMetrics:
    """Metrics from a single evaluation run."""

    timestamp: str
    model: str
    prompt_version: str  # "baseline" or "optimized"
    n_tasks: int

    # Overall scores
    avg_reward: float
    min_reward: float
    max_reward: float

    # Component scores
    sql_generated_score: float
    sql_contains_score: float
    sql_execution_score: float
    intent_score: float
    response_score: float

    # Success rates
    sql_generation_rate: float  # % of tasks that generated SQL when expected
    execution_success_rate: float  # % of generated SQL that executed successfully

    # Token usage
    total_tokens: int
    total_cost_usd: float

    # Per-task details
    task_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "n_tasks": self.n_tasks,
            "avg_reward": self.avg_reward,
            "min_reward": self.min_reward,
            "max_reward": self.max_reward,
            "sql_generated_score": self.sql_generated_score,
            "sql_contains_score": self.sql_contains_score,
            "sql_execution_score": self.sql_execution_score,
            "intent_score": self.intent_score,
            "response_score": self.response_score,
            "sql_generation_rate": self.sql_generation_rate,
            "execution_success_rate": self.execution_success_rate,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "task_results": self.task_results,
        }


async def run_evaluation(
    prompt_version: str = "baseline",
    max_tasks: int | None = None,
    max_cost_usd: float = 0.50,
) -> EvaluationMetrics:
    """Run evaluation on the current prompt configuration.

    Args:
        prompt_version: Label for this evaluation ("baseline" or "optimized").
        max_tasks: Maximum tasks to evaluate (None = all).
        max_cost_usd: Maximum cost budget.

    Returns:
        EvaluationMetrics with detailed results.
    """
    logger.info(f"Starting {prompt_version} evaluation")

    # Load dataset
    _, val_data = get_sql_focused_dataset()
    if max_tasks:
        val_data = val_data[:max_tasks]

    logger.info(f"Evaluating on {len(val_data)} tasks")

    # Get model
    model = get_model_from_settings()

    # Set up budget tracker
    budget_config = BudgetConfig(max_cost_usd=max_cost_usd)
    budget_tracker = BudgetTracker(
        config=budget_config,
        usage=TokenUsage(model=model),
    )

    # Create agent
    agent = AnalyticsChatbotAgent(
        reward_fn="sql_generator",
        budget_tracker=budget_tracker,
    )

    # Resources (uses current prompt - baseline or optimized)
    resources = {"sql_generator": get_sql_generator_template()}

    # Run evaluation
    task_results = []
    component_scores = {
        "sql_generated": [],
        "sql_contains": [],
        "sql_execution": [],
        "intent": [],
        "response": [],
        "overall": [],
    }

    sql_expected_count = 0
    sql_generated_count = 0
    sql_executed_count = 0
    sql_success_count = 0

    for task in val_data:
        if agent.budget_exceeded:
            logger.warning(f"Budget exceeded: {agent.budget_exceeded_reason}")
            break

        rollout_id = f"eval-{prompt_version}-{task['id']}"

        try:
            rollout = await agent.training_rollout_async(
                task=task,
                rollout_id=rollout_id,
                resources=resources,
            )

            result = rollout.metadata or {}
            expected = task.get("expected", {})

            # Calculate component scores
            scores = {
                "sql_generated": sql_generated_reward(result, expected),
                "sql_contains": sql_contains_reward(result, expected),
                "sql_execution": sql_execution_reward(result, expected),
                "intent": intent_classification_reward(result, expected),
                "response": response_contains_reward(result, expected),
                "overall": rollout.final_reward or 0.0,
            }

            for key, score in scores.items():
                component_scores[key].append(score)

            # Track SQL generation stats
            if expected.get("should_generate_sql"):
                sql_expected_count += 1
                if result.get("generated_sql"):
                    sql_generated_count += 1
                    sql_executed_count += 1
                    if not result.get("sql_error"):
                        sql_success_count += 1

            task_results.append(
                {
                    "task_id": task["id"],
                    "query": task["user_query"],
                    "scores": scores,
                    "generated_sql": result.get("generated_sql"),
                    "sql_error": result.get("sql_error"),
                    "intent": result.get("intent"),
                    "input_tokens": result.get("input_tokens", 0),
                    "output_tokens": result.get("output_tokens", 0),
                }
            )

            logger.info(f"Task {task['id']}: reward={rollout.final_reward:.3f}")

        except Exception as e:
            logger.error(f"Task {task['id']} failed: {e}")
            task_results.append(
                {
                    "task_id": task["id"],
                    "query": task["user_query"],
                    "error": str(e),
                    "scores": {"overall": 0.0},
                }
            )
            component_scores["overall"].append(0.0)

    # Calculate aggregate metrics
    def safe_avg(lst: list) -> float:
        return sum(lst) / len(lst) if lst else 0.0

    metrics = EvaluationMetrics(
        timestamp=datetime.now().isoformat(),
        model=model,
        prompt_version=prompt_version,
        n_tasks=len(task_results),
        avg_reward=safe_avg(component_scores["overall"]),
        min_reward=min(component_scores["overall"]) if component_scores["overall"] else 0.0,
        max_reward=max(component_scores["overall"]) if component_scores["overall"] else 0.0,
        sql_generated_score=safe_avg(component_scores["sql_generated"]),
        sql_contains_score=safe_avg(component_scores["sql_contains"]),
        sql_execution_score=safe_avg(component_scores["sql_execution"]),
        intent_score=safe_avg(component_scores["intent"]),
        response_score=safe_avg(component_scores["response"]),
        sql_generation_rate=sql_generated_count / sql_expected_count if sql_expected_count else 0.0,
        execution_success_rate=sql_success_count / sql_executed_count
        if sql_executed_count
        else 0.0,
        total_tokens=budget_tracker.usage.input_tokens + budget_tracker.usage.output_tokens,
        total_cost_usd=budget_tracker.usage.total_cost,
        task_results=task_results,
    )

    logger.info(f"Evaluation complete. Avg reward: {metrics.avg_reward:.3f}")
    return metrics


def save_evaluation(metrics: EvaluationMetrics, name: str | None = None) -> Path:
    """Save evaluation results to disk.

    Args:
        metrics: Evaluation metrics to save.
        name: Optional name for the file (default: timestamp-based).

    Returns:
        Path to saved file.
    """
    EVAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if name is None:
        name = f"{metrics.prompt_version}_{metrics.timestamp.replace(':', '-')}"

    filepath = EVAL_RESULTS_DIR / f"{name}.json"
    filepath.write_text(json.dumps(metrics.to_dict(), indent=2))

    logger.info(f"Saved evaluation to {filepath}")
    return filepath


def load_evaluation(filepath: Path) -> EvaluationMetrics:
    """Load evaluation results from disk.

    Args:
        filepath: Path to evaluation JSON file.

    Returns:
        EvaluationMetrics instance.
    """
    data = json.loads(filepath.read_text())
    return EvaluationMetrics(**data)


def compare_evaluations(
    baseline: EvaluationMetrics,
    optimized: EvaluationMetrics,
) -> dict[str, Any]:
    """Compare baseline and optimized evaluation results.

    Args:
        baseline: Metrics from baseline evaluation.
        optimized: Metrics from optimized evaluation.

    Returns:
        Comparison report dictionary.
    """

    def calc_improvement(before: float, after: float) -> dict[str, float]:
        abs_diff = after - before
        pct_diff = ((after - before) / before * 100) if before > 0 else 0.0
        return {
            "before": before,
            "after": after,
            "absolute": abs_diff,
            "percent": pct_diff,
        }

    return {
        "baseline_timestamp": baseline.timestamp,
        "optimized_timestamp": optimized.timestamp,
        "model": baseline.model,
        "tasks_evaluated": {
            "baseline": baseline.n_tasks,
            "optimized": optimized.n_tasks,
        },
        "improvements": {
            "avg_reward": calc_improvement(baseline.avg_reward, optimized.avg_reward),
            "sql_generated_score": calc_improvement(
                baseline.sql_generated_score, optimized.sql_generated_score
            ),
            "sql_contains_score": calc_improvement(
                baseline.sql_contains_score, optimized.sql_contains_score
            ),
            "sql_execution_score": calc_improvement(
                baseline.sql_execution_score, optimized.sql_execution_score
            ),
            "intent_score": calc_improvement(baseline.intent_score, optimized.intent_score),
            "sql_generation_rate": calc_improvement(
                baseline.sql_generation_rate, optimized.sql_generation_rate
            ),
            "execution_success_rate": calc_improvement(
                baseline.execution_success_rate, optimized.execution_success_rate
            ),
        },
        "cost": {
            "baseline_usd": baseline.total_cost_usd,
            "optimized_usd": optimized.total_cost_usd,
            "total_usd": baseline.total_cost_usd + optimized.total_cost_usd,
        },
    }


def format_evaluation_report(metrics: EvaluationMetrics) -> str:
    """Format evaluation metrics as a readable report.

    Args:
        metrics: Evaluation metrics.

    Returns:
        Formatted string report.
    """
    lines = [
        f"{'=' * 50}",
        f"EVALUATION REPORT: {metrics.prompt_version.upper()}",
        f"{'=' * 50}",
        f"Timestamp: {metrics.timestamp}",
        f"Model: {metrics.model}",
        f"Tasks evaluated: {metrics.n_tasks}",
        "",
        "OVERALL SCORES:",
        f"  Average Reward:    {metrics.avg_reward:.3f}",
        f"  Min Reward:        {metrics.min_reward:.3f}",
        f"  Max Reward:        {metrics.max_reward:.3f}",
        "",
        "COMPONENT SCORES:",
        f"  SQL Generated:     {metrics.sql_generated_score:.3f}",
        f"  SQL Contains:      {metrics.sql_contains_score:.3f}",
        f"  SQL Execution:     {metrics.sql_execution_score:.3f}",
        f"  Intent Match:      {metrics.intent_score:.3f}",
        f"  Response Match:    {metrics.response_score:.3f}",
        "",
        "SUCCESS RATES:",
        f"  SQL Generation:    {metrics.sql_generation_rate * 100:.1f}%",
        f"  Execution Success: {metrics.execution_success_rate * 100:.1f}%",
        "",
        "COST:",
        f"  Total Tokens:      {metrics.total_tokens:,}",
        f"  Total Cost:        ${metrics.total_cost_usd:.4f}",
        f"{'=' * 50}",
    ]
    return "\n".join(lines)


def format_comparison_report(comparison: dict[str, Any]) -> str:
    """Format comparison results as a readable report.

    Args:
        comparison: Comparison dictionary from compare_evaluations().

    Returns:
        Formatted string report.
    """

    def format_improvement(imp: dict[str, float], is_pct: bool = False) -> str:
        before = imp["before"]
        after = imp["after"]
        diff = imp["absolute"]
        pct = imp["percent"]

        if is_pct:
            before_str = f"{before * 100:.1f}%"
            after_str = f"{after * 100:.1f}%"
            diff_str = f"{diff * 100:+.1f}pp"
        else:
            before_str = f"{before:.3f}"
            after_str = f"{after:.3f}"
            diff_str = f"{diff:+.3f}"

        direction = "↑" if diff > 0 else "↓" if diff < 0 else "→"
        return f"{before_str} → {after_str} ({diff_str}, {pct:+.1f}%) {direction}"

    imp = comparison["improvements"]

    lines = [
        f"{'=' * 60}",
        "TRAINING COMPARISON REPORT",
        f"{'=' * 60}",
        f"Model: {comparison['model']}",
        f"Baseline tasks: {comparison['tasks_evaluated']['baseline']}",
        f"Optimized tasks: {comparison['tasks_evaluated']['optimized']}",
        "",
        "METRIC IMPROVEMENTS (before → after):",
        f"  Average Reward:      {format_improvement(imp['avg_reward'])}",
        f"  SQL Generated:       {format_improvement(imp['sql_generated_score'])}",
        f"  SQL Contains:        {format_improvement(imp['sql_contains_score'])}",
        f"  SQL Execution:       {format_improvement(imp['sql_execution_score'])}",
        f"  Intent Score:        {format_improvement(imp['intent_score'])}",
        "",
        "SUCCESS RATE CHANGES:",
        f"  SQL Generation Rate: {format_improvement(imp['sql_generation_rate'], is_pct=True)}",
        f"  Execution Success:   {format_improvement(imp['execution_success_rate'], is_pct=True)}",
        "",
        "TOTAL COST:",
        f"  Baseline eval:       ${comparison['cost']['baseline_usd']:.4f}",
        f"  Optimized eval:      ${comparison['cost']['optimized_usd']:.4f}",
        f"  Total:               ${comparison['cost']['total_usd']:.4f}",
        f"{'=' * 60}",
    ]
    return "\n".join(lines)


def get_latest_baseline() -> EvaluationMetrics | None:
    """Get the most recent baseline evaluation.

    Returns:
        Latest baseline metrics, or None if not found.
    """
    if not EVAL_RESULTS_DIR.exists():
        return None

    baseline_files = sorted(EVAL_RESULTS_DIR.glob("baseline_*.json"), reverse=True)
    if baseline_files:
        return load_evaluation(baseline_files[0])
    return None


def get_latest_optimized() -> EvaluationMetrics | None:
    """Get the most recent optimized evaluation.

    Returns:
        Latest optimized metrics, or None if not found.
    """
    if not EVAL_RESULTS_DIR.exists():
        return None

    optimized_files = sorted(EVAL_RESULTS_DIR.glob("optimized_*.json"), reverse=True)
    if optimized_files:
        return load_evaluation(optimized_files[0])
    return None
