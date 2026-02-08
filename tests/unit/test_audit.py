"""Unit tests for AuditEntry model and log_query function."""

from __future__ import annotations

import logging

import pytest

from src.services.audit import AuditEntry, log_query


class TestAuditEntry:
    """Tests for AuditEntry model."""

    def test_create_audit_entry_with_required_fields(self) -> None:
        entry = AuditEntry(
            user_id="user-123",
            conversation_id="conv-456",
            query="What is the leave policy?",
            response_summary="The company leave policy states...",
            latency_ms=1200,
            was_refused=False,
        )
        assert entry.user_id == "user-123"
        assert entry.conversation_id == "conv-456"
        assert entry.query == "What is the leave policy?"
        assert entry.latency_ms == 1200
        assert entry.was_refused is False
        assert entry.documents_accessed == []
        assert entry.id  # auto-generated UUID
        assert entry.timestamp  # auto-generated

    def test_create_audit_entry_with_documents(self) -> None:
        entry = AuditEntry(
            user_id="user-123",
            conversation_id="conv-456",
            query="Tell me about onboarding",
            documents_accessed=[
                "https://sp.example.com/docs/onboarding.docx",
                "https://sp.example.com/docs/handbook.pdf",
            ],
            response_summary="Onboarding involves...",
            latency_ms=2500,
            was_refused=False,
        )
        assert len(entry.documents_accessed) == 2

    def test_refused_audit_entry(self) -> None:
        entry = AuditEntry(
            user_id="user-123",
            conversation_id="conv-456",
            query="What is the weather today?",
            response_summary="I can only answer questions about SharePoint documents.",
            latency_ms=300,
            was_refused=True,
        )
        assert entry.was_refused is True


class TestLogQuery:
    """Tests for the log_query function."""

    @pytest.mark.asyncio
    async def test_log_query_writes_to_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        entry = AuditEntry(
            user_id="user-789",
            conversation_id="conv-012",
            query="What is the expense policy?",
            response_summary="The expense policy requires...",
            latency_ms=800,
            was_refused=False,
        )

        with caplog.at_level(logging.INFO, logger="src.services.audit"):
            await log_query(entry)

        assert "audit_entry" in caplog.text
