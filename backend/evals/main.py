"""CLI entry point for running evaluations.

Usage:
    python -m evals.main [--quick] [--no-report]
"""
# ruff: noqa: E402 - load_dotenv must run before imports that use env vars

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env from backend directory
load_dotenv(Path(__file__).parent.parent / ".env")

from evals.evaluator import Evaluator
from evals.schemas import EvalReport

logger = logging.getLogger(__name__)


def print_summary(report: EvalReport) -> None:
    """Print a formatted summary of the evaluation report.

    Args:
        report: The evaluation report to summarize.
    """
    print("\n" + "=" * 60)
    print("EVALUATION REPORT")
    print("=" * 60)
    print(f"\nReport ID: {report.report_id}")
    print(f"Created: {report.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total Traces Evaluated: {report.total_traces}")

    print("\n" + "-" * 60)
    print("SUMMARY BY METRIC")
    print("-" * 60)

    for metric_name, stats in report.summary.items():
        print(f"\n{metric_name.upper()}")
        print(f"  Count: {stats['count']:.0f}")
        print(f"  Mean:  {stats['mean']:.2f}")
        print(f"  Min:   {stats['min']:.2f}")
        print(f"  Max:   {stats['max']:.2f}")

    print("\n" + "-" * 60)
    print("DETAILED RESULTS")
    print("-" * 60)

    for result in report.results:
        print(f"\nTrace: {result.trace_id}")
        print(f"  Metric: {result.metric_name}")
        print(f"  Score:  {result.score.score:.2f}")
        print(f"  Reason: {result.score.reasoning[:100]}...")

    print("\n" + "=" * 60)


def save_report(report: EvalReport) -> Path:
    """Save the evaluation report to a JSON file.

    Args:
        report: The report to save.

    Returns:
        Path to the saved report file.
    """
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"eval_report_{timestamp}.json"

    with open(report_path, "w") as f:
        json.dump(report.model_dump(), f, indent=2, default=str)

    logger.info(f"Report saved to: {report_path}")
    return report_path


async def run_evaluation(args: argparse.Namespace) -> None:
    """Run the evaluation with given arguments.

    Args:
        args: Parsed command-line arguments.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("Starting evaluation...")

    evaluator = Evaluator()

    if not evaluator.metrics:
        print("No metrics found! Add metric files to evals/metrics/prompts/")
        return

    print(f"Loaded {len(evaluator.metrics)} metrics: {[m.name for m in evaluator.metrics]}")

    report = await evaluator.run(quick=args.quick)

    print_summary(report)

    if not args.no_report:
        report_path = save_report(report)
        print(f"\nReport saved to: {report_path}")


def main() -> None:
    """Main entry point for the evaluation CLI."""
    parser = argparse.ArgumentParser(
        description="Run agent evaluations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: only evaluate first 5 traces",
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

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    asyncio.run(run_evaluation(args))


if __name__ == "__main__":
    main()
