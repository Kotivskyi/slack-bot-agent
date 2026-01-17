"""API dependencies.

Dependency injection factories for services, repositories, and authentication.
"""
# ruff: noqa: I001, E402 - Imports structured for Jinja2 template conditionals

from typing import Annotated

from fastapi import Depends
from app.db.session import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession

DBSession = Annotated[AsyncSession, Depends(get_db_session)]
from app.services.item import ItemService
from app.services.conversation import ConversationService


def get_item_service(db: DBSession) -> ItemService:
    """Create ItemService instance with database session."""
    return ItemService(db)


ItemSvc = Annotated[ItemService, Depends(get_item_service)]


def get_conversation_service(db: DBSession) -> ConversationService:
    """Create ConversationService instance with database session."""
    return ConversationService(db)


ConversationSvc = Annotated[ConversationService, Depends(get_conversation_service)]
