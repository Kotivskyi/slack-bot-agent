"""Dataset and cases for agent evaluation.

Defines test cases using pydantic-evals Dataset and Case.
"""

from pydantic_evals import Case, Dataset

from evals.evaluator import (
    ContainsExpected,
    ToolsUsed,
    create_accuracy_judge,
    create_helpfulness_judge,
)
from evals.schemas import AgentInput, AgentOutput, ExpectedOutput


def create_dataset() -> Dataset[AgentInput, AgentOutput, ExpectedOutput]:
    """Create the evaluation dataset with test cases.

    Returns:
        Dataset containing test cases for agent evaluation.
    """
    dataset: Dataset[AgentInput, AgentOutput, ExpectedOutput] = Dataset(
        cases=[
            Case(
                name="greeting",
                inputs=AgentInput(user_input="Hello, how are you?"),
                expected_output=ExpectedOutput(contains=["hello", "help"]),
                metadata={"category": "greeting"},
            ),
            Case(
                name="time_query",
                inputs=AgentInput(user_input="What time is it?"),
                expected_output=ExpectedOutput(tool_names=["current_datetime"]),
                metadata={"category": "tool_use"},
            ),
            Case(
                name="help_request",
                inputs=AgentInput(user_input="What can you help me with?"),
                expected_output=ExpectedOutput(contains=["help", "assist"]),
                metadata={"category": "capabilities"},
            ),
            Case(
                name="date_query",
                inputs=AgentInput(user_input="What is today's date?"),
                expected_output=ExpectedOutput(tool_names=["current_datetime"]),
                metadata={"category": "tool_use"},
            ),
            Case(
                name="polite_farewell",
                inputs=AgentInput(user_input="Thank you, goodbye!"),
                expected_output=ExpectedOutput(contains=["goodbye", "welcome"]),
                metadata={"category": "greeting"},
            ),
        ]
    )

    # Add evaluators to the dataset
    dataset.add_evaluator(ContainsExpected())
    dataset.add_evaluator(ToolsUsed())
    dataset.add_evaluator(create_accuracy_judge())
    dataset.add_evaluator(create_helpfulness_judge())

    return dataset


def create_quick_dataset() -> Dataset[AgentInput, AgentOutput, ExpectedOutput]:
    """Create a quick dataset with fewer cases for fast iteration.

    Returns:
        Dataset with 2 test cases.
    """
    dataset: Dataset[AgentInput, AgentOutput, ExpectedOutput] = Dataset(
        cases=[
            Case(
                name="greeting",
                inputs=AgentInput(user_input="Hello!"),
                expected_output=ExpectedOutput(contains=["hello"]),
            ),
            Case(
                name="time_query",
                inputs=AgentInput(user_input="What time is it?"),
                expected_output=ExpectedOutput(tool_names=["current_datetime"]),
            ),
        ]
    )

    dataset.add_evaluator(create_accuracy_judge())

    return dataset
