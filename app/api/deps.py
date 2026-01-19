"""API dependencies.

Dependency injection factories for services, repositories, and authentication.
"""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from langchain_openai import ChatOpenAI
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_analytics_db_session, get_db_session
from app.services.llm import get_llm_client

if TYPE_CHECKING:
    from app.services.slack import SlackService

# ===== Database Sessions =====

DBSession = Annotated[AsyncSession, Depends(get_db_session)]
AnalyticsDBSession = Annotated[AsyncSession, Depends(get_analytics_db_session)]


# ===== External Clients =====


def get_slack_client() -> AsyncWebClient:
    """Create Slack async web client."""
    return AsyncWebClient(token=settings.SLACK_BOT_TOKEN)


SlackClient = Annotated[AsyncWebClient, Depends(get_slack_client)]
LLMClient = Annotated[ChatOpenAI, Depends(get_llm_client)]


# ===== Services =====


def get_slack_service(slack_client: SlackClient) -> "SlackService":
    """Create SlackService with injected dependencies."""
    from app.services.slack import SlackService

    return SlackService(
        slack_client=slack_client,
        signing_secret=settings.SLACK_SIGNING_SECRET,
    )


SlackServiceDep = Annotated["SlackService", Depends(get_slack_service)]
