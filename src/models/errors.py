"""Error response models matching the OpenAPI specification."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """Machine-readable error codes from the API contract."""

    INVALID_REQUEST = "invalid_request"
    INPUT_TOO_LONG = "input_too_long"
    UNAUTHORIZED = "unauthorized"
    TOKEN_EXPIRED = "token_expired"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    NOT_FOUND = "not_found"
    SERVICE_UNAVAILABLE = "service_unavailable"


class ErrorResponse(BaseModel):
    """Structured error response per openapi.yaml ErrorResponse schema."""

    error: ErrorCode = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
