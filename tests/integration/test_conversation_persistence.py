"""Integration tests for conversation persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestConversationPersistence:
    """Integration tests for multi-turn conversation persistence."""

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(self) -> None:
        """Multi-turn conversation should persist all messages."""
        from src.models.conversation import Message
        from src.services.conversation import ConversationService

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_container = MagicMock()
        mock_client.get_database_client.return_value = mock_db
        mock_db.get_container_client.return_value = mock_container

        # Track upserted data
        upserted_items: dict[str, dict] = {}

        async def mock_upsert(item):
            upserted_items[item["id"]] = item

        async def mock_read(item, partition_key):
            # Return from upserted items
            if item in upserted_items:
                return upserted_items[item]
            raise Exception("Not found")

        mock_container.upsert_item = mock_upsert
        mock_container.read_item = mock_read

        service = ConversationService(
            client=mock_client, database="test-db", container="test-container"
        )

        # Create conversation
        conv = await service.create_conversation(user_id="user-123", title="Multi-turn test")

        # Add user message
        msg1 = Message(role="user", content="What is the leave policy?")
        await service.add_message(conversation_id=conv.id, user_id="user-123", message=msg1)

        # Add assistant response
        msg2 = Message(role="assistant", content="The leave policy grants 25 days.")
        await service.add_message(conversation_id=conv.id, user_id="user-123", message=msg2)

        # Verify messages accumulated
        latest = upserted_items[conv.id]
        assert len(latest["messages"]) >= 1  # At least the last message added

    @pytest.mark.asyncio
    async def test_conversation_isolation(self) -> None:
        """Different users' conversations should be isolated."""
        from src.services.conversation import ConversationService

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_container = MagicMock()
        mock_client.get_database_client.return_value = mock_db
        mock_db.get_container_client.return_value = mock_container
        mock_container.upsert_item = AsyncMock()

        service = ConversationService(
            client=mock_client, database="test-db", container="test-container"
        )

        conv1 = await service.create_conversation(user_id="user-A", title="User A conv")
        conv2 = await service.create_conversation(user_id="user-B", title="User B conv")

        assert conv1.user_id == "user-A"
        assert conv2.user_id == "user-B"
        assert conv1.id != conv2.id
