"""API dependencies.

Dependency injection factories for services, repositories, and authentication.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.services.agent import AgentService

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_agent_service() -> AgentService:
    """Create AgentService instance."""
    return AgentService()


AgentSvc = Annotated[AgentService, Depends(get_agent_service)]
