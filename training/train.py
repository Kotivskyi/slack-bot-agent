"""Training pipeline for agent-lightning prompt optimization.

This module provides the main entry point for training analytics chatbot
prompts using agent-lightning's APO algorithm.

Usage:
    # Via CLI command
    uv run slack_analytics_app cmd train --prompt sql_generator --rounds 5

    # Direct execution
    python -m training.train --prompt sql_generator --rounds 5

    # Programmatic usage
    from training.train import train_sql_generator
    result = await train_sql_generator(n_rounds=5, n_workers=4)
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from agentlightning import (
    AgentLightningServer,
    DevTaskLoader,
    PromptTemplate,
    Trainer,
)

from training.budget import (
    BudgetConfig,
    BudgetTracker,
    TokenUsage,
    estimate_training_cost,
    format_cost_estimate,
    get_model_from_settings,
)
from training.datasets import get_sql_focused_dataset
from training.prompts import (
    TRAINED_PROMPTS_DIR,
    get_default_resources,
    get_sql_generator_template,
    save_optimized_prompt,
)
from training.rollouts import create_sql_generator_agent

logger = logging.getLogger(__name__)


async def train_sql_generator(
    n_rounds: int = 5,
    n_workers: int = 4,
    use_server: bool = False,
    server_port: int = 8765,
    max_tokens: int | None = None,
    max_cost_usd: float | None = None,
    skip_confirmation: bool = False,
) -> dict[str, Any]:
    """Train the SQL generator prompt using APO.

    Args:
        n_rounds: Number of optimization rounds.
        n_workers: Number of parallel workers.
        use_server: If True, use full server mode. If False, use DevTaskLoader.
        server_port: Port for the training server.
        max_tokens: Maximum tokens to use (budget limit).
        max_cost_usd: Maximum cost in USD (budget limit).
        skip_confirmation: If True, skip the cost confirmation prompt.

    Returns:
        Training result with best prompt and scores.
    """
    logger.info(f"Starting SQL generator training: {n_rounds} rounds, {n_workers} workers")

    # Load SQL-focused dataset
    train_data, val_data = get_sql_focused_dataset()
    logger.info(f"Loaded dataset: {len(train_data)} train, {len(val_data)} validation")

    # Get model for cost estimation
    model = get_model_from_settings()

    # Show cost estimate
    estimate = estimate_training_cost(
        n_tasks=len(train_data),
        n_rounds=n_rounds,
        model=model,
        include_validation=True,
    )

    if not skip_confirmation:
        print("\n" + format_cost_estimate(estimate))
        print("")

    # Set up budget tracker
    budget_config = BudgetConfig(
        max_tokens=max_tokens,
        max_cost_usd=max_cost_usd,
    )
    budget_tracker = BudgetTracker(
        config=budget_config,
        usage=TokenUsage(model=model),
    )

    logger.info(
        f"Budget limits: max_tokens={max_tokens}, max_cost=${max_cost_usd}"
        if max_tokens or max_cost_usd
        else "No budget limits set (using default $1 limit)"
    )

    # Get initial resources
    resources = {"sql_generator": get_sql_generator_template()}

    # Create agent with budget tracker
    agent = create_sql_generator_agent(budget_tracker=budget_tracker)

    if use_server:
        result = await _train_with_server(
            agent=agent,
            train_data=train_data,
            val_data=val_data,
            resources=resources,
            n_rounds=n_rounds,
            n_workers=n_workers,
            server_port=server_port,
        )
    else:
        result = await _train_with_dev_loader(
            agent=agent,
            train_data=train_data,
            val_data=val_data,
            resources=resources,
            n_workers=n_workers,
        )

    # Add budget usage to results
    result["token_usage"] = budget_tracker.usage.to_dict()
    result["budget_exceeded"] = agent.budget_exceeded
    if agent.budget_exceeded_reason:
        result["budget_exceeded_reason"] = agent.budget_exceeded_reason

    return result


async def _train_with_dev_loader(
    agent: Any,
    train_data: list[dict[str, Any]],
    val_data: list[dict[str, Any]],
    resources: dict[str, PromptTemplate],
    n_workers: int,
) -> dict[str, Any]:
    """Train using DevTaskLoader (local, no server).

    Args:
        agent: The LitAgent to train.
        train_data: Training tasks.
        val_data: Validation tasks.
        resources: Initial resources (prompts).
        n_workers: Number of parallel workers.

    Returns:
        Training result dict.
    """
    logger.info("Training with DevTaskLoader (local mode)")

    # NOTE: DevTaskLoader and Trainer are available for future enhancements
    # when integrating with agent-lightning's full training loop.
    # For now, we run rollouts directly for simplicity.
    _ = DevTaskLoader  # Acknowledge import for future use
    _ = Trainer  # Acknowledge import for future use

    # Run training
    results = []
    for task in train_data:
        # Check budget before each task
        if agent.budget_exceeded:
            logger.warning(
                f"Budget exceeded, stopping training early: {agent.budget_exceeded_reason}"
            )
            break

        rollout_id = f"train-{task['id']}"
        result = await agent.training_rollout_async(
            task=task,
            rollout_id=rollout_id,
            resources=resources,
        )
        results.append(result)
        logger.info(f"Task {task['id']}: reward={result.final_reward:.3f}")

    # Calculate metrics
    rewards = [r.final_reward for r in results if r.final_reward is not None]
    avg_reward = sum(rewards) / len(rewards) if rewards else 0.0

    logger.info(f"Training complete. Average reward: {avg_reward:.3f}")
    logger.info(f"Tasks completed: {len(results)}/{len(train_data)}")

    # Run validation (only if budget not exceeded)
    val_results = []
    if not agent.budget_exceeded:
        for task in val_data:
            if agent.budget_exceeded:
                logger.warning(f"Budget exceeded during validation: {agent.budget_exceeded_reason}")
                break

            rollout_id = f"val-{task['id']}"
            result = await agent.validation_rollout_async(
                task=task,
                rollout_id=rollout_id,
                resources=resources,
            )
            val_results.append(result)

        val_rewards = [r.final_reward for r in val_results if r.final_reward is not None]
        val_avg_reward = sum(val_rewards) / len(val_rewards) if val_rewards else 0.0
        logger.info(f"Validation complete. Average reward: {val_avg_reward:.3f}")
    else:
        val_avg_reward = 0.0
        logger.warning("Skipping validation due to budget constraints")

    return {
        "train_reward": avg_reward,
        "val_reward": val_avg_reward,
        "train_results": results,
        "val_results": val_results,
        "resources": resources,
        "tasks_completed": len(results),
        "tasks_total": len(train_data),
    }


async def _train_with_server(
    agent: Any,
    train_data: list[dict[str, Any]],
    val_data: list[dict[str, Any]],
    resources: dict[str, PromptTemplate],
    n_rounds: int,
    n_workers: int,
    server_port: int,
) -> dict[str, Any]:
    """Train using full server mode with APO.

    Args:
        agent: The LitAgent to train.
        train_data: Training tasks.
        val_data: Validation tasks.
        resources: Initial resources (prompts).
        n_rounds: Number of optimization rounds.
        n_workers: Number of parallel workers.
        server_port: Port for the training server.

    Returns:
        Training result dict.
    """
    logger.info(f"Training with server mode on port {server_port}")

    # Create and start server
    server = AgentLightningServer(
        host="127.0.0.1",
        port=server_port,
        task_timeout_seconds=300.0,
    )

    await server.start()
    logger.info(f"Training server started on port {server_port}")

    try:
        best_resources = resources.copy()
        best_reward = 0.0

        for round_num in range(n_rounds):
            logger.info(f"=== Round {round_num + 1}/{n_rounds} ===")

            # Update resources
            await server.update_resources(best_resources)

            # Queue training tasks
            for task in train_data:
                await server.queue_task(
                    sample=task,
                    mode="train",
                    metadata={"round": round_num},
                )

            # Create trainer and run
            trainer = Trainer(
                n_workers=n_workers,
                max_tasks=len(train_data),
            )
            trainer.fit(agent, backend=f"http://127.0.0.1:{server_port}")

            # Collect results
            rollouts = await server.retrieve_completed_rollouts()
            rewards = [r.final_reward for r in rollouts if r.final_reward is not None]
            avg_reward = sum(rewards) / len(rewards) if rewards else 0.0

            logger.info(f"Round {round_num + 1} average reward: {avg_reward:.3f}")

            if avg_reward > best_reward:
                best_reward = avg_reward
                logger.info(f"New best reward: {best_reward:.3f}")

        # Final validation
        for task in val_data:
            await server.queue_task(sample=task, mode="val")

        trainer = Trainer(n_workers=n_workers, max_tasks=len(val_data))
        trainer.fit(agent, backend=f"http://127.0.0.1:{server_port}")

        val_rollouts = await server.retrieve_completed_rollouts()
        val_rewards = [r.final_reward for r in val_rollouts if r.final_reward is not None]
        val_avg_reward = sum(val_rewards) / len(val_rewards) if val_rewards else 0.0

        logger.info(f"Final validation reward: {val_avg_reward:.3f}")

        return {
            "train_reward": best_reward,
            "val_reward": val_avg_reward,
            "resources": best_resources,
            "n_rounds": n_rounds,
        }

    finally:
        await server.stop()
        logger.info("Training server stopped")


async def evaluate_prompt(
    prompt_name: str = "sql_generator",
    custom_prompt: str | None = None,
) -> dict[str, Any]:
    """Evaluate a prompt against the validation dataset.

    Args:
        prompt_name: Name of the prompt to evaluate.
        custom_prompt: Optional custom prompt content.

    Returns:
        Evaluation results with reward scores.
    """
    logger.info(f"Evaluating prompt: {prompt_name}")

    # Load validation data
    _, val_data = get_sql_focused_dataset()

    # Create resources
    if custom_prompt:
        resources = {prompt_name: PromptTemplate(template=custom_prompt, engine="jinja")}
    else:
        resources = get_default_resources()

    # Create agent
    agent = create_sql_generator_agent()

    # Run validation
    results = []
    for task in val_data:
        rollout_id = f"eval-{task['id']}"
        result = await agent.validation_rollout_async(
            task=task,
            rollout_id=rollout_id,
            resources=resources,
        )
        results.append(result)
        logger.info(f"Task {task['id']}: reward={result.final_reward:.3f}")

    rewards = [r.final_reward for r in results if r.final_reward is not None]
    avg_reward = sum(rewards) / len(rewards) if rewards else 0.0

    return {
        "prompt_name": prompt_name,
        "avg_reward": avg_reward,
        "n_tasks": len(val_data),
        "results": results,
    }


def save_training_results(
    results: dict[str, Any],
    prompt_name: str = "sql_generator",
) -> Path:
    """Save training results and optimized prompt.

    Args:
        results: Training results dict.
        prompt_name: Name of the prompt.

    Returns:
        Path to the saved prompt file.
    """
    # Save optimized prompt if available
    if "resources" in results and prompt_name in results["resources"]:
        prompt_template = results["resources"][prompt_name]
        prompt_path = save_optimized_prompt(prompt_name, prompt_template.template)
        logger.info(f"Saved optimized prompt to {prompt_path}")
        return prompt_path

    return TRAINED_PROMPTS_DIR


async def main():
    """Main entry point for training."""
    import argparse

    parser = argparse.ArgumentParser(description="Train analytics chatbot prompts")
    parser.add_argument(
        "--prompt",
        "-p",
        default="sql_generator",
        help="Prompt to optimize",
    )
    parser.add_argument(
        "--rounds",
        "-r",
        type=int,
        default=5,
        help="Number of optimization rounds",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=4,
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="Use full server mode (default: DevTaskLoader)",
    )
    parser.add_argument(
        "--eval-only",
        action="store_true",
        help="Only evaluate, don't train",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if args.eval_only:
        results = await evaluate_prompt(prompt_name=args.prompt)
        print("\nEvaluation Results:")
        print(f"  Prompt: {results['prompt_name']}")
        print(f"  Average Reward: {results['avg_reward']:.3f}")
        print(f"  Tasks Evaluated: {results['n_tasks']}")
    else:
        results = await train_sql_generator(
            n_rounds=args.rounds,
            n_workers=args.workers,
            use_server=args.server,
        )
        print("\nTraining Results:")
        print(f"  Training Reward: {results['train_reward']:.3f}")
        print(f"  Validation Reward: {results['val_reward']:.3f}")

        # Save results
        save_training_results(results, prompt_name=args.prompt)


if __name__ == "__main__":
    asyncio.run(main())
