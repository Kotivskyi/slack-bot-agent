"""Rollout definitions for agent-lightning training.

Implements LitAgent subclass for running the analytics chatbot
with dynamic prompt injection for optimization.
"""

import logging
import uuid
from typing import Any

from agentlightning import LitAgent, NamedResources, PromptTemplate, Rollout, TaskInput

from training.budget import ESTIMATED_TOKENS_PER_RUN, BudgetTracker
from training.rewards import end_to_end_reward, sql_generator_reward

logger = logging.getLogger(__name__)


class AnalyticsChatbotAgent(LitAgent):
    """LitAgent implementation for analytics chatbot training.

    This agent wraps the analytics chatbot execution and provides
    reward signals for agent-lightning's APO algorithm.
    """

    def __init__(
        self,
        reward_fn: str = "sql_generator",
        budget_tracker: BudgetTracker | None = None,
        **kwargs: Any,
    ):
        """Initialize the analytics chatbot agent.

        Args:
            reward_fn: Name of reward function to use ('sql_generator' or 'end_to_end').
            budget_tracker: Optional budget tracker for cost control.
            **kwargs: Additional arguments passed to LitAgent.
        """
        super().__init__(**kwargs)
        self._reward_fn = reward_fn
        self._budget_tracker = budget_tracker
        self._reward_functions = {
            "sql_generator": sql_generator_reward,
            "end_to_end": end_to_end_reward,
        }
        self._budget_exceeded = False
        self._budget_exceeded_reason: str | None = None

    @property
    def budget_exceeded(self) -> bool:
        """Check if budget has been exceeded."""
        return self._budget_exceeded

    @property
    def budget_exceeded_reason(self) -> str | None:
        """Get the reason for budget being exceeded."""
        return self._budget_exceeded_reason

    def set_budget_tracker(self, tracker: BudgetTracker) -> None:
        """Set the budget tracker.

        Args:
            tracker: Budget tracker instance.
        """
        self._budget_tracker = tracker
        self._budget_exceeded = False
        self._budget_exceeded_reason = None

    async def training_rollout_async(
        self,
        task: TaskInput,
        rollout_id: str,
        resources: NamedResources,
    ) -> Rollout:
        """Execute a single training rollout of the analytics chatbot.

        Args:
            task: Task containing input data and expected outputs.
            rollout_id: Unique identifier for this rollout.
            resources: Named resources including prompts to use.

        Returns:
            Rollout object with final reward and metadata.
        """
        # Import here to avoid circular imports

        from app.db.session import get_analytics_db_context
        from app.repositories import AnalyticsRepository
        from app.services.llm import get_llm_client
        from training.chatbot_wrapper import run_chatbot_with_prompt_override

        # Extract task data
        task_data = task.sample if hasattr(task, "sample") else task
        user_query = task_data.get("user_query", "")
        conversation_history = task_data.get("conversation_history", [])
        expected = task_data.get("expected", {})

        # Extract optimized prompt from resources
        sql_generator_prompt = None
        if "sql_generator" in resources:
            prompt_resource = resources["sql_generator"]
            if isinstance(prompt_resource, PromptTemplate):
                sql_generator_prompt = prompt_resource.template

        # Generate unique thread ID for this rollout
        thread_id = f"training-{rollout_id}-{uuid.uuid4().hex[:8]}"

        try:
            # Run chatbot with prompt override
            async with get_analytics_db_context() as analytics_db:
                llm_client = get_llm_client()
                repository = AnalyticsRepository()

                result = await run_chatbot_with_prompt_override(
                    user_query=user_query,
                    thread_id=thread_id,
                    conversation_history=conversation_history,
                    analytics_db=analytics_db,
                    llm_client=llm_client,
                    repository=repository,
                    sql_generator_prompt=sql_generator_prompt,
                )

            # Calculate reward
            reward_fn = self._reward_functions.get(self._reward_fn, sql_generator_reward)
            reward = reward_fn(result, expected)

            # Extract token usage
            token_usage = result.get("token_usage")
            if token_usage:
                input_tokens = token_usage.get("input_tokens", 0)
                output_tokens = token_usage.get("output_tokens", 0)
            else:
                # Use estimated tokens if actual usage not available
                estimated = ESTIMATED_TOKENS_PER_RUN["full_run"]
                input_tokens = estimated["input"]
                output_tokens = estimated["output"]

            # Track with budget tracker if available
            if self._budget_tracker:
                can_continue, reason = self._budget_tracker.record_run(input_tokens, output_tokens)
                if not can_continue:
                    self._budget_exceeded = True
                    self._budget_exceeded_reason = reason
                    logger.warning(f"Budget exceeded: {reason}")

            logger.info(
                f"Rollout {rollout_id} complete. Query: {user_query[:50]}... "
                f"Reward: {reward:.3f}, Tokens: {input_tokens + output_tokens}"
            )

            return Rollout(
                rollout_id=rollout_id,
                final_reward=reward,
                metadata={
                    "user_query": user_query,
                    "intent": result.get("intent"),
                    "generated_sql": result.get("generated_sql"),
                    "sql_error": result.get("sql_error"),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )

        except Exception as e:
            logger.exception(f"Rollout {rollout_id} failed: {e}")
            return Rollout(
                rollout_id=rollout_id,
                final_reward=0.0,
                metadata={"error": str(e), "user_query": user_query},
            )


def create_sql_generator_agent(
    budget_tracker: BudgetTracker | None = None,
) -> AnalyticsChatbotAgent:
    """Create an agent optimized for SQL generator prompt.

    Args:
        budget_tracker: Optional budget tracker for cost control.

    Returns:
        Configured AnalyticsChatbotAgent.
    """
    return AnalyticsChatbotAgent(reward_fn="sql_generator", budget_tracker=budget_tracker)


def create_end_to_end_agent(
    budget_tracker: BudgetTracker | None = None,
) -> AnalyticsChatbotAgent:
    """Create an agent for end-to-end optimization.

    Args:
        budget_tracker: Optional budget tracker for cost control.

    Returns:
        Configured AnalyticsChatbotAgent.
    """
    return AnalyticsChatbotAgent(reward_fn="end_to_end", budget_tracker=budget_tracker)
