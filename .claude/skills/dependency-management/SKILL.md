---
name: dependency-management
description: FastAPI and LangGraph dependency injection patterns. Use when (1) adding new dependencies or services to FastAPI routes, (2) creating LangGraph nodes that need database or external client access, (3) bridging FastAPI routes with LangGraph workflows, (4) deciding where to put resources vs workflow data, (5) writing repository or service layer code, or (6) debugging dependency injection issues.
---

# Dependency Management Best Practices

**Core Principle:** FastAPI dependencies provide resources. LangGraph state carries workflow data. The Service layer bridges them.

```
┌─────────────────────────────────────────────────────────────────┐
│ FastAPI Layer                                                   │
│   Depends(get_db) → AsyncSession                                │
│   Depends(get_current_user) → User                              │
│   Depends(get_slack_client) → WebClient                         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ inject into
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Service Layer (Bridge)                                          │
│   - Receives FastAPI deps via constructor                       │
│   - Creates repositories from db session                        │
│   - Initializes LangGraph state                                 │
│   - Passes repos to graph via config["configurable"]            │
└──────────────────────────┬──────────────────────────────────────┘
                           │ runs graph with
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ LangGraph Layer                                                 │
│   State: user_query, intent, sql, results, response             │
│   Config: repos, clients (accessed via config["configurable"])  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Reference

| Layer | What Goes Here | Example |
|-------|---------------|---------|
| FastAPI Depends | Resources (db, clients, config) | `db: AsyncSession = Depends(get_db)` |
| LangGraph State | Serializable workflow data | `user_query`, `intent`, `results` |
| LangGraph Config | Non-serializable resources for nodes | `config["configurable"]["metrics_repo"]` |

## Checklist

Before adding a new dependency, ask:

- [ ] Is it a resource (db, client, config)? → FastAPI dependency
- [ ] Is it workflow data? → LangGraph state
- [ ] Does a node need a resource? → Pass via `config["configurable"]`
- [ ] Is the state serializable? → Only primitive types and TypedDicts
- [ ] Are transactions managed at the right level? → Service/dependency, not repository

For detailed patterns and examples, see:
- [Implementation Patterns](references/implementation-patterns.md) - Route → Service → Node → Repository code
- [Anti-Patterns to Avoid](references/anti-patterns.md) - Common mistakes and why they break
- [Testing Patterns](references/testing-patterns.md) - Unit and integration test examples
