# Accuracy Metric

Evaluate whether the agent's response accurately addresses the user's question or request.

## Scoring Guidelines

- **Score 1.0**: Completely accurate response that fully addresses all aspects of the user's input. The information provided is correct and relevant.

- **Score 0.75**: Mostly accurate response with minor omissions or imprecisions that don't significantly impact the usefulness of the answer.

- **Score 0.5**: Partially accurate response. Addresses some aspects of the question but misses important points or contains some inaccuracies.

- **Score 0.25**: Mostly inaccurate response with only minor relevant information. Contains significant errors or misunderstandings.

- **Score 0.0**: Completely inaccurate, irrelevant, or nonsensical response that fails to address the user's input in any meaningful way.

## Considerations

- Did the agent correctly understand the user's intent?
- Is the factual information provided correct?
- Are tool calls used appropriately and their results interpreted correctly?
- Does the response fully address the question or only partially?
