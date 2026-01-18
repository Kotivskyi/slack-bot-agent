"""Core evaluation logic using pydantic-evals.

Provides evaluators for scoring agent responses.
"""

from pydantic_evals.evaluators import Evaluator, EvaluatorContext, LLMJudge

from evals.schemas import (
    AgentInput,
    AgentOutput,
    AnalyticsExpected,
    AnalyticsInput,
    AnalyticsOutput,
    ExpectedOutput,
)


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


# Analytics Chatbot Evaluators


class IntentMatch(Evaluator[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]):
    """Check if the classified intent matches expected intent."""

    async def evaluate(
        self, ctx: EvaluatorContext[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]
    ) -> float:
        """Evaluate if intent classification is correct.

        Args:
            ctx: Evaluation context with input, output, and expected values.

        Returns:
            1.0 if intent matches, 0.0 otherwise.
        """
        if not ctx.expected_output or ctx.expected_output.intent is None:
            return 1.0

        return 1.0 if ctx.output.intent == ctx.expected_output.intent else 0.0


class SQLGenerated(Evaluator[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]):
    """Check if SQL was generated when expected."""

    async def evaluate(
        self, ctx: EvaluatorContext[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]
    ) -> float:
        """Evaluate if SQL generation matches expectation.

        Args:
            ctx: Evaluation context with input, output, and expected values.

        Returns:
            1.0 if SQL presence matches expectation, 0.0 otherwise.
        """
        if not ctx.expected_output or ctx.expected_output.should_generate_sql is None:
            return 1.0

        has_sql = ctx.output.generated_sql is not None and len(ctx.output.generated_sql) > 0
        return 1.0 if has_sql == ctx.expected_output.should_generate_sql else 0.0


class SQLContains(Evaluator[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]):
    """Check if generated SQL contains expected substrings."""

    async def evaluate(
        self, ctx: EvaluatorContext[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]
    ) -> float:
        """Evaluate if SQL contains expected keywords/clauses.

        Args:
            ctx: Evaluation context with input, output, and expected values.

        Returns:
            Score between 0 and 1 based on substring matches.
        """
        if not ctx.expected_output or not ctx.expected_output.sql_contains:
            return 1.0

        if not ctx.output.generated_sql:
            return 0.0

        sql_upper = ctx.output.generated_sql.upper()
        matches = sum(1 for s in ctx.expected_output.sql_contains if s.upper() in sql_upper)
        return matches / len(ctx.expected_output.sql_contains)


class ResponseContains(Evaluator[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]):
    """Check if response contains expected substrings."""

    async def evaluate(
        self, ctx: EvaluatorContext[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]
    ) -> float:
        """Evaluate if response contains expected content.

        Args:
            ctx: Evaluation context with input, output, and expected values.

        Returns:
            Score between 0 and 1 based on substring matches.
        """
        if not ctx.expected_output or not ctx.expected_output.response_contains:
            return 1.0

        response_lower = ctx.output.text.lower()
        matches = sum(1 for s in ctx.expected_output.response_contains if s.lower() in response_lower)
        return matches / len(ctx.expected_output.response_contains)


class CSVExport(Evaluator[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]):
    """Check if CSV content is present when expected."""

    async def evaluate(
        self, ctx: EvaluatorContext[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]
    ) -> float:
        """Evaluate if CSV export matches expectation.

        Args:
            ctx: Evaluation context with input, output, and expected values.

        Returns:
            1.0 if CSV presence matches expectation, 0.0 otherwise.
        """
        if not ctx.expected_output or ctx.expected_output.should_have_csv is None:
            return 1.0

        has_csv = ctx.output.csv_content is not None and len(ctx.output.csv_content) > 0
        return 1.0 if has_csv == ctx.expected_output.should_have_csv else 0.0


class ResponseFormatMatch(Evaluator[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]):
    """Check if response format matches expected format."""

    async def evaluate(
        self, ctx: EvaluatorContext[AnalyticsInput, AnalyticsOutput, AnalyticsExpected]
    ) -> float:
        """Evaluate if response format is correct.

        Args:
            ctx: Evaluation context with input, output, and expected values.

        Returns:
            1.0 if format matches, 0.0 otherwise.
        """
        if not ctx.expected_output or ctx.expected_output.response_format is None:
            return 1.0

        return 1.0 if ctx.output.response_format == ctx.expected_output.response_format else 0.0


def create_analytics_judge(model: str = "openai:gpt-4o-mini") -> LLMJudge:
    """Create an LLM judge for analytics response evaluation.

    Args:
        model: Model to use for evaluation (default: gpt-4o-mini).

    Returns:
        Configured LLMJudge evaluator.
    """
    return LLMJudge(
        model=model,
        include_input=True,
        rubric="""Evaluate the analytics chatbot response quality.

## Scoring Guidelines

- **Score 1.0**: Excellent response that correctly answers the analytics question.
  SQL is valid, results are well-interpreted, and assumptions are clearly stated.

- **Score 0.75**: Good response with minor issues. Answer is mostly correct
  but may have small interpretation gaps or missing context.

- **Score 0.5**: Adequate response. Partially addresses the question but
  may have SQL issues, unclear interpretation, or missing assumptions.

- **Score 0.25**: Poor response. Significant issues with SQL, interpretation,
  or relevance to the question.

- **Score 0.0**: Failed response. SQL errors, wrong data, or completely
  irrelevant answer.

## Considerations

- Does the SQL correctly query for what the user asked?
- Is the interpretation of results accurate and clear?
- Are assumptions documented when the query is ambiguous?
- Is the response format appropriate (simple text vs table)?
- For off-topic queries, is the decline polite and helpful?
""",
    )
