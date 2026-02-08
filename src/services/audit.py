"""Audit trail service for compliance logging."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AuditEntry(BaseModel):
    """Audit trail record capturing each user interaction for compliance.

    Written to structured logs (JSON). One entry per user query.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(..., description="User's Entra object ID")
    conversation_id: str = Field(..., description="Conversation context")
    query: str = Field(..., description="User's question text")
    documents_accessed: list[str] = Field(
        default_factory=list, description="SharePoint URLs of documents searched"
    )
    response_summary: str = Field(..., description="First 500 chars of agent response")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    latency_ms: int = Field(..., description="End-to-end response time in ms")
    was_refused: bool = Field(..., description="Whether agent refused to answer")


async def log_query(entry: AuditEntry) -> None:
    """Write an audit entry to structured JSON logs.

    Args:
        entry: The audit entry to log.
    """
    logger.info(
        "audit_entry",
        extra={
            "user_id": entry.user_id,
            "conversation_id": entry.conversation_id,
            "query": entry.query,
            "documents_accessed": entry.documents_accessed,
            "response_summary": entry.response_summary[:500],
            "latency_ms": entry.latency_ms,
            "was_refused": entry.was_refused,
        },
    )
