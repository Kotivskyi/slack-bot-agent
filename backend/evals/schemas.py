"""Schemas for the evaluation framework."""

from datetime import datetime

from pydantic import BaseModel, Field


class ScoreSchema(BaseModel):
    """Schema for evaluation scores.

    Attributes:
        score: Score between 0 and 1.
        reasoning: Explanation for the score.
    """

    score: float = Field(ge=0, le=1, description="Score between 0 and 1")
    reasoning: str = Field(description="Explanation for the score")


class TraceData(BaseModel):
    """Data representing an agent trace to evaluate.

    Attributes:
        trace_id: Unique identifier for the trace.
        user_input: The original user input.
        agent_response: The agent's response.
        tool_calls: List of tool calls made during execution.
        duration_ms: Execution time in milliseconds.
        timestamp: When the trace was created.
    """

    trace_id: str
    user_input: str
    agent_response: str
    tool_calls: list[dict] = Field(default_factory=list)
    duration_ms: float | None = None
    timestamp: datetime | None = None


class MetricDefinition(BaseModel):
    """Definition of an evaluation metric.

    Attributes:
        name: Name of the metric.
        description: What the metric measures.
        prompt: The evaluation prompt template.
    """

    name: str
    description: str
    prompt: str


class EvalResult(BaseModel):
    """Result of evaluating a trace against a metric.

    Attributes:
        trace_id: ID of the evaluated trace.
        metric_name: Name of the metric used.
        score: The score result.
        evaluated_at: When the evaluation was performed.
    """

    trace_id: str
    metric_name: str
    score: ScoreSchema
    evaluated_at: datetime = Field(default_factory=datetime.now)


class EvalReport(BaseModel):
    """Complete evaluation report.

    Attributes:
        report_id: Unique identifier for the report.
        created_at: When the report was created.
        total_traces: Number of traces evaluated.
        results: Individual evaluation results.
        summary: Summary statistics by metric.
    """

    report_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    total_traces: int
    results: list[EvalResult]
    summary: dict[str, dict[str, float]]
