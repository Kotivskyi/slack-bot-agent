"""PromptTemplate wrappers for agent-lightning training.

Provides wrappers around existing chatbot prompts for use with
agent-lightning's APO algorithm.
"""

from pathlib import Path

from agentlightning import PromptTemplate

from app.agents.analytics_chatbot.prompts import (
    DB_SCHEMA,
    FEW_SHOT_EXAMPLES,
)

# Directory for storing optimized prompts
TRAINED_PROMPTS_DIR = Path(__file__).parent.parent / "trained_prompts"


def get_sql_generator_template() -> PromptTemplate:
    """Create a PromptTemplate for the SQL generator prompt.

    The SQL generator is the primary target for optimization as it has
    the highest impact on end-to-end query accuracy.

    Returns:
        PromptTemplate configured for agent-lightning training.
    """
    # The system prompt content that will be optimized
    template = """You are an expert SQL generator for a mobile app analytics database.

DATABASE SCHEMA:
{{ schema }}

EXAMPLES:
{{ examples }}

SAFETY RULES (CRITICAL):
1. Generate ONLY SELECT or WITH statements
2. NEVER use: DROP, DELETE, UPDATE, INSERT, TRUNCATE, ALTER, CREATE, GRANT, REVOKE, EXEC, EXECUTE
3. Query must start with SELECT or WITH - no other statement types allowed

GENERATION RULES:
1. Always use appropriate aggregations (SUM, COUNT, AVG) for metrics
2. Include meaningful column aliases
3. Add LIMIT for potentially large result sets
4. Note any assumptions made about ambiguous terms

Return JSON format:
{
    "sql": "<your SQL query>",
    "assumptions": ["assumption 1", "assumption 2"]
}"""

    return PromptTemplate(template=template, engine="jinja")


def get_intent_classifier_template() -> PromptTemplate:
    """Create a PromptTemplate for the intent classifier prompt.

    Returns:
        PromptTemplate configured for agent-lightning training.
    """
    template = """You are an intent classifier for a mobile app analytics chatbot.

Classify the user's message into ONE of these categories:
- analytics_query: A new question about app data (installs, revenue, costs, etc.)
- follow_up: A question that references previous context (e.g., "what about iOS?", "and last month?")
- export_csv: Request to download/export data as CSV
- show_sql: Request to see the SQL query used
- off_topic: Not related to app analytics

Respond with JSON: {"intent": "<category>", "confidence": <0.0-1.0>}

App analytics topics include: installs, downloads, revenue, ads, in-app purchases,
UA cost, user acquisition, countries, platforms (iOS/Android), app names, dates,
comparisons, rankings, trends."""

    return PromptTemplate(template=template, engine="jinja")


def get_context_resolver_template() -> PromptTemplate:
    """Create a PromptTemplate for the context resolver prompt.

    Returns:
        PromptTemplate configured for agent-lightning training.
    """
    template = """You analyze user questions in the context of conversation history and produce a clear, standalone query.

Given a user's question and conversation history, determine if the question:
1. Is a STANDALONE question that doesn't need any context - return it unchanged
2. Is a FOLLOW-UP that references previous conversation - incorporate that context
3. Might SEEM like a follow-up but is about a NEW TOPIC - return it unchanged

Rules:
- If the question is standalone and complete, return it unchanged
- If the question references previous context (pronouns like "it", "those", "that", comparisons like "and Android?", "what about iOS?"), incorporate that context
- If there's conversation history but the question is clearly about a new topic, return the question unchanged
- Always return a complete, self-contained question

Examples:

History: (empty)
Current: "How many apps do we have?"
Resolved: "How many apps do we have?"

History: "How many Android apps do we have?" → "We have 15 Android apps"
Current: "what about iOS?"
Resolved: "How many iOS apps do we have?"

History: "Which country generates the most revenue?" → "USA with $1.2M"
Current: "Show me installs for Paint app"
Resolved: "Show me installs for Paint app"

History: "Show me revenue for Gaming category" → "Total revenue is $5M"
Current: "break it down by country"
Resolved: "Show me revenue for Gaming category broken down by country"

History: "What's the UA cost for Game A?" → "UA cost is $50,000"
         "And Game B?" → "UA cost is $30,000"
Current: "compare them"
Resolved: "Compare the UA cost between Game A and Game B"

Return ONLY the resolved question, nothing else."""

    return PromptTemplate(template=template, engine="jinja")


def get_default_resources() -> dict[str, PromptTemplate]:
    """Get default resources for training.

    Returns:
        Dictionary of named PromptTemplates for agent-lightning.
    """
    return {
        "sql_generator": get_sql_generator_template(),
        "intent_classifier": get_intent_classifier_template(),
        "context_resolver": get_context_resolver_template(),
    }


def load_optimized_prompt(name: str) -> str | None:
    """Load an optimized prompt from disk if available.

    Args:
        name: Name of the prompt (e.g., 'sql_generator').

    Returns:
        Optimized prompt content, or None if not found.
    """
    prompt_path = TRAINED_PROMPTS_DIR / f"{name}.txt"
    if prompt_path.exists():
        return prompt_path.read_text()
    return None


def save_optimized_prompt(name: str, content: str) -> Path:
    """Save an optimized prompt to disk.

    Args:
        name: Name of the prompt (e.g., 'sql_generator').
        content: The optimized prompt content.

    Returns:
        Path to the saved prompt file.
    """
    TRAINED_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    prompt_path = TRAINED_PROMPTS_DIR / f"{name}.txt"
    prompt_path.write_text(content)
    return prompt_path


def get_schema_and_examples() -> tuple[str, str]:
    """Get the database schema and few-shot examples.

    These are constants that don't need optimization but are
    needed for rendering the SQL generator prompt.

    Returns:
        Tuple of (schema, examples) strings.
    """
    return DB_SCHEMA, FEW_SHOT_EXAMPLES
