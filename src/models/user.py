"""User model derived from Entra ID JWT claims."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class User(BaseModel):
    """Authenticated user populated from Entra ID token claims.

    Not persisted as a separate entity — derived on each request from
    the authentication token. Used to scope Cosmos DB queries and
    AI Search security trimming.
    """

    user_id: str = Field(..., description="Entra ID object ID (GUID)")
    display_name: str = Field(..., max_length=256, description="User display name")
    email: str = Field(..., description="User email address")
    tenant_id: str = Field(..., description="Entra ID tenant ID")

    @classmethod
    def from_jwt_claims(cls, claims: dict[str, Any]) -> User:
        """Construct a User from decoded JWT token claims.

        Expected claims:
            - oid: Entra object ID → user_id
            - name: Display name → display_name
            - preferred_username: Email → email
            - tid: Tenant ID → tenant_id
        """
        return cls(
            user_id=claims["oid"],
            display_name=claims.get("name", "Unknown"),
            email=claims.get("preferred_username", ""),
            tenant_id=claims["tid"],
        )
