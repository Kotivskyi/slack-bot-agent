"""CLI entry point for running evaluations.

Usage:
    uv run python -m evals.main [--quick] [--no-report]           # Generic agent
    uv run python -m evals.main --analytics [--quick] [--no-report]  # Analytics chatbot
"""
# ruff: noqa: E402 - load_dotenv must run before imports that use env vars

import argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env from backend directory
load_dotenv(Path(__file__).parent.parent / ".env")

# Configure Logfire for pydantic-evals integration
import logfire

if os.getenv("LOGFIRE_TOKEN"):
    logfire.configure()

from pydantic_evals.reporting import EvaluationReport

from evals.analytics_dataset import create_analytics_dataset, create_quick_analytics_dataset
from evals.dataset import create_dataset, create_quick_dataset
from evals.schemas import AgentInput, AgentOutput, AnalyticsInput, AnalyticsOutput

logger = logging.getLogger(__name__)


async def run_agent(inputs: AgentInput) -> AgentOutput:
    """Run the agent and return output.

    This is the task function that pydantic-evals will evaluate.

    Args:
        inputs: The agent input containing user message.

    Returns:
        AgentOutput with response and tool calls.
    """
    from uuid import uuid4

    from app.services.agent import AgentService

    thread_id = inputs.thread_id or f"eval-{uuid4()}"

    agent_service = AgentService()
    response, tool_events = await agent_service.run(
        user_input=inputs.user_input,
        thread_id=thread_id,
    )

    tool_calls = [{"name": e["name"], "args": e.get("args", {})} for e in tool_events]

    return AgentOutput(response=response, tool_calls=tool_calls)


async def run_analytics_agent(inputs: AnalyticsInput) -> AnalyticsOutput:
    """Run the analytics chatbot and return output.

    This is the task function for analytics chatbot evaluation.

    Args:
        inputs: The analytics input containing user query and optional history.

    Returns:
        AnalyticsOutput with response details.
    """
    from uuid import uuid4

    from app.db.session import get_analytics_db_context
    from app.services.agent import AnalyticsAgentService

    thread_id = inputs.thread_id or f"eval-{uuid4()}"

    async with get_analytics_db_context() as db:
        service = AnalyticsAgentService(db)
        response = await service.run(
            user_query=inputs.user_query,
            thread_id=thread_id,
            conversation_history=inputs.conversation_history or [],
        )

    # Extract response_format from slack_blocks if available
    response_format = None
    if response.slack_blocks:
        # Check for table indicator (code block with table data)
        for block in response.slack_blocks:
            if block.get("type") == "section":
                text = block.get("text", {}).get("text", "")
                if "```" in text or "|" in text:
                    response_format = "table"
                    break
        if response_format is None:
            response_format = "simple"

    return AnalyticsOutput(
        text=response.text,
        intent=response.intent,
        generated_sql=response.generated_sql,
        response_format=response_format,
        csv_content=response.csv_content,
        has_slack_blocks=response.slack_blocks is not None and len(response.slack_blocks) > 0,
    )


def save_report(report: EvaluationReport, prefix: str = "eval") -> Path:
    """Save the evaluation report to a JSON file.

    Args:
        report: The pydantic-evals report.
        prefix: Filename prefix.

    Returns:
        Path to the saved report file.
    """
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"{prefix}_report_{timestamp}.json"

    # Build report dict from EvaluationReport attributes
    report_data = {
        "name": report.name,
        "averages": report.averages,
        "cases": [
            {
                "name": case.name,
                "inputs": case.inputs.model_dump()
                if hasattr(case.inputs, "model_dump")
                else str(case.inputs),
                "output": case.output.model_dump()
                if hasattr(case.output, "model_dump")
                else str(case.output),
                "scores": case.scores,
                "assertions": case.assertions,
                "metrics": case.metrics,
            }
            for case in report.cases
        ],
        "trace_id": report.trace_id,
        "span_id": report.span_id,
    }

    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2, default=str)

    return report_path


async def run_evaluation(args: argparse.Namespace) -> None:
    """Run the evaluation with given arguments.

    Args:
        args: Parsed command-line arguments.
    """
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("Starting evaluation with pydantic-evals...")

    if args.analytics:
        # Analytics chatbot evaluation
        if args.quick:
            dataset = create_quick_analytics_dataset()
            print(f"Analytics quick mode: {len(dataset.cases)} cases")
        else:
            dataset = create_analytics_dataset()
            print(f"Analytics full evaluation: {len(dataset.cases)} cases")

        # Run evaluation
        report = await dataset.evaluate(run_analytics_agent)
        prefix = "analytics_quick" if args.quick else "analytics_full"
    else:
        # Generic agent evaluation
        if args.quick:
            dataset = create_quick_dataset()
            print(f"Quick mode: {len(dataset.cases)} cases")
        else:
            dataset = create_dataset()
            print(f"Full evaluation: {len(dataset.cases)} cases")

        # Run evaluation
        report = await dataset.evaluate(run_agent)
        prefix = "quick" if args.quick else "full"

    # Print results
    report.print(include_input=True, include_output=True)

    # Save report
    if not args.no_report:
        report_path = save_report(report, prefix=prefix)
        print(f"\nReport saved to: {report_path}")


def main() -> None:
    """Main entry point for the evaluation CLI."""
    parser = argparse.ArgumentParser(
        description="Run agent evaluations using pydantic-evals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run python -m evals.main                      # Generic agent (full)
    uv run python -m evals.main --quick              # Generic agent (quick)
    uv run python -m evals.main --analytics          # Analytics chatbot (full)
    uv run python -m evals.main --analytics --quick  # Analytics chatbot (quick)
    uv run python -m evals.main --no-report          # Don't save report
        """,
    )
    parser.add_argument(
        "--analytics",
        action="store_true",
        help="Run analytics chatbot evaluation instead of generic agent",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: evaluate fewer test cases",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Don't save the report to a file",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    import asyncio

    asyncio.run(run_evaluation(args))


if __name__ == "__main__":
    main()
