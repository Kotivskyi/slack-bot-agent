"""Async PostgreSQL database session."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session for FastAPI dependency injection.

    Use this with FastAPI Depends().
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session as context manager.

    Use this with 'async with' for manual session management (e.g., WebSockets).
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_analytics_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Get read-only database session for analytics queries.

    This session:
    - Uses READ ONLY transaction mode (enforced by PostgreSQL)
    - Always rolls back (no commits possible)
    - Is isolated from the main app session (separate transaction)

    Use this for executing user-generated analytics SQL queries to:
    - Prevent accidental writes from SQL injection
    - Isolate query failures from checkpoint persistence
    """
    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        try:
            yield session
        finally:
            await session.rollback()


async def get_analytics_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get read-only database session for FastAPI dependency injection.

    This session:
    - Uses READ ONLY transaction mode (enforced by PostgreSQL)
    - Always rolls back (no commits possible)
    - Is isolated from the main app session (separate transaction)

    Use with FastAPI Depends() for analytics query routes.
    """
    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        try:
            yield session
        finally:
            await session.rollback()


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
