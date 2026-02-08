"""Unit tests for User model JWT parsing."""

from __future__ import annotations

import pytest

from src.models.user import User


class TestUser:
    """Tests for the User Pydantic model."""

    def test_create_user(self) -> None:
        user = User(
            user_id="00000000-0000-0000-0000-000000000001",
            display_name="Jane Doe",
            email="jane@contoso.com",
            tenant_id="00000000-0000-0000-0000-000000000099",
        )
        assert user.user_id == "00000000-0000-0000-0000-000000000001"
        assert user.display_name == "Jane Doe"
        assert user.email == "jane@contoso.com"
        assert user.tenant_id == "00000000-0000-0000-0000-000000000099"

    def test_from_jwt_claims_full(self) -> None:
        claims = {
            "oid": "abc-123",
            "name": "John Smith",
            "preferred_username": "john@contoso.com",
            "tid": "tenant-xyz",
        }
        user = User.from_jwt_claims(claims)
        assert user.user_id == "abc-123"
        assert user.display_name == "John Smith"
        assert user.email == "john@contoso.com"
        assert user.tenant_id == "tenant-xyz"

    def test_from_jwt_claims_missing_optional(self) -> None:
        claims = {
            "oid": "abc-123",
            "tid": "tenant-xyz",
        }
        user = User.from_jwt_claims(claims)
        assert user.user_id == "abc-123"
        assert user.display_name == "Unknown"
        assert user.email == ""
        assert user.tenant_id == "tenant-xyz"

    def test_from_jwt_claims_missing_required_raises(self) -> None:
        with pytest.raises(KeyError):
            User.from_jwt_claims({"name": "No OID"})
