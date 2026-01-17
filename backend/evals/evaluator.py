"""Core evaluation logic for agent traces.

Provides the Evaluator class for scoring agent responses against metrics.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from openai import AsyncOpenAI

from evals.schemas import EvalReport, EvalResult, MetricDefinition, ScoreSchema, TraceData

logger = logging.getLogger(__name__)


class Evaluator:
    """Evaluator for agent traces.

    Loads metrics from markdown files and uses an LLM to score traces
    against each metric.

    Usage:
        evaluator = Evaluator()
        report = await evaluator.run(traces)
    """

    def __init__(
        self,
        metrics_dir: Path | None = None,
        model: str = "gpt-4o-mini",
    ):
        """Initialize the evaluator.

        Args:
            metrics_dir: Path to directory containing metric prompts.
                        Defaults to evals/metrics/prompts.
            model: OpenAI model to use for evaluation.
        """
        self.client = AsyncOpenAI()
        self.model = model

        if metrics_dir is None:
            metrics_dir = Path(__file__).parent / "metrics" / "prompts"
        self.metrics_dir = metrics_dir

        self.metrics = self._load_metrics()

    def _load_metrics(self) -> list[MetricDefinition]:
        """Load metric definitions from markdown files.

        Returns:
            List of MetricDefinition objects.
        """
        metrics = []

        if not self.metrics_dir.exists():
            logger.warning(f"Metrics directory not found: {self.metrics_dir}")
            return metrics

        for md_file in self.metrics_dir.glob("*.md"):
            try:
                content = md_file.read_text()
                name = md_file.stem

                # Extract description from first paragraph after title
                lines = content.strip().split("\n")
                description = ""
                for line in lines[1:]:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        description = line
                        break

                metrics.append(
                    MetricDefinition(
                        name=name,
                        description=description,
                        prompt=content,
                    )
                )
                logger.info(f"Loaded metric: {name}")
            except Exception as e:
                logger.error(f"Failed to load metric from {md_file}: {e}")

        return metrics

    async def run(
        self,
        traces: list[TraceData] | None = None,
        quick: bool = False,
    ) -> EvalReport:
        """Run evaluation on traces.

        Args:
            traces: List of traces to evaluate. If None, fetches from logs.
            quick: If True, only evaluate first 5 traces.

        Returns:
            EvalReport with results and summary.
        """
        if traces is None:
            traces = await self._fetch_traces()

        if quick and len(traces) > 5:
            traces = traces[:5]
            logger.info("Quick mode: evaluating only first 5 traces")

        results: list[EvalResult] = []

        for trace in traces:
            for metric in self.metrics:
                try:
                    score = await self._evaluate_trace(trace, metric)
                    results.append(
                        EvalResult(
                            trace_id=trace.trace_id,
                            metric_name=metric.name,
                            score=score,
                        )
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to evaluate trace {trace.trace_id} with {metric.name}: {e}"
                    )

        summary = self._compute_summary(results)

        return EvalReport(
            report_id=str(uuid4()),
            total_traces=len(traces),
            results=results,
            summary=summary,
        )

    async def _evaluate_trace(
        self,
        trace: TraceData,
        metric: MetricDefinition,
    ) -> ScoreSchema:
        """Evaluate a single trace against a metric.

        Args:
            trace: The trace to evaluate.
            metric: The metric to use.

        Returns:
            ScoreSchema with score and reasoning.
        """
        evaluation_prompt = f"""You are an AI evaluator. Evaluate the following agent interaction based on the metric defined below.

## Metric: {metric.name}

{metric.prompt}

## Interaction to Evaluate

**User Input:** {trace.user_input}

**Agent Response:** {trace.agent_response}

**Tool Calls:** {json.dumps(trace.tool_calls, indent=2) if trace.tool_calls else "None"}

## Your Task

Evaluate the interaction and provide:
1. A score between 0.0 and 1.0
2. A brief reasoning for your score

Respond in JSON format:
{{"score": <float>, "reasoning": "<string>"}}
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": evaluation_prompt}],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from evaluator")

        result = json.loads(content)
        return ScoreSchema(
            score=float(result["score"]),
            reasoning=str(result["reasoning"]),
        )

    async def _fetch_traces(self) -> list[TraceData]:
        """Fetch traces from logs or Logfire.

        This is a placeholder that returns sample traces.
        In production, implement fetching from your observability platform.

        Returns:
            List of TraceData objects.
        """
        logger.warning("Using sample traces - implement _fetch_traces for production")
        return [
            TraceData(
                trace_id="sample-1",
                user_input="What time is it?",
                agent_response="The current time is 2024-01-15T10:30:00Z.",
                tool_calls=[{"name": "current_datetime", "args": {}}],
                duration_ms=150.0,
                timestamp=datetime.now(),
            ),
            TraceData(
                trace_id="sample-2",
                user_input="Hello, how are you?",
                agent_response="Hello! I'm doing well, thank you for asking. How can I help you today?",
                tool_calls=[],
                duration_ms=80.0,
                timestamp=datetime.now(),
            ),
        ]

    def _compute_summary(self, results: list[EvalResult]) -> dict[str, dict[str, float]]:
        """Compute summary statistics by metric.

        Args:
            results: List of evaluation results.

        Returns:
            Dict mapping metric names to statistics.
        """
        summary: dict[str, dict[str, float]] = {}

        for metric in self.metrics:
            metric_results = [r for r in results if r.metric_name == metric.name]
            if not metric_results:
                continue

            scores = [r.score.score for r in metric_results]
            summary[metric.name] = {
                "count": len(scores),
                "mean": sum(scores) / len(scores),
                "min": min(scores),
                "max": max(scores),
            }

        return summary
