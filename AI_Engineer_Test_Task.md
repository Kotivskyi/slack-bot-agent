# AI Engineer Challenge

## Objective
Build an internal Slack chatbot for data analytics and business intelligence that can answer questions about the Rounds apps portfolio. The chatbot works with an SQL database, converting user questions into SQL statements, executing them, and providing users with interpreted, formatted data. It should determine when to display a simple interpretation of the results and when to show the raw data. It should also support follow-up questions.

Additionally:
- Users should be able to request the SQL statement used to answer their questions.
- Users should be able to download the raw data in CSV format.

## Requirements

### Database
Provide the chatbot with a simple database schema containing the following columns:

**Columns**
- **App Name** — The name of a mobile app (e.g., Paint for Android, Countdown iOS)
- **Platform** — The operating system (iOS or Android)
- **Date** — The specific date for the data being reported
- **Country** — The geographic country where the app metrics were recorded
- **Installs** — The number of times the app was downloaded by users
- **In-App Revenue** — Revenue generated from purchases made within the app (e.g., premium features, virtual goods, subscriptions)
- **Ads Revenue** — Revenue earned from advertisements displayed within the app
- **UA Cost** — User Acquisition Cost — the amount spent on marketing and advertising to acquire new app users

You may use any relational DBMS of your choice. Please generate your own sample data for demonstration purposes.

## Supported Question Types
The chatbot handles a wide range of data requests while maintaining a natural conversational flow that allows for follow-up questions/requests. It intelligently interprets user intent and provides responses with an appropriate level of detail.

- It processes natural language queries related to the app portfolio and provides responses either in plain text or as detailed tables, depending on query complexity.
- Table responses include clear descriptions and note any assumptions made.
- Users can ask follow-up questions, and the conversation context is maintained.
- Users can export query results as CSV files.
- Users can request the underlying SQL statements used to generate answers.
- Off-topic questions are politely declined to maintain conversation focus on app portfolio analytics.

## Example scenarios

### Simple questions
**user:** how many apps do we have?  
**bot:** ​[simple answer without a CSV table]

**user:** how many android apps do we have?  
**bot:** ​[simple answer without a CSV table]

**user:** what about ios?  
**bot:** ​[follow-up answer showing the bot understood the question]

### More complex questions
**user:** which country generates the most revenue?  
**bot:** ​[table with country name, total revenue, plus a brief text summary explaining timeframe assumptions]

**user:** List all ios apps sorted by their popularity  
**bot:** ​[table of iOS apps sorted by popularity, plus an explanation of how “popularity” was defined]

**user:** Which apps had the biggest change in UA spend comparing Jan 2025 to Dec 2024?  
**bot:** ​[table showing apps with largest UA spend changes, optionally with extra columns for added context]

### CSV export requests
**user:** how many apps do we have?  
**bot:** ​[answer]

**user:** export this as csv  
**bot:** ​[confirmation message with CSV download link or button]

### SQL statement requests
**user:** how many apps do we have?  
**bot:** ​[answer]

**user:** how many iOS apps do we have?  
**bot:** ​[answer]

**user:** show me the SQL you used to retrieve all the apps  
**bot:** ​[SQL used for the first question (total apps)]

## Observability and Traceability
- Use LangSmith or other LLM observability platform to be able to x-ray into inner working of the agent.

## Deliverables
- Submit your solution as a GitHub repository with clear setup and deployment instructions, including how to install the Slack app in a new workspace.
- Prepare for a 40 minutes presentation session with the CTO and Lead AI Engineer (20 minutes presentation + 20 minutes Q&A).
- Have a plan on further development. Think of:
  - Security measures (user-level access permissions)
  - Upcoming chatbot features
  - A prioritized list of improvements required before deploying to production

If you have any questions, please feel free to contact Martin via Telegram (https://t.me/mlukasik) or email (martin.l@rounds.com).

## Note
The challenge does not specify particular technical requirements. You should select suitable technologies and be prepared to justify your choices during the presentation.

The primary technical constraint is that the chatbot must run within Slack (you can use a free Developer Sandbox for testing). It is recommended to utilize Slack features such as AI Assistants and Code Snippets.

## Evaluation Criteria
- The basic MVP is functional and free of unexpected bugs *(Note: nobody wants to hire someone who generates production code entirely with AI and doesn't even review it)*.
- The chatbot is optimized for cost-effective token usage (e.g., it could include a smart solution for CSV exports and SQL requests so that it doesn’t regenerate the SQL or data each time a user requests a CSV export or SQL retrieval).
- The chosen architecture is scalable (in terms of feature extension) and the codebase is maintainable.
- The roadmap for further development is well-thought-out, innovative, and practical.
