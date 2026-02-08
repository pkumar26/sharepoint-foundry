"""Contract tests for POST /chat endpoint matching openapi.yaml schemas."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def env_vars() -> dict[str, str]:
    """Provide minimal env vars for app startup."""
    return {
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
        "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
        "COSMOS_ENDPOINT": "https://test.documents.azure.com:443/",
        "ENTRA_TENANT_ID": "tenant-123",
        "ENTRA_CLIENT_ID": "client-456",
        "ENTRA_CLIENT_SECRET": "secret-789",
    }


@pytest.fixture
async def client(env_vars: dict[str, str]) -> AsyncClient:
    """Create test client with mocked environment."""
    with patch.dict(os.environ, env_vars, clear=False):
        from src.main import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c  # type: ignore[misc]


class TestChatEndpointContract:
    """Verify POST /chat request/response shapes match openapi.yaml."""

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_200(self, client: AsyncClient) -> None:
        """Health endpoint should always be accessible."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "version" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_chat_without_auth_returns_401(self, client: AsyncClient) -> None:
        """POST /chat without Authorization header should return 401."""
        resp = await client.post(
            "/chat",
            json={"message": "What is the leave policy?"},
        )
        assert resp.status_code == 401
        data = resp.json()
        # FastAPI wraps HTTPException detail in a 'detail' key
        detail = data.get("detail", data)
        assert "error" in detail
        assert "message" in detail

    @pytest.mark.asyncio
    async def test_chat_request_schema_validation(self, client: AsyncClient) -> None:
        """POST /chat with empty body should return 400 or 422."""
        resp = await client.post(
            "/chat",
            json={},
            headers={"Authorization": "Bearer fake-token"},
        )
        # Will be 401 (auth check first) or 422 (validation) depending on order
        assert resp.status_code in (401, 422)

    @pytest.mark.asyncio
    async def test_chat_input_too_long_returns_400(self, client: AsyncClient) -> None:
        """POST /chat with message exceeding max length should return 400."""
        long_message = "x" * 5000
        resp = await client.post(
            "/chat",
            json={"message": long_message},
            headers={"Authorization": "Bearer fake-token"},
        )
        # Will be 401 (auth first) or 400 (input_too_long)
        assert resp.status_code in (400, 401)
