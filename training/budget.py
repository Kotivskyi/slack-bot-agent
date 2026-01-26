"""Budget control and cost estimation for training.

Provides token tracking, cost estimation, and budget enforcement
to control training costs.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# OpenAI pricing per 1M tokens (as of Jan 2025)
# https://openai.com/pricing
MODEL_PRICING: dict[str, dict[str, float]] = {
    # GPT-4.1 series
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    # GPT-4o series
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    # GPT-4 Turbo
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4-turbo-preview": {"input": 10.00, "output": 30.00},
    # GPT-4
    "gpt-4": {"input": 30.00, "output": 60.00},
    # GPT-3.5
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    # Default fallback
    "default": {"input": 2.00, "output": 8.00},
}

# Estimated tokens per analytics chatbot run
# Based on typical prompt sizes and response lengths
ESTIMATED_TOKENS_PER_RUN = {
    "intent_classifier": {"input": 500, "output": 50},
    "context_resolver": {"input": 800, "output": 100},
    "sql_generator": {"input": 1500, "output": 200},
    "interpreter": {"input": 1000, "output": 150},
    # Total per full chatbot run (analytics query path)
    "full_run": {"input": 3800, "output": 500},
}


@dataclass
class TokenUsage:
    """Tracks token usage during training."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    model: str = "gpt-4.1"
    runs_completed: int = 0

    def add_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Add token usage from a single run."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.runs_completed += 1
        self._update_cost()

    def _update_cost(self) -> None:
        """Recalculate total cost based on current usage."""
        pricing = MODEL_PRICING.get(self.model, MODEL_PRICING["default"])
        input_cost = (self.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (self.output_tokens / 1_000_000) * pricing["output"]
        self.total_cost = input_cost + output_cost

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "total_cost_usd": round(self.total_cost, 4),
            "runs_completed": self.runs_completed,
            "model": self.model,
        }


@dataclass
class BudgetConfig:
    """Configuration for training budget limits."""

    max_tokens: int | None = None  # Total token limit
    max_cost_usd: float | None = None  # Dollar limit
    max_tasks: int | None = None  # Task limit
    warn_at_percent: float = 80.0  # Warn when reaching this % of budget

    def __post_init__(self) -> None:
        # Set sensible defaults if nothing specified
        if self.max_tokens is None and self.max_cost_usd is None:
            self.max_cost_usd = 1.0  # Default $1 budget


@dataclass
class BudgetTracker:
    """Tracks and enforces budget limits during training."""

    config: BudgetConfig
    usage: TokenUsage = field(default_factory=TokenUsage)
    _warned: bool = field(default=False, repr=False)

    def check_budget(self) -> tuple[bool, str | None]:
        """Check if budget allows continuing.

        Returns:
            Tuple of (can_continue, reason_if_stopped)
        """
        # Check token limit
        if self.config.max_tokens:
            total = self.usage.input_tokens + self.usage.output_tokens
            if total >= self.config.max_tokens:
                return False, f"Token budget exceeded: {total:,} >= {self.config.max_tokens:,}"

            # Warn at threshold
            if not self._warned and total >= self.config.max_tokens * (
                self.config.warn_at_percent / 100
            ):
                logger.warning(
                    f"Token usage at {total:,} ({total / self.config.max_tokens * 100:.0f}% of budget)"
                )
                self._warned = True

        # Check cost limit
        if self.config.max_cost_usd:
            if self.usage.total_cost >= self.config.max_cost_usd:
                return (
                    False,
                    f"Cost budget exceeded: ${self.usage.total_cost:.4f} >= ${self.config.max_cost_usd:.2f}",
                )

            # Warn at threshold
            if not self._warned and self.usage.total_cost >= self.config.max_cost_usd * (
                self.config.warn_at_percent / 100
            ):
                logger.warning(
                    f"Cost at ${self.usage.total_cost:.4f} ({self.usage.total_cost / self.config.max_cost_usd * 100:.0f}% of budget)"
                )
                self._warned = True

        # Check task limit
        if self.config.max_tasks and self.usage.runs_completed >= self.config.max_tasks:
            return (
                False,
                f"Task limit reached: {self.usage.runs_completed} >= {self.config.max_tasks}",
            )

        return True, None

    def record_run(self, input_tokens: int, output_tokens: int) -> tuple[bool, str | None]:
        """Record a completed run and check budget.

        Args:
            input_tokens: Input tokens used.
            output_tokens: Output tokens used.

        Returns:
            Tuple of (can_continue, reason_if_stopped)
        """
        self.usage.add_usage(input_tokens, output_tokens)
        return self.check_budget()

    def get_remaining(self) -> dict[str, Any]:
        """Get remaining budget information."""
        remaining = {}

        if self.config.max_tokens:
            total = self.usage.input_tokens + self.usage.output_tokens
            remaining["tokens"] = self.config.max_tokens - total
            remaining["tokens_percent"] = (1 - total / self.config.max_tokens) * 100

        if self.config.max_cost_usd:
            remaining["cost_usd"] = self.config.max_cost_usd - self.usage.total_cost
            remaining["cost_percent"] = (1 - self.usage.total_cost / self.config.max_cost_usd) * 100

        if self.config.max_tasks:
            remaining["tasks"] = self.config.max_tasks - self.usage.runs_completed

        return remaining


def estimate_training_cost(
    n_tasks: int,
    n_rounds: int = 1,
    model: str = "gpt-4.1",
    include_validation: bool = True,
) -> dict[str, Any]:
    """Estimate the cost of a training run.

    Args:
        n_tasks: Number of training tasks.
        n_rounds: Number of optimization rounds.
        model: Model to use for cost calculation.
        include_validation: Whether to include validation cost.

    Returns:
        Dictionary with cost estimates.
    """
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])
    tokens_per_run = ESTIMATED_TOKENS_PER_RUN["full_run"]

    # Training runs
    train_runs = n_tasks * n_rounds
    train_input = train_runs * tokens_per_run["input"]
    train_output = train_runs * tokens_per_run["output"]

    # Validation runs (typically once at the end)
    val_runs = n_tasks if include_validation else 0
    val_input = val_runs * tokens_per_run["input"]
    val_output = val_runs * tokens_per_run["output"]

    # Total tokens
    total_input = train_input + val_input
    total_output = train_output + val_output
    total_tokens = total_input + total_output

    # Cost calculation
    input_cost = (total_input / 1_000_000) * pricing["input"]
    output_cost = (total_output / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost

    return {
        "model": model,
        "n_tasks": n_tasks,
        "n_rounds": n_rounds,
        "training_runs": train_runs,
        "validation_runs": val_runs,
        "total_runs": train_runs + val_runs,
        "estimated_tokens": {
            "input": total_input,
            "output": total_output,
            "total": total_tokens,
        },
        "estimated_cost": {
            "input_usd": round(input_cost, 4),
            "output_usd": round(output_cost, 4),
            "total_usd": round(total_cost, 4),
        },
        "pricing_per_1m": pricing,
    }


def format_cost_estimate(estimate: dict[str, Any]) -> str:
    """Format cost estimate for display.

    Args:
        estimate: Cost estimate from estimate_training_cost().

    Returns:
        Formatted string for CLI display.
    """
    lines = [
        "Training Cost Estimate",
        "=" * 40,
        f"Model: {estimate['model']}",
        f"Tasks: {estimate['n_tasks']} x {estimate['n_rounds']} rounds = {estimate['training_runs']} training runs",
        f"Validation: {estimate['validation_runs']} runs",
        f"Total runs: {estimate['total_runs']}",
        "",
        "Estimated Tokens:",
        f"  Input:  {estimate['estimated_tokens']['input']:>10,}",
        f"  Output: {estimate['estimated_tokens']['output']:>10,}",
        f"  Total:  {estimate['estimated_tokens']['total']:>10,}",
        "",
        "Estimated Cost:",
        f"  Input:  ${estimate['estimated_cost']['input_usd']:>8.4f}",
        f"  Output: ${estimate['estimated_cost']['output_usd']:>8.4f}",
        f"  Total:  ${estimate['estimated_cost']['total_usd']:>8.4f}",
        "",
        f"(Pricing: ${estimate['pricing_per_1m']['input']}/1M input, ${estimate['pricing_per_1m']['output']}/1M output)",
    ]
    return "\n".join(lines)


def get_model_from_settings() -> str:
    """Get the configured model from settings."""
    from app.core.config import settings

    return settings.AI_MODEL
