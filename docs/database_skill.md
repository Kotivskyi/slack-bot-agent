# Database Skill: Repositories, Services & Pydantic Models

Best practices for working with the database layer in this FastAPI + PostgreSQL project.

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   API Routes    │────▶│    Services     │────▶│  Repositories   │
│  (HTTP layer)   │     │ (business logic)│     │  (data access)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
┌─────────────────┐                                     ▼
│ Pydantic Schemas│◀─────────────────────────▶┌─────────────────┐
│ (Create/Update/ │                           │  SQLAlchemy     │
│    Response)    │                           │    Models       │
└─────────────────┘                           └─────────────────┘
```

## Core Principles

| Principle | Description |
|-----------|-------------|
| **Session per request** | Pass `AsyncSession` to methods, don't store in `__init__` |
| **Flush, don't commit** | Repositories use `db.flush()` — let services/routes manage transactions |
| **Thin routes** | Routes validate input, delegate to services |
| **Domain exceptions** | Services raise `NotFoundError`, `AlreadyExistsError`, etc. |
| **Async everywhere** | All DB operations use `async/await` |

---

## Quick Reference

| Layer | Location | Purpose |
|-------|----------|---------|
| Model | `app/db/models/` | SQLAlchemy table definition |
| Schema | `app/schemas/` | Pydantic validation (Create/Update/Response) |
| Repository | `app/repositories/` | Database CRUD operations |
| Service | `app/services/` | Business logic, orchestration |
| Route | `app/api/routes/` | HTTP endpoints |

| Schema Type | Purpose | Field Requirements |
|-------------|---------|-------------------|
| `XxxCreate` | Input for creation | Required fields only |
| `XxxUpdate` | Input for updates | All fields optional |
| `XxxResponse` | API output | All fields + timestamps |

---

## Step 1: Create SQLAlchemy Model

Location: `app/db/models/`

```python
# app/db/models/user.py
"""User database model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class User(Base):
    """User model for storing user information."""

    __tablename__ = "users"

    # Primary key with UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Required fields
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Optional fields
    slack_id: Mapped[str | None] = mapped_column(
        String(50), unique=True, nullable=True
    )

    # Timestamps (auto-managed)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
```

Export in `app/db/models/__init__.py`:
```python
from app.db.models.base import Base
from app.db.models.user import User

__all__ = ["Base", "User"]
```

---

## Step 2: Create Pydantic Schemas

Location: `app/schemas/`

```python
# app/schemas/user.py
"""User Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.base import BaseSchema


# --- Create Schema ---
class UserCreate(BaseModel):
    """Schema for creating a user.

    Only required fields. No defaults for critical data.
    """
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    slack_id: str | None = None


# --- Update Schema ---
class UserUpdate(BaseModel):
    """Schema for updating a user.

    All fields optional — only provided fields will be updated.
    """
    email: EmailStr | None = None
    name: str | None = Field(None, min_length=1, max_length=255)
    slack_id: str | None = None


# --- Response Schema ---
class UserResponse(BaseSchema):
    """Schema for user response.

    Inherits from BaseSchema for `from_attributes=True` config.
    """
    id: UUID
    email: str
    name: str
    slack_id: str | None
    created_at: datetime
    updated_at: datetime | None
```

Export in `app/schemas/__init__.py`:
```python
from app.schemas.user import UserCreate, UserResponse, UserUpdate

__all__ = ["UserCreate", "UserResponse", "UserUpdate"]
```

---

## Step 3: Create Repository

Location: `app/repositories/`

**Always extend `BaseRepository`** for entity repositories:

```python
# app/repositories/user.py
"""User repository for database operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.repositories.base import BaseRepository
from app.schemas.user import UserCreate, UserUpdate


class UserRepository(BaseRepository[User, UserCreate, UserUpdate]):
    """Repository for User entity.

    Inherits standard CRUD operations from BaseRepository:
    - get(db, id) -> User | None
    - get_multi(db, skip, limit) -> list[User]
    - create(db, obj_in) -> User
    - update(db, db_obj, obj_in) -> User
    - delete(db, id) -> User | None
    """

    def __init__(self):
        super().__init__(User)

    # Custom query methods
    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        """Get user by email address."""
        query = select(User).where(User.email == email)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_slack_id(self, db: AsyncSession, slack_id: str) -> User | None:
        """Get user by Slack ID."""
        query = select(User).where(User.slack_id == slack_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()
```

Export in `app/repositories/__init__.py`:
```python
from app.repositories.base import BaseRepository
from app.repositories.user import UserRepository

__all__ = ["BaseRepository", "UserRepository"]
```

> **Note:** `AnalyticsRepository` exists for executing raw SQL from the analytics chatbot. This is a special-purpose class, not a pattern to follow for new entities.

---

## Step 4: Create Service

Location: `app/services/`

```python
# app/services/user.py
"""User service for business logic."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.db.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)


class UserService:
    """Service for user-related operations.

    Holds db session in __init__ (unlike repositories).
    Orchestrates repositories and enforces business rules.
    """

    def __init__(self, db: AsyncSession):
        self._db = db
        self._repository = UserRepository()

    async def get_user(self, user_id: str) -> User:
        """Get user by ID.

        Raises:
            NotFoundError: If user doesn't exist.
        """
        user = await self._repository.get(self._db, user_id)
        if not user:
            raise NotFoundError(f"User {user_id} not found")
        return user

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email (returns None if not found)."""
        return await self._repository.get_by_email(self._db, email)

    async def create_user(self, data: UserCreate) -> User:
        """Create a new user.

        Raises:
            AlreadyExistsError: If email already exists.
        """
        existing = await self._repository.get_by_email(self._db, data.email)
        if existing:
            raise AlreadyExistsError(f"User with email {data.email} already exists")

        user = await self._repository.create(self._db, obj_in=data)
        logger.info(f"Created user: {user.id}")
        return user

    async def update_user(self, user_id: str, data: UserUpdate) -> User:
        """Update an existing user.

        Raises:
            NotFoundError: If user doesn't exist.
            AlreadyExistsError: If new email already in use.
        """
        user = await self.get_user(user_id)

        # Check email uniqueness if changing email
        if data.email and data.email != user.email:
            existing = await self._repository.get_by_email(self._db, data.email)
            if existing:
                raise AlreadyExistsError(f"Email {data.email} already in use")

        return await self._repository.update(self._db, db_obj=user, obj_in=data)

    async def delete_user(self, user_id: str) -> User:
        """Delete a user.

        Raises:
            NotFoundError: If user doesn't exist.
        """
        user = await self._repository.delete(self._db, id=user_id)
        if not user:
            raise NotFoundError(f"User {user_id} not found")
        logger.info(f"Deleted user: {user_id}")
        return user
```

---

## Step 5: Create API Route

Location: `app/api/routes/`

```python
# app/api/routes/users.py
"""User API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new user."""
    service = UserService(db)
    user = await service.create_user(data)
    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Get user by ID."""
    service = UserService(db)
    user = await service.get_user(str(user_id))
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    """Update a user."""
    service = UserService(db)
    user = await service.update_user(str(user_id), data)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Delete a user."""
    service = UserService(db)
    await service.delete_user(str(user_id))
```

Register router in `app/api/routes/__init__.py`:
```python
from app.api.routes.users import router as users_router

api_router.include_router(users_router)
```

---

## Step 6: Create Migration

```bash
# Generate migration from model changes
uv run alembic revision --autogenerate -m "Add users table"

# Apply migration
uv run alembic upgrade head
```

---

## Database Session Patterns

### Pattern 1: FastAPI Dependency Injection (routes)

```python
from fastapi import Depends
from app.db.session import get_db_session

@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db_session)):
    # Session auto-commits on success, rollbacks on error
    ...
```

### Pattern 2: Context Manager (background tasks, WebSockets)

```python
from app.db.session import get_db_context

async def background_task():
    async with get_db_context() as db:
        # Session auto-commits on success, rollbacks on error
        service = UserService(db)
        await service.create_user(...)
```

### Pattern 3: Read-Only Session (analytics, user-generated SQL)

```python
from app.db.session import get_analytics_db_context

async def run_analytics():
    async with get_analytics_db_context() as db:
        # READ ONLY transaction — always rollbacks
        # Protects against SQL injection writes
        repo = AnalyticsRepository()
        rows, cols = await repo.execute_query(db, "SELECT ...")
```

---

## Testing

### Unit Testing Repositories (mocked session)

```python
# tests/test_repositories.py
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.repositories.user import UserRepository


class TestUserRepository:
    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def repository(self):
        return UserRepository()

    @pytest.mark.anyio
    async def test_get_by_email_found(self, repository, mock_session):
        mock_user = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_email(mock_session, "test@example.com")

        assert result == mock_user

    @pytest.mark.anyio
    async def test_get_by_email_not_found(self, repository, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_email(mock_session, "missing@example.com")

        assert result is None
```

### Integration Testing Services (real DB)

```python
# tests/integration/test_user_service.py
import pytest
from app.db.session import get_db_context
from app.services.user import UserService
from app.schemas.user import UserCreate
from app.core.exceptions import AlreadyExistsError


@pytest.mark.anyio
async def test_create_user_duplicate_email():
    async with get_db_context() as db:
        service = UserService(db)

        # First create succeeds
        await service.create_user(UserCreate(email="test@x.com", name="Test"))

        # Duplicate fails
        with pytest.raises(AlreadyExistsError):
            await service.create_user(UserCreate(email="test@x.com", name="Test2"))
```

---

## Common Pitfalls

### ❌ Blocking code in async context

```python
# BAD: sync database driver
import psycopg2
conn = psycopg2.connect(...)  # Blocks event loop!

# GOOD: async driver (already configured)
from app.db.session import get_db_context
async with get_db_context() as db:
    await db.execute(...)
```

### ❌ Business logic in routes

```python
# BAD: Route does too much
@router.post("/users")
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db_session)):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Email exists")
    user = User(**data.model_dump())
    db.add(user)
    await db.flush()
    return user

# GOOD: Delegate to service
@router.post("/users")
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db_session)):
    service = UserService(db)
    return await service.create_user(data)
```

### ❌ Committing in repository

```python
# BAD: Repository commits
async def create(self, db: AsyncSession, obj_in: CreateSchema) -> Model:
    db_obj = self.model(**obj_in.model_dump())
    db.add(db_obj)
    await db.commit()  # Don't do this!
    return db_obj

# GOOD: Repository flushes
async def create(self, db: AsyncSession, obj_in: CreateSchema) -> Model:
    db_obj = self.model(**obj_in.model_dump())
    db.add(db_obj)
    await db.flush()  # Let caller manage transaction
    await db.refresh(db_obj)
    return db_obj
```

### ❌ Storing session in repository `__init__`

```python
# BAD: Session tied to repository instance
class UserRepository:
    def __init__(self, db: AsyncSession):
        self._db = db  # Don't do this

# GOOD: Session passed to methods
class UserRepository:
    async def get(self, db: AsyncSession, id: Any) -> User | None:
        return await db.get(User, id)
```

### ❌ Raising HTTPException in services

```python
# BAD: Service coupled to HTTP layer
from fastapi import HTTPException

class UserService:
    async def get_user(self, user_id: str):
        user = await self._repository.get(self._db, user_id)
        if not user:
            raise HTTPException(404, "Not found")  # Don't do this!

# GOOD: Domain exception (caught by middleware)
from app.core.exceptions import NotFoundError

class UserService:
    async def get_user(self, user_id: str):
        user = await self._repository.get(self._db, user_id)
        if not user:
            raise NotFoundError(f"User {user_id} not found")
```

---

## Domain Exceptions

Use these from `app.core.exceptions`:

| Exception | HTTP Code | When to Use |
|-----------|-----------|-------------|
| `NotFoundError` | 404 | Resource doesn't exist |
| `AlreadyExistsError` | 409 | Duplicate key/unique constraint |
| `ValidationError` | 422 | Business rule validation failed |
| `AuthenticationError` | 401 | Invalid credentials |
| `AuthorizationError` | 403 | Insufficient permissions |
| `BadRequestError` | 400 | Malformed request |
| `ExternalServiceError` | 503 | Third-party API failure |
| `DatabaseError` | 500 | Database-level error |

---

## Checklist: Adding a New Entity

- [ ] Create SQLAlchemy model in `app/db/models/`
- [ ] Export model in `app/db/models/__init__.py`
- [ ] Create Pydantic schemas (Create, Update, Response) in `app/schemas/`
- [ ] Export schemas in `app/schemas/__init__.py`
- [ ] Create repository in `app/repositories/`
- [ ] Export repository in `app/repositories/__init__.py`
- [ ] Create service in `app/services/`
- [ ] Create API routes in `app/api/routes/`
- [ ] Register router in `app/api/routes/__init__.py`
- [ ] Generate Alembic migration: `uv run alembic revision --autogenerate -m "..."`
- [ ] Apply migration: `uv run alembic upgrade head`
- [ ] Add unit tests for repository
- [ ] Add integration tests for service
