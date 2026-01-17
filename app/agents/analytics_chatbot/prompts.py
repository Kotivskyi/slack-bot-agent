"""LLM prompts for the analytics chatbot.

Contains all prompt templates used by the chatbot nodes.
"""

from langchain_core.prompts import ChatPromptTemplate

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
            """You resolve ambiguous follow-up questions by incorporating context from conversation history.

Your task: Rewrite the current question as a complete, standalone question that includes all necessary context.

Examples:
- History: "How many Android apps do we have?" → "We have 15 Android apps"
- Current: "what about iOS?"
- Resolved: "How many iOS apps do we have?"

- History: "Which country generates the most revenue?" → "USA with $1.2M"
- Current: "and the least?"
- Resolved: "Which country generates the least revenue?"

- History: "Show me installs for Paint app in January"
- Current: "compare to February"
- Resolved: "Compare installs for Paint app between January and February"

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

SQL_GENERATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert SQL generator for a mobile app analytics database.

DATABASE SCHEMA:
{schema}

EXAMPLES:
{examples}

RULES:
1. Generate ONLY SELECT statements (no INSERT, UPDATE, DELETE, DROP)
2. Always use appropriate aggregations (SUM, COUNT, AVG) for metrics
3. Include meaningful column aliases
4. Add LIMIT for potentially large result sets
5. Note any assumptions made about ambiguous terms

Return JSON format:
{{
    "sql": "<your SQL query>",
    "assumptions": ["assumption 1", "assumption 2"]
}}""",
        ),
        ("human", "Question: {query}"),
    ]
)

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
2. Highlight key insights
3. Mention any assumptions that were made

Keep responses concise but informative. For single-value results, just state the answer.
For tables, provide a brief summary of what the data shows.

Do NOT include the raw data in your response - that will be formatted separately.""",
        ),
        (
            "human",
            """Original question: {query}

SQL assumptions made: {assumptions}

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
            """You are an expert SQL generator. The previous SQL query failed validation.
Fix the query based on the error message provided.

DATABASE SCHEMA:
{schema}

RULES:
1. Generate ONLY SELECT statements (no INSERT, UPDATE, DELETE, DROP)
2. Always use appropriate aggregations (SUM, COUNT, AVG) for metrics
3. Include meaningful column aliases
4. Add LIMIT for potentially large result sets

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
