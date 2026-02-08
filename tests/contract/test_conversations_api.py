"""Contract tests for GET /conversations and GET /conversations/{id} endpoints."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def env_vars() -> dict[str, str]:
    return {
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
        "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
        "COSMOS_ENDPOINT": "https://test.documents.azure.com:443/",
        "ENTRA_TENANT_ID": "tenant-123",
        "ENTRA_CLIENT_ID": "client-456",
        "ENTRA_CLIENT_SECRET": "secret-789",
    }


class TestConversationsApiContract:
    """Verify conversations endpoint response shapes match openapi.yaml."""

    @pytest.mark.asyncio
    async def test_list_conversations_requires_auth(self, env_vars: dict[str, str]) -> None:
        """GET /conversations without auth should return 401."""
        with patch.dict(os.environ, env_vars, clear=False):
            from src.main import create_app

            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/conversations")
                assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_conversation_requires_auth(self, env_vars: dict[str, str]) -> None:
        """GET /conversations/{id} without auth should return 401."""
        with patch.dict(os.environ, env_vars, clear=False):
            from src.main import create_app

            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/conversations/some-uuid")
                assert resp.status_code == 401
