"""Integration tests for rate limiting in the chat endpoint (T041)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.models.user import User


def _make_user(user_id: str = "user-rate-test") -> User:
    return User(
        user_id=user_id,
        display_name="Rate Tester",
        email=f"{user_id}@test.com",
        tenant_id="tenant-1",
    )


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


def _create_test_app():
    """Create a test app with mock settings."""
    from src.main import create_app

    app = create_app()
    app.state.settings = _mock_settings()
    return app


class TestRateLimiting:
    """Rate-limiting integration tests against the FastAPI app."""

    @pytest.mark.asyncio
    async def test_rate_limit_returns_429(self) -> None:
        """Exceeding rate limit returns 429 with rate_limit_exceeded error."""
        from src.main import get_current_user

        app = _create_test_app()
        app.dependency_overrides[get_current_user] = lambda: _make_user("user-rate-test")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Fire 21 requests (limit=20)
            responses = []
            for _ in range(21):
                resp = await client.post(
                    "/chat",
                    json={"message": "test question?"},
                )
                responses.append(resp)

            status_codes = [r.status_code for r in responses]
            assert 429 in status_codes, f"Expected at least one 429; got {set(status_codes)}"

            # Verify 429 body has correct error code
            rate_limited = [r for r in responses if r.status_code == 429]
            body = rate_limited[0].json()
            error_data = body.get("detail", body)
            assert error_data.get("error") == "rate_limit_exceeded"

    @pytest.mark.asyncio
    async def test_different_users_independent_limits(self) -> None:
        """Different users should have independent rate limits."""
        from src.main import get_current_user

        app = _create_test_app()

        call_count = 0
        user_pool = [_make_user(f"user-{i}") for i in range(2)]

        def rotating_user() -> User:
            nonlocal call_count
            user = user_pool[call_count % 2]
            call_count += 1
            return user

        app.dependency_overrides[get_current_user] = rotating_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Each user sends 20 requests (within limit)
            # Total 40 requests alternating between 2 users
            responses = []
            for _ in range(40):
                resp = await client.post(
                    "/chat",
                    json={"message": "test question?"},
                )
                responses.append(resp)

            # None should be rate-limited; both users are at exactly 20
            status_codes = [r.status_code for r in responses]
            assert 429 not in status_codes, (
                f"No user should be rate-limited; got {status_codes.count(429)} 429s"
            )
