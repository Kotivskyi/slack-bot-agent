"""API router aggregation."""

from fastapi import APIRouter

from app.api.routes import health, slack

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(slack.router, prefix="/slack", tags=["slack"])
