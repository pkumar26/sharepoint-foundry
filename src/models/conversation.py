"""Conversation and Message models for Cosmos DB persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from src.models.document import SourceReference

# 90 days in seconds
TTL_90_DAYS = 7_776_000


class Message(BaseModel):
    """A single turn in a conversation.

    Embedded within Conversation.messages — not a separate Cosmos DB document.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text content")
    source_references: list[SourceReference] = Field(
        default_factory=list, description="Citations (assistant only)"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="UTC timestamp",
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for Cosmos DB storage."""
        data = self.model_dump()
        data["timestamp"] = self.timestamp.isoformat()
        data["source_references"] = [sr.model_dump() for sr in self.source_references]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        """Deserialize from Cosmos DB document."""
        return cls(**data)


class Conversation(BaseModel):
    """A threaded exchange between one user and the agent.

    Persisted as a single document in Azure Cosmos DB with
    partition key = user_id.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(..., description="Owner's Entra object ID (partition key)")
    title: str = Field(..., max_length=200, description="Auto-generated title")
    messages: list[Message] = Field(default_factory=list)
    status: str = Field(default="active", description="'active' or 'archived'")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
    )
    last_active_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
    )
    ttl: int = Field(default=TTL_90_DAYS, description="Time-to-live in seconds")

    def to_cosmos_dict(self) -> dict[str, Any]:
        """Serialize for Cosmos DB upsert."""
        data: dict[str, Any] = {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "last_active_at": self.last_active_at.isoformat(),
            "ttl": self.ttl,
        }
        return data

    @classmethod
    def from_cosmos_dict(cls, data: dict[str, Any]) -> Conversation:
        """Deserialize from Cosmos DB document."""
        messages = [Message.from_dict(m) for m in data.get("messages", [])]
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            title=data.get("title", ""),
            messages=messages,
            status=data.get("status", "active"),
            created_at=data.get("created_at", datetime.now(tz=UTC)),
            last_active_at=data.get("last_active_at", datetime.now(tz=UTC)),
            ttl=data.get("ttl", TTL_90_DAYS),
        )
