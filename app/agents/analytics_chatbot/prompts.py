"""LLM prompts for the analytics chatbot.

Contains all prompt templates used by the chatbot nodes.
Supports loading optimized prompts from trained_prompts/ directory.
"""

import os
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

# Directory for optimized prompts (relative to project root)
TRAINED_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "trained_prompts"

# Environment variable to disable optimized prompts (for testing)
USE_OPTIMIZED_PROMPTS = os.environ.get("USE_OPTIMIZED_PROMPTS", "true").lower() == "true"


def _load_optimized_prompt(name: str) -> str | None:
    """Load an optimized prompt from disk if available.

    Args:
        name: Name of the prompt (e.g., 'sql_generator').

    Returns:
        Optimized prompt content, or None if not found.
    """
    if not USE_OPTIMIZED_PROMPTS:
        return None

    prompt_path = TRAINED_PROMPTS_DIR / f"{name}.txt"
    if prompt_path.exists():
        return prompt_path.read_text()
    return None


def _create_sql_generator_prompt(system_template: str | None = None) -> ChatPromptTemplate:
    """Create the SQL generator prompt template.

    Args:
        system_template: Optional custom system template.

    Returns:
        Configured ChatPromptTemplate.
    """
    if system_template is None:
        system_template = """You are an expert SQL generator for a mobile app analytics database.

DATABASE SCHEMA:
{schema}

EXAMPLES:
{examples}

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
{{
    "sql": "<your SQL query>",
    "assumptions": ["assumption 1", "assumption 2"]
}}"""

    return ChatPromptTemplate.from_messages(
        [
            ("system", system_template),
            ("human", "Question: {query}"),
        ]
    )


# =============================================================================
# Intent Classification
# =============================================================================

INTENT_CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an intent classifier for a mobile app analytics chatbot.

Classify the user's message into ONE of these categories:
- analytics_query: A new question about app data (installs, revenue, costs, etc.)
- follow_up: A question that references previous context (e.g., "what about iOS?", "and last month?")
- export_csv: Request to download/export data as CSV
- show_sql: Request to see the SQL query used
- off_topic: Not related to app analytics

Respond with JSON: {{"intent": "<category>", "confidence": <0.0-1.0>}}

App analytics topics include: installs, downloads, revenue, ads, in-app purchases,
UA cost, user acquisition, countries, platforms (iOS/Android), app names, dates,
comparisons, rankings, trends.""",
        ),
        (
            "human",
            """Conversation history:
{history}

Current message: {query}

Classify this message:""",
        ),
    ]
)

# =============================================================================
# Context Resolution
# =============================================================================

CONTEXT_RESOLVER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You analyze user questions in the context of conversation history and produce a clear, standalone query.

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

Return ONLY the resolved question, nothing else.""",
        ),
        (
            "human",
            """Conversation history:
{history}

Current question: {current_query}

Resolved question:""",
        ),
    ]
)

# =============================================================================
# SQL Generation
# =============================================================================

DB_SCHEMA = """
TABLE: app_metrics
COLUMNS:
- app_name (VARCHAR): Name of the mobile app (e.g., "Paint for Android", "Countdown iOS")
- platform (VARCHAR): Operating system - "iOS" or "Android"
- date (DATE): The reporting date
- country (VARCHAR): Geographic country where metrics were recorded
- installs (INTEGER): Number of app downloads
- in_app_revenue (DECIMAL): Revenue from in-app purchases
- ads_revenue (DECIMAL): Revenue from advertisements
- ua_cost (DECIMAL): User Acquisition Cost (marketing spend)

COMPUTED:
- total_revenue = in_app_revenue + ads_revenue
- net_revenue = total_revenue - ua_cost

NOTES:
- Data is daily granular
- Use SUM() for aggregating revenue/installs across dates
- "Popularity" typically means installs unless specified otherwise
- Revenue comparisons should consider total_revenue unless user specifies
"""

FEW_SHOT_EXAMPLES = """
Q: How many apps do we have?
SQL: SELECT COUNT(DISTINCT app_name) as app_count FROM app_metrics;
Assumptions: Counting unique app names across all platforms.

Q: How many Android apps do we have?
SQL: SELECT COUNT(DISTINCT app_name) as android_app_count FROM app_metrics WHERE platform = 'Android';
Assumptions: None.

Q: Which country generates the most revenue?
SQL: SELECT country, SUM(in_app_revenue + ads_revenue) as total_revenue
     FROM app_metrics
     GROUP BY country
     ORDER BY total_revenue DESC
     LIMIT 10;
Assumptions: Using all available data (no date filter specified). Revenue = in_app + ads.

Q: List all iOS apps sorted by popularity
SQL: SELECT app_name, SUM(installs) as total_installs
     FROM app_metrics
     WHERE platform = 'iOS'
     GROUP BY app_name
     ORDER BY total_installs DESC;
Assumptions: Popularity defined as total installs.

Q: Which apps had the biggest change in UA spend comparing Jan 2025 to Dec 2024?
SQL: WITH jan_2025 AS (
       SELECT app_name, SUM(ua_cost) as ua_jan
       FROM app_metrics
       WHERE date BETWEEN '2025-01-01' AND '2025-01-31'
       GROUP BY app_name
     ),
     dec_2024 AS (
       SELECT app_name, SUM(ua_cost) as ua_dec
       FROM app_metrics
       WHERE date BETWEEN '2024-12-01' AND '2024-12-31'
       GROUP BY app_name
     )
     SELECT
       COALESCE(j.app_name, d.app_name) as app_name,
       COALESCE(ua_jan, 0) as jan_2025_ua,
       COALESCE(ua_dec, 0) as dec_2024_ua,
       COALESCE(ua_jan, 0) - COALESCE(ua_dec, 0) as ua_change,
       CASE WHEN ua_dec > 0 THEN
         ROUND(((ua_jan - ua_dec) / ua_dec) * 100, 2)
       ELSE NULL END as change_percent
     FROM jan_2025 j
     FULL OUTER JOIN dec_2024 d ON j.app_name = d.app_name
     ORDER BY ABS(COALESCE(ua_jan, 0) - COALESCE(ua_dec, 0)) DESC;
Assumptions: Comparing full months. Showing absolute change.
"""

# Load optimized SQL generator prompt if available
_optimized_sql_prompt = _load_optimized_prompt("sql_generator")
SQL_GENERATOR_PROMPT = _create_sql_generator_prompt(_optimized_sql_prompt)

# =============================================================================
# Result Interpretation
# =============================================================================

INTERPRETER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You interpret SQL query results for a mobile app analytics chatbot.

Your job:
1. Summarize the results in natural language
2. Highlight key insights or trends if applicable

Keep responses concise but informative. For single-value results, just state the answer.
For tables, provide a brief summary of what the data shows.

Do NOT include the raw data in your response - that will be formatted separately.
Do NOT mention assumptions - they will be shown separately in the message footer.""",
        ),
        (
            "human",
            """Original question: {query}

Query returned {row_count} rows.
Column names: {columns}
Sample data (first 5 rows): {sample_data}

Provide your interpretation:""",
        ),
    ]
)

# =============================================================================
# Error Messages
# =============================================================================

SQL_RETRY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert SQL generator. The previous SQL query failed execution.
Fix the query based on the error message provided.

DATABASE SCHEMA:
{schema}

REFLECTION ON ERROR:
Analyze the error carefully. Common issues include:
- Column does not exist: Check column names against schema above
- Syntax error: Check SQL syntax (commas, quotes, keywords)
- Type mismatch: Ensure correct data types in comparisons
- Ambiguous column: Add table prefix to column names
- Division by zero: Add NULLIF or CASE WHEN guards
- Invalid date: Check date format (use 'YYYY-MM-DD')

SAFETY RULES (CRITICAL):
1. Generate ONLY SELECT or WITH statements
2. NEVER use: DROP, DELETE, UPDATE, INSERT, TRUNCATE, ALTER, CREATE, GRANT, REVOKE, EXEC, EXECUTE
3. Query must start with SELECT or WITH - no other statement types allowed

GENERATION RULES:
1. Always use appropriate aggregations (SUM, COUNT, AVG) for metrics
2. Include meaningful column aliases
3. Add LIMIT for potentially large result sets

Return JSON format:
{{
    "sql": "<your fixed SQL query>",
    "assumptions": ["assumption 1", "assumption 2"]
}}""",
        ),
        (
            "human",
            """Original question: {query}

Previous SQL that failed:
{previous_sql}

Error message: {error}

Generate a fixed SQL query:""",
        ),
    ]
)


# =============================================================================
# Prompt Management Utilities
# =============================================================================


def reload_sql_generator_prompt() -> ChatPromptTemplate:
    """Reload the SQL generator prompt, checking for optimized versions.

    Useful for reloading prompts after training without restarting the app.

    Returns:
        Reloaded ChatPromptTemplate.
    """
    global SQL_GENERATOR_PROMPT
    optimized = _load_optimized_prompt("sql_generator")
    SQL_GENERATOR_PROMPT = _create_sql_generator_prompt(optimized)
    return SQL_GENERATOR_PROMPT


def has_optimized_prompt(name: str) -> bool:
    """Check if an optimized prompt exists.

    Args:
        name: Name of the prompt (e.g., 'sql_generator').

    Returns:
        True if an optimized prompt file exists.
    """
    prompt_path = TRAINED_PROMPTS_DIR / f"{name}.txt"
    return prompt_path.exists()


def list_optimized_prompts() -> list[str]:
    """List all available optimized prompts.

    Returns:
        List of prompt names that have optimized versions.
    """
    if not TRAINED_PROMPTS_DIR.exists():
        return []
    return [p.stem for p in TRAINED_PROMPTS_DIR.glob("*.txt")]
