"""LLM client service.

Factory for creating LLM clients with consistent configuration.
"""

from langchain_openai import ChatOpenAI

from app.core.config import settings


def get_llm_client() -> ChatOpenAI:
    """Create OpenAI LLM client for analytics chatbot."""
    return ChatOpenAI(
        model=settings.AI_MODEL,
        temperature=0,
        api_key=settings.OPENAI_API_KEY,
    )
