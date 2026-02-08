"""Unit tests for conversation persistence service."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestConversationService:
    """Tests for ConversationService class."""

    @pytest.fixture
    def mock_cosmos_client(self) -> MagicMock:
        """Create a mock Cosmos DB client."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_container = MagicMock()
        mock_client.get_database_client.return_value = mock_db
        mock_db.get_container_client.return_value = mock_container
        return mock_client

    @pytest.fixture
    def mock_container(self, mock_cosmos_client: MagicMock) -> MagicMock:
        return mock_cosmos_client.get_database_client().get_container_client()

    @pytest.mark.asyncio
    async def test_create_conversation(
        self, mock_cosmos_client: MagicMock, mock_container: MagicMock
    ) -> None:
        """Creating a conversation should write to Cosmos DB."""
        from src.services.conversation import ConversationService

        mock_container.upsert_item = AsyncMock()

        service = ConversationService(
            client=mock_cosmos_client, database="test-db", container="test-container"
        )
        conv = await service.create_conversation(user_id="user-123", title="Test Conversation")

        assert conv.user_id == "user-123"
        assert conv.title == "Test Conversation"
        assert conv.status == "active"
        assert len(conv.messages) == 0
        mock_container.upsert_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_conversation(
        self, mock_cosmos_client: MagicMock, mock_container: MagicMock
    ) -> None:
        """Getting a conversation should read from Cosmos DB."""
        from src.services.conversation import ConversationService

        conv_data = {
            "id": "conv-456",
            "user_id": "user-123",
            "title": "Test",
            "messages": [],
            "status": "active",
            "created_at": datetime.now(tz=UTC).isoformat(),
            "last_active_at": datetime.now(tz=UTC).isoformat(),
            "ttl": 7776000,
        }
        mock_container.read_item = AsyncMock(return_value=conv_data)

        service = ConversationService(
            client=mock_cosmos_client, database="test-db", container="test-container"
        )
        conv = await service.get_conversation(conversation_id="conv-456", user_id="user-123")

        assert conv is not None
        assert conv.id == "conv-456"
        assert conv.user_id == "user-123"
        mock_container.read_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_message_resets_ttl(
        self, mock_cosmos_client: MagicMock, mock_container: MagicMock
    ) -> None:
        """Adding a message should upsert (resetting TTL)."""
        from src.models.conversation import Message
        from src.services.conversation import ConversationService

        conv_data = {
            "id": "conv-456",
            "user_id": "user-123",
            "title": "Test",
            "messages": [],
            "status": "active",
            "created_at": datetime.now(tz=UTC).isoformat(),
            "last_active_at": datetime.now(tz=UTC).isoformat(),
            "ttl": 7776000,
        }
        mock_container.read_item = AsyncMock(return_value=conv_data)
        mock_container.upsert_item = AsyncMock()

        service = ConversationService(
            client=mock_cosmos_client, database="test-db", container="test-container"
        )

        message = Message(
            role="user",
            content="What is the leave policy?",
        )
        await service.add_message(conversation_id="conv-456", user_id="user-123", message=message)

        # Verify upsert was called (which resets TTL)
        mock_container.upsert_item.assert_called_once()
        upserted_data = mock_container.upsert_item.call_args[0][0]
        assert len(upserted_data["messages"]) == 1

    @pytest.mark.asyncio
    async def test_list_conversations_scoped_by_user(
        self, mock_cosmos_client: MagicMock, mock_container: MagicMock
    ) -> None:
        """Listing conversations should be partition-scoped by user_id."""
        from src.services.conversation import ConversationService

        mock_items = [
            {
                "id": "conv-1",
                "user_id": "user-123",
                "title": "Conv 1",
                "messages": [
                    {
                        "id": "m1",
                        "role": "user",
                        "content": "Hi",
                        "timestamp": datetime.now(tz=UTC).isoformat(),
                    }
                ],
                "status": "active",
                "created_at": datetime.now(tz=UTC).isoformat(),
                "last_active_at": datetime.now(tz=UTC).isoformat(),
                "ttl": 7776000,
            },
        ]

        # Mock query_items as an async iterator
        async def mock_query(*args, **kwargs):
            for item in mock_items:
                yield item

        mock_container.query_items = mock_query

        service = ConversationService(
            client=mock_cosmos_client, database="test-db", container="test-container"
        )
        convs = await service.list_conversations(user_id="user-123")

        assert len(convs) == 1
        assert convs[0].user_id == "user-123"
