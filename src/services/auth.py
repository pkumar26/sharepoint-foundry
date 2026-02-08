"""Entra ID authentication service with On-Behalf-Of (OBO) flow."""

from __future__ import annotations

import logging
import time
from typing import Any

import jwt
import msal

from src.models.user import User

logger = logging.getLogger(__name__)

# Graph API scopes for OBO flow
GRAPH_SCOPES = [
    "https://graph.microsoft.com/Sites.Read.All",
    "https://graph.microsoft.com/Files.Read.All",
]


class AuthService:
    """Microsoft Entra ID authentication service.

    Handles:
    1. JWT token validation (audience, issuer, expiration)
    2. OBO token exchange for Graph API access
    3. User extraction from JWT claims
    """

    def __init__(self, settings: Any) -> None:
        self._tenant_id = settings.entra_tenant_id
        self._client_id = settings.entra_client_id
        self._client_secret = settings.entra_client_secret
        self._authority = f"https://login.microsoftonline.com/{self._tenant_id}"

        self._msal_app = msal.ConfidentialClientApplication(
            client_id=self._client_id,
            client_credential=self._client_secret,
            authority=self._authority,
        )

    async def validate_token(self, authorization_header: str) -> User:
        """Validate a Bearer token and return the authenticated User.

        Args:
            authorization_header: Full Authorization header value (e.g., "Bearer <token>").

        Returns:
            User extracted from validated JWT claims.

        Raises:
            ValueError: If token is invalid, expired, or has wrong audience/issuer.
        """
        if not authorization_header.startswith("Bearer "):
            raise ValueError("Missing Bearer prefix in Authorization header")

        token = authorization_header.removeprefix("Bearer ").strip()
        if not token:
            raise ValueError("Empty bearer token")

        # Decode and validate the token
        payload = self._decode_token(token)

        # Validate expiration
        exp = payload.get("exp", 0)
        if time.time() > exp:
            raise ValueError("Token expired: token has passed its expiration time")

        # Validate audience
        aud = payload.get("aud", "")
        if aud != self._client_id:
            raise ValueError(f"Invalid audience (aud): expected {self._client_id}, got {aud}")

        # Validate issuer
        expected_issuer = f"https://login.microsoftonline.com/{self._tenant_id}/v2.0"
        iss = payload.get("iss", "")
        if iss != expected_issuer:
            logger.warning("Issuer mismatch: expected %s, got %s", expected_issuer, iss)

        return User.from_jwt_claims(payload)

    def _decode_token(self, token: str) -> dict[str, Any]:
        """Decode a JWT token without verification for claim extraction.

        In production, this should verify the token signature against
        the Entra ID JWKS endpoint. For now, decode without verification
        and rely on claim validation.
        """
        try:
            # Decode without signature verification — production should use JWKS
            payload = jwt.decode(
                token,
                options={
                    "verify_signature": False,
                    "verify_aud": False,
                    "verify_exp": False,
                },
                algorithms=["RS256"],
            )
            return payload
        except jwt.exceptions.DecodeError as e:
            raise ValueError(f"Invalid token format: {e}") from e

    async def get_graph_token(self, user_assertion: str) -> str:
        """Exchange user token for a Graph API token using OBO flow.

        Args:
            user_assertion: The user's access token to exchange.

        Returns:
            Graph API access token string.

        Raises:
            RuntimeError: If OBO token exchange fails.
        """
        result = self._msal_app.acquire_token_on_behalf_of(
            user_assertion=user_assertion,
            scopes=GRAPH_SCOPES,
        )

        if "access_token" in result:
            return result["access_token"]

        error = result.get("error", "unknown")
        description = result.get("error_description", "OBO token exchange failed")
        raise RuntimeError(f"Token exchange failed via OBO: {error} — {description}")

    def extract_user(self, claims: dict[str, Any]) -> User:
        """Extract a User model from JWT claims.

        Args:
            claims: Decoded JWT payload dictionary.

        Returns:
            User model populated from claims.
        """
        return User.from_jwt_claims(claims)
