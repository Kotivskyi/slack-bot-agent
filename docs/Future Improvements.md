# Roadmap: Further Development

---

## 1. Security Measures

### Current (✅ Done)
- **Read-only DB** — Prevents data modification
- **SQL allowlisting** — Only SELECT/WITH in prompts
- **Slack signature verification** — HMAC-SHA256

### Before Production
- **SQL runtime validation** — Defense-in-depth, reject dangerous patterns before execution
- **User permissions** — Role-based access to sensitive data

---

## 2. Upcoming Features

### High Priority
| Feature | Value |
|---------|-------|
| **Richer data model** | Multi-currency, acquisition sources, revenue types |
| **Data pipeline** | Scheduled job to populate analytics DB |
| **User permissions** | Role-based access to sensitive data |

### Medium Priority
| Feature | Value |
|---------|-------|
| Scheduled reports | "Send revenue daily at 9am" |
| Anomaly alerts | "Notify if revenue drops >20%" |
| Streaming responses | Better UX for complex queries |
| Chart generation | Visual data in Slack |

---

## 3. Production Checklist (Prioritized)

### P0 — Must Have
- SQL runtime validation
- Sample data population
- Cost alerts (AWS + LLM)
- User permissions management
- Regression checklist for manual QA

### P1 — Should Have
- Integration tests
- CI pipeline (GitHub Actions)
- Jailbreak testing
- Separate DB instance for publicly avaiable data
- Rate limiting
- Query timeout
- Scheduled data pipeline to populate analytics DB
- More robust evals

### P2 — Post-Launch
- CD pipeline
- Infrastructure as Code
- Online evals (👍/👎)
- LiteLLM (fallback models)
- AWS Lambda + SQS
- Prompt management tool (versioning, A/B testing)
