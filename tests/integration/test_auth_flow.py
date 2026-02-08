"""Integration tests for the authentication flow."""

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


class TestAuthFlow:
    """Integration tests for Entra ID authentication."""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self, env_vars: dict[str, str]) -> None:
        """Request without Authorization header should return 401."""
        with patch.dict(os.environ, env_vars, clear=False):
            from src.main import create_app

            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/chat",
                    json={"message": "test question"},
                )
                assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_bearer_returns_401(self, env_vars: dict[str, str]) -> None:
        """Request with empty Bearer token should return 401."""
        with patch.dict(os.environ, env_vars, clear=False):
            from src.main import create_app

            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/chat",
                    json={"message": "test question"},
                    headers={"Authorization": "Bearer "},
                )
                assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_format_returns_401(self, env_vars: dict[str, str]) -> None:
        """Request with non-Bearer auth should return 401."""
        with patch.dict(os.environ, env_vars, clear=False):
            from src.main import create_app

            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/chat",
                    json={"message": "test question"},
                    headers={"Authorization": "Basic dXNlcjpwYXNz"},
                )
                assert resp.status_code == 401
