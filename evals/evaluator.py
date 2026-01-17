"""Core evaluation logic using pydantic-evals.

Provides evaluators for scoring agent responses.
"""

from pydantic_evals.evaluators import Evaluator, EvaluatorContext, LLMJudge

from evals.schemas import AgentInput, AgentOutput, ExpectedOutput


class ContainsExpected(Evaluator[AgentInput, AgentOutput, ExpectedOutput]):
    """Check if response contains expected substrings."""

    async def evaluate(
        self, ctx: EvaluatorContext[AgentInput, AgentOutput, ExpectedOutput]
    ) -> float:
        """Evaluate if response contains expected content.

        Args:
            ctx: Evaluation context with input, output, and expected values.

        Returns:
            Score between 0 and 1 based on matches.
        """
        if not ctx.expected_output or not ctx.expected_output.contains:
            return 1.0

        response_lower = ctx.output.response.lower()
        matches = sum(1 for s in ctx.expected_output.contains if s.lower() in response_lower)
        return matches / len(ctx.expected_output.contains)


class ToolsUsed(Evaluator[AgentInput, AgentOutput, ExpectedOutput]):
    """Check if expected tools were called."""

    async def evaluate(
        self, ctx: EvaluatorContext[AgentInput, AgentOutput, ExpectedOutput]
    ) -> float:
        """Evaluate if expected tools were called.

        Args:
            ctx: Evaluation context with input, output, and expected values.

        Returns:
            Score between 0 and 1 based on tool matches.
        """
        if not ctx.expected_output or not ctx.expected_output.tool_names:
            return 1.0

        called_tools = {tc.get("name", "") for tc in ctx.output.tool_calls}
        expected_tools = set(ctx.expected_output.tool_names)
        matches = len(called_tools & expected_tools)
        return matches / len(expected_tools)


def create_accuracy_judge(model: str = "openai:gpt-4o-mini") -> LLMJudge:
    """Create an LLM judge for accuracy evaluation.

    Args:
        model: Model to use for evaluation (default: gpt-4o-mini).

    Returns:
        Configured LLMJudge evaluator.
    """
    return LLMJudge(
        model=model,
        include_input=True,
        rubric="""Evaluate the accuracy of the agent's response.

## Scoring Guidelines

- **Score 1.0**: Completely accurate response that fully addresses the user's input.
  The information is correct and relevant.

- **Score 0.75**: Mostly accurate with minor omissions that don't significantly
  impact usefulness.

- **Score 0.5**: Partially accurate. Addresses some aspects but misses important
  points or contains some inaccuracies.

- **Score 0.25**: Mostly inaccurate with only minor relevant information.

- **Score 0.0**: Completely inaccurate, irrelevant, or nonsensical.

## Considerations

- Did the agent correctly understand the user's intent?
- Is the factual information provided correct?
- Are tool calls used appropriately?
- Does the response fully address the question?
""",
    )


def create_helpfulness_judge(model: str = "openai:gpt-4o-mini") -> LLMJudge:
    """Create an LLM judge for helpfulness evaluation.

    Args:
        model: Model to use for evaluation (default: gpt-4o-mini).

    Returns:
        Configured LLMJudge evaluator.
    """
    return LLMJudge(
        model=model,
        include_input=True,
        rubric="""Evaluate how helpful the agent's response is.

## Scoring Guidelines

- **Score 1.0**: Extremely helpful. Provides clear, actionable information
  that fully addresses the user's needs.

- **Score 0.75**: Helpful with minor room for improvement.

- **Score 0.5**: Somewhat helpful but missing key information or clarity.

- **Score 0.25**: Minimally helpful. Vague or incomplete.

- **Score 0.0**: Not helpful at all. Fails to provide useful information.

## Considerations

- Is the response clear and easy to understand?
- Does it provide actionable information?
- Is the tone appropriate and professional?
""",
    )
