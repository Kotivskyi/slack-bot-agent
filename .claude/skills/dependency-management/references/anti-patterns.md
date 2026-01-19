# Anti-Patterns to Avoid

## Don't: Import FastAPI deps in nodes

```python
# BAD - couples node to FastAPI
from app.api.deps import get_db

async def my_node(state: ChatbotState) -> dict:
    db = get_db()  # This won't work and breaks architecture
    ...
```

**Why:** Nodes should be decoupled from FastAPI. Resources come via `config["configurable"]`.

---

## Don't: Put resources in LangGraph state

```python
# BAD - state should be serializable data only
class ChatbotState(TypedDict):
    db: AsyncSession  # Don't do this
    slack_client: WebClient  # Don't do this
```

**Why:** State must be serializable for checkpointing. Non-serializable resources go in config.

---

## Don't: Create db sessions in nodes

```python
# BAD - breaks transaction management
async def my_node(state: ChatbotState, config: RunnableConfig) -> dict:
    async with get_db_context() as db:  # Don't create new sessions
        repo = MetricsRepository(db)
        ...
```

**Why:** The service layer owns the db session. Nodes should use repos passed via config.

---

## Don't: Commit in repositories

```python
# BAD - service should control transaction boundaries
class MetricsRepository:
    async def save_query(self, query: Query):
        self.db.add(query)
        await self.db.commit()  # Don't commit here
```

**Why:** Transaction boundaries belong at the service/dependency level.

---

## Do: Flush in repositories, commit in dependency

```python
# Repository - just flush
class MetricsRepository:
    async def save_query(self, query: Query):
        self.db.add(query)
        await self.db.flush()  # Just flush

# Dependency handles commit/rollback
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

---

## Summary Table

| Anti-Pattern | Correct Pattern |
|--------------|-----------------|
| Import FastAPI deps in nodes | Pass via `config["configurable"]` |
| Resources in LangGraph state | Resources in config, data in state |
| Create db sessions in nodes | Use repos from config |
| Commit in repositories | Flush in repos, commit in dependency |
