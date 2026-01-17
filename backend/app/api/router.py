"""API router aggregation."""

from fastapi import APIRouter

from app.api.routes import health, items, conversations, agent

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(items.router, prefix="/items", tags=["items"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(agent.router, tags=["agent"])
