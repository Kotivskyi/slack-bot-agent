"""Training commands for agent-lightning prompt optimization.

Provides CLI commands for training and evaluating analytics chatbot prompts
using agent-lightning's APO algorithm.
"""

import asyncio

import click

from app.commands import command, error, info, success, warning


@command("train", help="Train analytics chatbot prompts with agent-lightning")
@click.option(
    "--prompt",
    "-p",
    default="sql_generator",
    type=click.Choice(["sql_generator", "intent_classifier", "context_resolver"]),
    help="Prompt to optimize (default: sql_generator)",
)
@click.option(
    "--rounds",
    "-r",
    default=5,
    type=int,
    help="Number of optimization rounds (default: 5)",
)
@click.option(
    "--workers",
    "-w",
    default=4,
    type=int,
    help="Number of parallel workers (default: 4)",
)
@click.option(
    "--max-tokens",
    "-t",
    default=None,
    type=int,
    help="Maximum tokens to use (budget limit)",
)
@click.option(
    "--max-cost",
    "-c",
    default=1.0,
    type=float,
    help="Maximum cost in USD (default: $1.00)",
)
@click.option(
    "--server",
    is_flag=True,
    help="Use full server mode (default: local DevTaskLoader)",
)
@click.option(
    "--eval-only",
    is_flag=True,
    help="Only evaluate current prompt, don't train",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip cost confirmation prompt",
)
def train(
    prompt: str,
    rounds: int,
    workers: int,
    max_tokens: int | None,
    max_cost: float,
    server: bool,
    eval_only: bool,
    yes: bool,
) -> None:
    """Train analytics chatbot prompts using agent-lightning.

    This command runs the APO (Automatic Prompt Optimization) algorithm
    to optimize the specified prompt for better performance.

    Before training starts, a cost estimate is shown and you must confirm
    to proceed. Use --yes to skip the confirmation.

    Examples:
        # Train the SQL generator prompt (will show cost estimate)
        slack_analytics_app cmd train --prompt sql_generator --rounds 5

        # Train with a $2 budget limit
        slack_analytics_app cmd train -p sql_generator --max-cost 2.0

        # Train with a token limit
        slack_analytics_app cmd train -p sql_generator --max-tokens 100000

        # Evaluate the current SQL generator prompt
        slack_analytics_app cmd train --prompt sql_generator --eval-only

        # Skip confirmation (for CI/automation)
        slack_analytics_app cmd train -p sql_generator -y
    """
    if eval_only:
        info(f"Evaluating prompt: {prompt}")
        asyncio.run(_run_evaluation(prompt))
    else:
        asyncio.run(
            _run_training_with_confirmation(
                prompt_name=prompt,
                rounds=rounds,
                workers=workers,
                max_tokens=max_tokens,
                max_cost=max_cost,
                use_server=server,
                skip_confirmation=yes,
            )
        )


async def _run_training_with_confirmation(
    prompt_name: str,
    rounds: int,
    workers: int,
    max_tokens: int | None,
    max_cost: float,
    use_server: bool,
    skip_confirmation: bool,
) -> None:
    """Run training with cost estimation and confirmation."""
    try:
        from training.budget import (
            estimate_training_cost,
            format_cost_estimate,
            get_model_from_settings,
        )
        from training.datasets import get_sql_focused_dataset

        if prompt_name != "sql_generator":
            warning(f"Training for '{prompt_name}' not yet implemented")
            warning("Only 'sql_generator' is currently supported")
            return

        # Load dataset to get task count
        train_data, val_data = get_sql_focused_dataset()
        model = get_model_from_settings()

        # Show cost estimate
        estimate = estimate_training_cost(
            n_tasks=len(train_data),
            n_rounds=rounds,
            model=model,
            include_validation=True,
        )

        click.echo("")
        click.echo(format_cost_estimate(estimate))
        click.echo("")

        # Show budget limits
        info("Budget Limits:")
        if max_tokens:
            info(f"  Max Tokens: {max_tokens:,}")
        info(f"  Max Cost:   ${max_cost:.2f}")
        click.echo("")

        # Check if estimated cost exceeds budget
        estimated_cost = estimate["estimated_cost"]["total_usd"]
        if estimated_cost > max_cost:
            warning(f"Estimated cost (${estimated_cost:.4f}) exceeds budget (${max_cost:.2f})")
            warning("Training will stop when budget is reached.")
            click.echo("")

        # Confirm before proceeding
        if not skip_confirmation and not click.confirm("Proceed with training?"):
            info("Training cancelled.")
            return

        click.echo("")
        info(f"Starting training for prompt: {prompt_name}")
        info(f"  Rounds: {rounds}")
        info(f"  Workers: {workers}")
        info(f"  Mode: {'server' if use_server else 'local'}")
        click.echo("")

        await _run_training(
            prompt_name=prompt_name,
            rounds=rounds,
            workers=workers,
            max_tokens=max_tokens,
            max_cost=max_cost,
            use_server=use_server,
        )

    except ImportError as e:
        error(f"Failed to import training module: {e}")
        error("Make sure agentlightning is installed: uv add agentlightning")
    except Exception as e:
        error(f"Training failed: {e}")
        raise


async def _run_training(
    prompt_name: str,
    rounds: int,
    workers: int,
    max_tokens: int | None,
    max_cost: float,
    use_server: bool,
) -> None:
    """Run the training pipeline."""
    try:
        from training.train import save_training_results, train_sql_generator

        results = await train_sql_generator(
            n_rounds=rounds,
            n_workers=workers,
            use_server=use_server,
            max_tokens=max_tokens,
            max_cost_usd=max_cost,
            skip_confirmation=True,  # Already confirmed
        )

        click.echo("")
        success("Training Results:")
        info(f"  Training Reward:   {results['train_reward']:.3f}")
        info(f"  Validation Reward: {results['val_reward']:.3f}")

        # Show token usage
        if "token_usage" in results:
            usage = results["token_usage"]
            click.echo("")
            info("Token Usage:")
            info(f"  Input Tokens:  {usage['input_tokens']:>10,}")
            info(f"  Output Tokens: {usage['output_tokens']:>10,}")
            info(f"  Total Tokens:  {usage['total_tokens']:>10,}")
            info(f"  Total Cost:    ${usage['total_cost_usd']:>10.4f}")
            info(f"  Runs Completed: {usage['runs_completed']}")

        # Check if budget was exceeded
        if results.get("budget_exceeded"):
            click.echo("")
            warning(f"Budget exceeded: {results.get('budget_exceeded_reason', 'Unknown reason')}")
            warning(
                f"Tasks completed: {results.get('tasks_completed', 0)}/{results.get('tasks_total', 0)}"
            )

        # Save results
        save_path = save_training_results(results, prompt_name)
        click.echo("")
        success(f"Optimized prompt saved to: {save_path}")

    except ImportError as e:
        error(f"Failed to import training module: {e}")
        error("Make sure agentlightning is installed: uv add agentlightning")
    except Exception as e:
        error(f"Training failed: {e}")
        raise


async def _run_evaluation(prompt_name: str) -> None:
    """Run evaluation on current prompt."""
    try:
        from training.train import evaluate_prompt

        results = await evaluate_prompt(prompt_name=prompt_name)

        click.echo("")
        success("Evaluation Results:")
        info(f"  Prompt: {results['prompt_name']}")
        info(f"  Average Reward: {results['avg_reward']:.3f}")
        info(f"  Tasks Evaluated: {results['n_tasks']}")

        # Show individual results
        click.echo("")
        info("Individual Task Results:")
        for r in results["results"]:
            reward = r.final_reward if r.final_reward is not None else 0.0
            metadata = r.metadata or {}
            query = metadata.get("user_query", "N/A")[:50]
            click.echo(f"  {reward:.3f} - {query}...")

    except ImportError as e:
        error(f"Failed to import training module: {e}")
        error("Make sure agentlightning is installed: uv add agentlightning")
    except Exception as e:
        error(f"Evaluation failed: {e}")
        raise


@command("train-status", help="Check training status and available optimized prompts")
def train_status() -> None:
    """Check the status of prompt training.

    Shows which prompts have optimized versions and their status.
    """
    from app.agents.analytics_chatbot.prompts import (
        TRAINED_PROMPTS_DIR,
        has_optimized_prompt,
        list_optimized_prompts,
    )

    info("Prompt Training Status")
    info("=" * 40)
    info(f"Optimized prompts directory: {TRAINED_PROMPTS_DIR}")
    click.echo("")

    prompts = ["sql_generator", "intent_classifier", "context_resolver"]

    for prompt_name in prompts:
        if has_optimized_prompt(prompt_name):
            success(f"  [OPTIMIZED] {prompt_name}")
        else:
            info(f"  [DEFAULT]   {prompt_name}")

    click.echo("")
    optimized = list_optimized_prompts()
    if optimized:
        info(f"Optimized prompts available: {', '.join(optimized)}")
    else:
        warning("No optimized prompts found. Run 'cmd train' to train prompts.")


@command("train-reset", help="Reset optimized prompts to defaults")
@click.option(
    "--prompt",
    "-p",
    default=None,
    help="Specific prompt to reset (default: all)",
)
@click.confirmation_option(
    prompt="Are you sure you want to reset optimized prompts?",
)
def train_reset(prompt: str | None) -> None:
    """Reset optimized prompts to default versions.

    This deletes the optimized prompt files, causing the chatbot
    to use the default built-in prompts.
    """
    from app.agents.analytics_chatbot.prompts import (
        TRAINED_PROMPTS_DIR,
        list_optimized_prompts,
        reload_sql_generator_prompt,
    )

    if prompt:
        # Reset specific prompt
        prompt_path = TRAINED_PROMPTS_DIR / f"{prompt}.txt"
        if prompt_path.exists():
            prompt_path.unlink()
            success(f"Reset prompt: {prompt}")
        else:
            warning(f"No optimized prompt found for: {prompt}")
    else:
        # Reset all prompts
        optimized = list_optimized_prompts()
        if not optimized:
            warning("No optimized prompts to reset")
            return

        for name in optimized:
            prompt_path = TRAINED_PROMPTS_DIR / f"{name}.txt"
            if prompt_path.exists():
                prompt_path.unlink()
                info(f"  Reset: {name}")

        success(f"Reset {len(optimized)} optimized prompt(s)")

    # Reload prompts
    reload_sql_generator_prompt()
    info("Prompts reloaded")


@command("train-baseline", help="Run baseline evaluation before training")
@click.option(
    "--max-tasks",
    "-n",
    default=None,
    type=int,
    help="Maximum tasks to evaluate (default: all)",
)
@click.option(
    "--max-cost",
    "-c",
    default=0.50,
    type=float,
    help="Maximum cost in USD (default: $0.50)",
)
@click.option(
    "--save-as",
    "-s",
    default=None,
    type=str,
    help="Custom name for saved evaluation file",
)
def train_baseline(max_tasks: int | None, max_cost: float, save_as: str | None) -> None:
    """Run baseline evaluation on current prompts.

    This measures the current performance of prompts before training,
    providing a baseline for comparison after optimization.

    The evaluation results are automatically saved and can be compared
    with post-training results using 'cmd train-compare'.

    Examples:
        # Run full baseline evaluation
        slack_analytics_app cmd train-baseline

        # Run quick evaluation (first 5 tasks)
        slack_analytics_app cmd train-baseline --max-tasks 5

        # Run with custom budget
        slack_analytics_app cmd train-baseline --max-cost 1.0
    """
    asyncio.run(_run_baseline_evaluation(max_tasks, max_cost, save_as))


async def _run_baseline_evaluation(
    max_tasks: int | None,
    max_cost: float,
    save_as: str | None,
) -> None:
    """Run baseline evaluation."""
    try:
        from training.evaluation import (
            format_evaluation_report,
            run_evaluation,
            save_evaluation,
        )

        info("Running baseline evaluation...")
        info(f"  Max tasks: {max_tasks or 'all'}")
        info(f"  Max cost:  ${max_cost:.2f}")
        click.echo("")

        metrics = await run_evaluation(
            prompt_version="baseline",
            max_tasks=max_tasks,
            max_cost_usd=max_cost,
        )

        # Show report
        click.echo(format_evaluation_report(metrics))
        click.echo("")

        # Save results
        filepath = save_evaluation(metrics, name=save_as)
        success(f"Baseline evaluation saved to: {filepath}")

    except ImportError as e:
        error(f"Failed to import evaluation module: {e}")
    except Exception as e:
        error(f"Baseline evaluation failed: {e}")
        raise


@command("train-optimized", help="Run evaluation on optimized prompts after training")
@click.option(
    "--max-tasks",
    "-n",
    default=None,
    type=int,
    help="Maximum tasks to evaluate (default: all)",
)
@click.option(
    "--max-cost",
    "-c",
    default=0.50,
    type=float,
    help="Maximum cost in USD (default: $0.50)",
)
@click.option(
    "--save-as",
    "-s",
    default=None,
    type=str,
    help="Custom name for saved evaluation file",
)
def train_optimized(max_tasks: int | None, max_cost: float, save_as: str | None) -> None:
    """Run evaluation on optimized prompts after training.

    This measures the performance of optimized prompts after training,
    allowing comparison with baseline results.

    Examples:
        # Run full optimized evaluation
        slack_analytics_app cmd train-optimized

        # Match baseline evaluation size
        slack_analytics_app cmd train-optimized --max-tasks 10
    """
    asyncio.run(_run_optimized_evaluation(max_tasks, max_cost, save_as))


async def _run_optimized_evaluation(
    max_tasks: int | None,
    max_cost: float,
    save_as: str | None,
) -> None:
    """Run optimized evaluation."""
    try:
        from training.evaluation import (
            format_evaluation_report,
            run_evaluation,
            save_evaluation,
        )

        info("Running optimized evaluation...")
        info(f"  Max tasks: {max_tasks or 'all'}")
        info(f"  Max cost:  ${max_cost:.2f}")
        click.echo("")

        metrics = await run_evaluation(
            prompt_version="optimized",
            max_tasks=max_tasks,
            max_cost_usd=max_cost,
        )

        # Show report
        click.echo(format_evaluation_report(metrics))
        click.echo("")

        # Save results
        filepath = save_evaluation(metrics, name=save_as)
        success(f"Optimized evaluation saved to: {filepath}")

    except ImportError as e:
        error(f"Failed to import evaluation module: {e}")
    except Exception as e:
        error(f"Optimized evaluation failed: {e}")
        raise


@command("train-compare", help="Compare baseline and optimized evaluations")
@click.option(
    "--baseline",
    "-b",
    default=None,
    type=click.Path(exists=True),
    help="Path to baseline evaluation file (default: most recent)",
)
@click.option(
    "--optimized",
    "-o",
    default=None,
    type=click.Path(exists=True),
    help="Path to optimized evaluation file (default: most recent)",
)
def train_compare(baseline: str | None, optimized: str | None) -> None:
    """Compare baseline and optimized evaluation results.

    Shows improvement metrics between pre-training (baseline) and
    post-training (optimized) prompt performance.

    If no files are specified, uses the most recent baseline and
    optimized evaluations from the training_results directory.

    Examples:
        # Compare most recent evaluations
        slack_analytics_app cmd train-compare

        # Compare specific files
        slack_analytics_app cmd train-compare \\
            --baseline training_results/baseline_2024-01-15.json \\
            --optimized training_results/optimized_2024-01-15.json
    """
    from pathlib import Path

    try:
        from training.evaluation import (
            compare_evaluations,
            format_comparison_report,
            get_latest_baseline,
            get_latest_optimized,
            load_evaluation,
        )

        # Load baseline
        if baseline:
            baseline_metrics = load_evaluation(Path(baseline))
            info(f"Loaded baseline from: {baseline}")
        else:
            baseline_metrics = get_latest_baseline()
            if not baseline_metrics:
                error("No baseline evaluation found.")
                error("Run 'cmd train-baseline' first to create a baseline.")
                return
            info("Using most recent baseline evaluation")

        # Load optimized
        if optimized:
            optimized_metrics = load_evaluation(Path(optimized))
            info(f"Loaded optimized from: {optimized}")
        else:
            optimized_metrics = get_latest_optimized()
            if not optimized_metrics:
                error("No optimized evaluation found.")
                error("Run training and then 'cmd train-optimized' to create one.")
                return
            info("Using most recent optimized evaluation")

        click.echo("")

        # Generate and display comparison
        comparison = compare_evaluations(baseline_metrics, optimized_metrics)
        click.echo(format_comparison_report(comparison))

        # Summary verdict
        click.echo("")
        avg_improvement = comparison["improvements"]["avg_reward"]["percent"]
        if avg_improvement > 0:
            success(f"Training improved average reward by {avg_improvement:.1f}%")
        elif avg_improvement < 0:
            warning(f"Average reward decreased by {abs(avg_improvement):.1f}%")
        else:
            info("No change in average reward")

    except ImportError as e:
        error(f"Failed to import evaluation module: {e}")
    except Exception as e:
        error(f"Comparison failed: {e}")
        raise


@command("train-workflow", help="Run full training workflow: baseline -> train -> compare")
@click.option(
    "--max-tasks",
    "-n",
    default=None,
    type=int,
    help="Maximum tasks for evaluation (default: all)",
)
@click.option(
    "--max-cost",
    "-c",
    default=2.0,
    type=float,
    help="Maximum total cost in USD (default: $2.00)",
)
@click.option(
    "--rounds",
    "-r",
    default=3,
    type=int,
    help="Training rounds (default: 3)",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompts",
)
def train_workflow(max_tasks: int | None, max_cost: float, rounds: int, yes: bool) -> None:
    """Run the complete training workflow.

    This command automates the full training process:
    1. Run baseline evaluation (pre-training metrics)
    2. Run training to optimize the prompt
    3. Run optimized evaluation (post-training metrics)
    4. Show comparison report

    Examples:
        # Run full workflow with defaults
        slack_analytics_app cmd train-workflow

        # Quick workflow for testing
        slack_analytics_app cmd train-workflow --max-tasks 5 --rounds 2

        # Skip confirmations
        slack_analytics_app cmd train-workflow -y
    """
    asyncio.run(_run_full_workflow(max_tasks, max_cost, rounds, yes))


async def _run_full_workflow(
    max_tasks: int | None,
    max_cost: float,
    rounds: int,
    yes: bool,
) -> None:
    """Run the complete training workflow."""
    try:
        from training.evaluation import (
            compare_evaluations,
            format_comparison_report,
            format_evaluation_report,
            run_evaluation,
            save_evaluation,
        )
        from training.train import train_sql_generator

        # Budget allocation: 20% baseline, 60% training, 20% optimized eval
        baseline_budget = max_cost * 0.20
        training_budget = max_cost * 0.60
        optimized_budget = max_cost * 0.20

        info("=" * 60)
        info("TRAINING WORKFLOW")
        info("=" * 60)
        info(f"Total budget: ${max_cost:.2f}")
        info(f"  Baseline eval:   ${baseline_budget:.2f}")
        info(f"  Training:        ${training_budget:.2f}")
        info(f"  Optimized eval:  ${optimized_budget:.2f}")
        info(f"Training rounds: {rounds}")
        info(f"Max tasks per eval: {max_tasks or 'all'}")
        click.echo("")

        if not yes and not click.confirm("Proceed with training workflow?"):
            info("Workflow cancelled.")
            return

        # Step 1: Baseline evaluation
        click.echo("")
        info("=" * 60)
        info("STEP 1/4: Baseline Evaluation")
        info("=" * 60)

        baseline_metrics = await run_evaluation(
            prompt_version="baseline",
            max_tasks=max_tasks,
            max_cost_usd=baseline_budget,
        )
        click.echo(format_evaluation_report(baseline_metrics))
        baseline_path = save_evaluation(baseline_metrics)
        success(f"Saved to: {baseline_path}")

        # Step 2: Training
        click.echo("")
        info("=" * 60)
        info("STEP 2/4: Training")
        info("=" * 60)

        training_results = await train_sql_generator(
            n_rounds=rounds,
            n_workers=4,
            use_server=False,
            max_cost_usd=training_budget,
            skip_confirmation=True,
        )

        info(f"Training reward: {training_results['train_reward']:.3f}")
        info(f"Validation reward: {training_results['val_reward']:.3f}")

        if training_results.get("budget_exceeded"):
            warning(f"Budget exceeded: {training_results.get('budget_exceeded_reason')}")

        # Step 3: Optimized evaluation
        click.echo("")
        info("=" * 60)
        info("STEP 3/4: Optimized Evaluation")
        info("=" * 60)

        optimized_metrics = await run_evaluation(
            prompt_version="optimized",
            max_tasks=max_tasks,
            max_cost_usd=optimized_budget,
        )
        click.echo(format_evaluation_report(optimized_metrics))
        optimized_path = save_evaluation(optimized_metrics)
        success(f"Saved to: {optimized_path}")

        # Step 4: Comparison
        click.echo("")
        info("=" * 60)
        info("STEP 4/4: Comparison Report")
        info("=" * 60)

        comparison = compare_evaluations(baseline_metrics, optimized_metrics)
        click.echo(format_comparison_report(comparison))

        # Final summary
        click.echo("")
        info("=" * 60)
        info("WORKFLOW COMPLETE")
        info("=" * 60)

        avg_improvement = comparison["improvements"]["avg_reward"]["percent"]
        if avg_improvement > 0:
            success(f"Training improved average reward by {avg_improvement:.1f}%")
        elif avg_improvement < 0:
            warning(f"Average reward decreased by {abs(avg_improvement):.1f}%")
        else:
            info("No change in average reward")

        total_cost = comparison["cost"]["total_usd"]
        info(f"Total cost: ${total_cost:.4f}")

    except ImportError as e:
        error(f"Failed to import modules: {e}")
    except Exception as e:
        error(f"Workflow failed: {e}")
        raise
