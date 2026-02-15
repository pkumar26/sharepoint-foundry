"""Conversation persistence service using Azure Cosmos DB."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.models.conversation import TTL_90_DAYS, Conversation, Message

logger = logging.getLogger(__name__)


class ConversationService:
    """Manage conversation persistence in Azure Cosmos DB.

    Each conversation is a single document in the 'conversations' container,
    partitioned by user_id. TTL resets on every upsert (new message).
    """

    def __init__(
        self,
        client: Any,
        database: str,
        container: str,
    ) -> None:
        db = client.get_database_client(database)
        self._container = db.get_container_client(container)

    async def create_conversation(
        self,
        user_id: str,
        title: str,
    ) -> Conversation:
        """Create a new conversation.

        Args:
            user_id: Owner's Entra object ID.
            title: Conversation title (auto-generated from first message).

        Returns:
            The created Conversation with a new UUID.
        """
        conv = Conversation(
            user_id=user_id,
            title=title,
        )
        await self._container.upsert_item(conv.to_cosmos_dict())
        logger.info("Created conversation", extra={"conversation_id": conv.id, "user_id": user_id})
        return conv

    async def get_conversation(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Conversation | None:
        """Get a conversation by ID, scoped to the owning user.

        Args:
            conversation_id: Conversation UUID.
            user_id: Owner's Entra object ID (partition key).

        Returns:
            Conversation if found, None otherwise.
        """
        try:
            data = await self._container.read_item(
                item=conversation_id,
                partition_key=user_id,
            )
            return Conversation.from_cosmos_dict(data)
        except Exception:
            logger.warning(
                "Conversation not found",
                extra={"conversation_id": conversation_id, "user_id": user_id},
            )
            return None

    async def add_message(
        self,
        conversation_id: str,
        user_id: str,
        message: Message,
    ) -> Conversation:
        """Add a message to an existing conversation.

        Upserts the document, which resets the Cosmos DB TTL timer.

        Args:
            conversation_id: Target conversation UUID.
            user_id: Owner's Entra object ID.
            message: Message to append.

        Returns:
            Updated Conversation.

        Raises:
            ValueError: If conversation not found.
        """
        conv = await self.get_conversation(conversation_id, user_id)
        if conv is None:
            raise ValueError(f"Conversation {conversation_id} not found for user {user_id}")

        conv.messages.append(message)
        conv.last_active_at = datetime.now(tz=UTC)
        conv.ttl = TTL_90_DAYS  # Reset TTL

        await self._container.upsert_item(conv.to_cosmos_dict())
        logger.info(
            "Added message to conversation",
            extra={
                "conversation_id": conversation_id,
                "user_id": user_id,
                "message_role": message.role,
            },
        )
        return conv

    async def list_conversations(
        self,
        user_id: str,
        status: str = "active",
        limit: int = 20,
        offset: int = 0,
    ) -> list[Conversation]:
        """List conversations for a user, ordered by most recent first.

        Args:
            user_id: Owner's Entra object ID (partition key).
            status: Filter by status ('active' or 'archived').
            limit: Maximum results to return.
            offset: Number of results to skip.

        Returns:
            List of Conversation objects.
        """
        query = (
            "SELECT * FROM c WHERE c.user_id = @user_id AND c.status = @status "
            "ORDER BY c.last_active_at DESC OFFSET @offset LIMIT @limit"
        )
        parameters = [
            {"name": "@user_id", "value": user_id},
            {"name": "@status", "value": status},
            {"name": "@offset", "value": offset},
            {"name": "@limit", "value": limit},
        ]

        results: list[Conversation] = []
        async for item in self._container.query_items(
            query=query,
            parameters=parameters,
            partition_key=user_id,
        ):
            results.append(Conversation.from_cosmos_dict(item))

        return results

    async def update_title(
        self,
        conversation_id: str,
        user_id: str,
        title: str,
    ) -> None:
        """Update the title of a conversation.

        Args:
            conversation_id: Target conversation UUID.
            user_id: Owner's Entra object ID.
            title: New title string (max 200 chars).
        """
        conv = await self.get_conversation(conversation_id, user_id)
        if conv is None:
            logger.warning(
                "Cannot update title — conversation not found",
                extra={"conversation_id": conversation_id},
            )
            return

        conv.title = title[:200]
        await self._container.upsert_item(conv.to_cosmos_dict())
        logger.info(
            "Updated conversation title",
            extra={"conversation_id": conversation_id, "title": title[:200]},
        )
