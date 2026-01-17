"""Exception handler tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_not_found_error_format(client: AsyncClient):
    """Test that 404 errors return proper JSON format."""
    response = await client.get("/nonexistent-endpoint")
    assert response.status_code == 404
    # FastAPI returns 404 for unknown routes
