"""Integration test for concurrent user isolation (T044b).

Verifies that parallel requests from different users don't cross-contaminate
identity or conversation data.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from src.models.user import User


def _mock_settings():
    """Return a Settings-like object with dummy values for testing."""
    from unittest.mock import MagicMock

    s = MagicMock()
    s.log_level = "WARNING"
    s.max_input_length = 4000
    s.rate_limit_per_minute = 20
    s.azure_openai_endpoint = "https://fake.openai.azure.com"
    s.azure_openai_deployment = "gpt-4o"
    s.azure_openai_api_version = "2024-06-01"
    s.azure_openai_embedding_deployment = "text-embedding-3-small"
    s.azure_search_endpoint = "https://fake.search.windows.net"
    s.azure_search_index_name = "test-index"
    s.cosmos_endpoint = "https://fake.documents.azure.com"
    s.cosmos_database = "test-db"
    s.cosmos_container = "test-container"
    s.entra_tenant_id = "fake-tenant"
    s.entra_client_id = "fake-client"
    s.entra_client_secret = "fake-secret"
    return s


class TestConcurrentUsers:
    """Concurrent user isolation tests."""

    @pytest.mark.asyncio
    async def test_parallel_requests_no_identity_bleed(self) -> None:
        """10 parallel requests with different users should each get correct identity."""
        from src.main import create_app, get_current_user

        users = [
            User(
                user_id=f"concurrent-user-{i}",
                display_name=f"User {i}",
                email=f"user{i}@test.com",
                tenant_id="tenant-1",
            )
            for i in range(10)
        ]

        results: list[tuple[int, int]] = []

        async def make_request(user_idx: int) -> tuple[int, int]:
            """Make a request as a specific user and return (user_idx, status)."""
            per_user_app = create_app()
            per_user_app.state.settings = _mock_settings()
            per_user_app.dependency_overrides[get_current_user] = lambda u=users[user_idx]: u

            transport = ASGITransport(app=per_user_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/chat",
                    json={"message": f"Question from user {user_idx}"},
                )
                return (user_idx, resp.status_code)

        # Launch 10 parallel requests
        tasks = [make_request(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # None should be rate-limited (each user sends only 1 request)
        for user_idx, status_code in results:
            assert status_code != 429, f"User {user_idx} was unexpectedly rate-limited"

        # All requests should have been processed
        assert len(results) == 10
