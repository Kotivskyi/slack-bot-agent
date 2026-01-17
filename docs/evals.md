# Evaluation Framework

Agent evaluation using [pydantic-evals](https://ai.pydantic.dev/evals/).

## Quick Start

```bash
# Run full evaluation
uv run python -m evals.main

# Quick evaluation (fewer cases)
uv run python -m evals.main --quick

# With options
uv run python -m evals.main --quick --no-report -v
```

## Architecture

```
evals/
├── main.py        # CLI entry point, run_agent task function
├── dataset.py     # Test cases and dataset creation
├── evaluator.py   # Custom evaluators and LLM judges
├── schemas.py     # AgentInput, AgentOutput, ExpectedOutput
└── reports/       # JSON reports (auto-created)
```

## Core Concepts

### Dataset and Cases

A **Dataset** contains multiple **Cases**. Each case defines:
- `inputs`: What to send to the agent (`AgentInput`)
- `expected_output`: What we expect (`ExpectedOutput`)
- `metadata`: Additional context for filtering/reporting

```python
from pydantic_evals import Case, Dataset
from evals.schemas import AgentInput, AgentOutput, ExpectedOutput

dataset: Dataset[AgentInput, AgentOutput, ExpectedOutput] = Dataset(
    cases=[
        Case(
            name="greeting",
            inputs=AgentInput(user_input="Hello!"),
            expected_output=ExpectedOutput(contains=["hello"]),
            metadata={"category": "greeting"},
        ),
    ]
)
```

### Evaluators

Evaluators score the agent's output. Two types:

**Deterministic Evaluators** - Rule-based, fast:

```python
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

class ContainsExpected(Evaluator[AgentInput, AgentOutput, ExpectedOutput]):
    async def evaluate(self, ctx: EvaluatorContext) -> float:
        if not ctx.expected_output.contains:
            return 1.0
        response = ctx.output.response.lower()
        matches = sum(1 for s in ctx.expected_output.contains if s.lower() in response)
        return matches / len(ctx.expected_output.contains)
```

**LLM Judges** - AI-powered, for subjective criteria:

```python
from pydantic_evals.evaluators import LLMJudge

accuracy_judge = LLMJudge[AgentInput, AgentOutput](
    model="openai:gpt-4o-mini",
    rubric="""Evaluate accuracy of the response.

    - Score 1.0: Completely accurate
    - Score 0.5: Partially accurate
    - Score 0.0: Inaccurate
    """,
)
```

### Task Function

The task function runs your agent and returns output:

```python
async def run_agent(inputs: AgentInput) -> AgentOutput:
    async with get_db_context() as db:
        agent_service = AgentService(db)
        response, tool_events = await agent_service.run(
            user_input=inputs.user_input,
            thread_id=f"eval-{uuid4()}",
        )
    return AgentOutput(response=response, tool_calls=tool_events)
```

## Current Evaluators

| Evaluator | Type | Description |
|-----------|------|-------------|
| `ContainsExpected` | Deterministic | Response contains expected substrings |
| `ToolsUsed` | Deterministic | Expected tools were called |
| `AccuracyJudge` | LLM | Factual accuracy (0-1 score) |
| `HelpfulnessJudge` | LLM | Helpfulness (0-1 score) |

## Adding Test Cases

Edit `evals/dataset.py`:

```python
def create_dataset():
    dataset = Dataset(
        cases=[
            # Add new case
            Case(
                name="weather_query",
                inputs=AgentInput(user_input="What's the weather?"),
                expected_output=ExpectedOutput(
                    contains=["weather"],
                    tool_names=["get_weather"],
                ),
                metadata={"category": "tool_use"},
            ),
        ]
    )
    # Add evaluators
    dataset.add_evaluator(ContainsExpected())
    dataset.add_evaluator(create_accuracy_judge())
    return dataset
```

## Adding Custom Evaluators

Create in `evals/evaluator.py`:

```python
class ResponseLength(Evaluator[AgentInput, AgentOutput, ExpectedOutput]):
    """Score based on response length."""

    min_length: int = 10
    max_length: int = 500

    async def evaluate(self, ctx: EvaluatorContext) -> float:
        length = len(ctx.output.response)
        if length < self.min_length:
            return 0.0
        if length > self.max_length:
            return 0.5
        return 1.0
```

Then add to dataset:

```python
dataset.add_evaluator(ResponseLength(min_length=20))
```

## Running Evaluations

```bash
# Full evaluation
make evals

# Quick mode (fewer cases)
make evals-quick

# CLI options
uv run python -m evals.main --help

Options:
  --quick       Quick mode: 2 test cases
  --no-report   Don't save JSON report
  -v, --verbose Enable debug logging
```

## Reports

Reports are saved to `evals/reports/` as JSON:

```json
{
  "cases": [
    {
      "name": "greeting",
      "inputs": {"user_input": "Hello!"},
      "output": {"response": "Hello! How can I help?"},
      "scores": {
        "ContainsExpected": 1.0,
        "AccuracyJudge": 0.95
      }
    }
  ],
  "summary": {
    "total_cases": 5,
    "average_scores": {
      "ContainsExpected": 0.9,
      "AccuracyJudge": 0.85
    }
  }
}
```

## Logfire Integration

pydantic-evals has native [Logfire](https://pydantic.dev/logfire) integration for visualization.
When `LOGFIRE_TOKEN` is set in `.env`, evaluations are automatically traced:

```bash
# Add to .env
LOGFIRE_TOKEN=your-token
```

The evals CLI auto-configures Logfire when the token is present.
View results in the [Logfire dashboard](https://logfire.pydantic.dev).

## Best Practices

1. **Start with deterministic evaluators** - Fast feedback loop
2. **Add LLM judges for subjective criteria** - Accuracy, helpfulness, tone
3. **Use metadata for filtering** - Group cases by category
4. **Run quick mode during development** - Full eval in CI/CD
5. **Track scores over time** - Catch regressions

## Troubleshooting

**Missing OPENAI_API_KEY:**
```bash
# Ensure .env has the key
echo "OPENAI_API_KEY=sk-..." >> .env
```

**Database connection errors:**
```bash
# Start PostgreSQL
docker-compose up -d db

# Apply migrations
make migrate
```

**Import errors:**
```bash
# Reinstall dependencies
uv sync --dev
```
