"""Unit tests for Entra ID authentication service."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.models.user import User
from src.services.auth import AuthService


class TestAuthService:
    """Tests for AuthService class."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        settings = MagicMock()
        settings.entra_tenant_id = "tenant-123"
        settings.entra_client_id = "client-456"
        settings.entra_client_secret = "secret-789"
        return settings

    def _make_valid_token_payload(self) -> dict:
        """Create a valid JWT payload."""
        return {
            "oid": "user-abc-123",
            "name": "Jane Doe",
            "preferred_username": "jane@contoso.com",
            "tid": "tenant-123",
            "aud": "client-456",
            "iss": "https://login.microsoftonline.com/tenant-123/v2.0",
            "exp": int(time.time()) + 3600,
        }

    @pytest.fixture
    def auth_service(self, mock_settings: MagicMock) -> AuthService:
        with patch("src.services.auth.msal.ConfidentialClientApplication"):
            service = AuthService(mock_settings)
        return service

    @pytest.mark.asyncio
    async def test_validate_token_returns_user(self, auth_service: Any) -> None:
        """Valid token should return a User object."""
        payload = self._make_valid_token_payload()

        with patch.object(auth_service, "_decode_token", return_value=payload):
            user = await auth_service.validate_token("Bearer fake.jwt.token")

        assert isinstance(user, User)
        assert user.user_id == "user-abc-123"
        assert user.display_name == "Jane Doe"
        assert user.email == "jane@contoso.com"
        assert user.tenant_id == "tenant-123"

    @pytest.mark.asyncio
    async def test_validate_token_expired_raises(self, auth_service: Any) -> None:
        """Expired token should raise an error."""
        payload = self._make_valid_token_payload()
        payload["exp"] = int(time.time()) - 100  # expired

        with (
            patch.object(auth_service, "_decode_token", return_value=payload),
            pytest.raises(Exception, match="expired|token"),
        ):
            await auth_service.validate_token("Bearer expired.jwt.token")

    @pytest.mark.asyncio
    async def test_validate_token_wrong_audience_raises(self, auth_service: Any) -> None:
        """Token with wrong audience should raise an error."""
        payload = self._make_valid_token_payload()
        payload["aud"] = "wrong-audience"

        with (
            patch.object(auth_service, "_decode_token", return_value=payload),
            pytest.raises(Exception, match="audience|aud"),
        ):
            await auth_service.validate_token("Bearer wrong-aud.jwt.token")

    @pytest.mark.asyncio
    async def test_get_graph_token_obo_flow(self, auth_service: Any) -> None:
        """OBO flow should exchange user token for Graph token."""
        mock_result = {"access_token": "graph-token-xyz"}
        auth_service._msal_app.acquire_token_on_behalf_of.return_value = mock_result

        result = await auth_service.get_graph_token("user-assertion-token")
        assert result == "graph-token-xyz"

    @pytest.mark.asyncio
    async def test_get_graph_token_obo_failure_raises(self, auth_service: Any) -> None:
        """Failed OBO flow should raise an error."""
        mock_result = {
            "error": "invalid_grant",
            "error_description": "Token exchange failed",
        }
        auth_service._msal_app.acquire_token_on_behalf_of.return_value = mock_result

        with pytest.raises(Exception, match="Token exchange|OBO|failed"):
            await auth_service.get_graph_token("bad-user-assertion")

    def test_extract_user_from_claims(self, auth_service: Any) -> None:
        """Extract User from JWT claims."""
        claims = self._make_valid_token_payload()
        user = auth_service.extract_user(claims)

        assert user.user_id == "user-abc-123"
        assert user.display_name == "Jane Doe"
