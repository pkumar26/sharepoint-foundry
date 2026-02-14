"""Azure AI Search service for hybrid document retrieval."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from src.models.document import SearchResult

logger = logging.getLogger(__name__)


@runtime_checkable
class SearchBackend(Protocol):
    """Protocol defining the contract for any search backend.

    All search implementations (indexer, foundryiq, indexed_sharepoint)
    must satisfy this interface so they can be used interchangeably.
    """

    async def search_documents(
        self,
        query: str,
        user_id: str,
        group_ids: list[str],
        top: int = 5,
    ) -> list[SearchResult]: ...


class IndexerSearchService:
    """Search SharePoint documents using Azure AI Search hybrid queries.

    Combines vector (HNSW), keyword (BM25), and semantic ranking.
    Applies ACL-based security trimming using user and group IDs.
    This is the Approach 1 (direct index query) backend.
    """

    def __init__(
        self,
        endpoint: str,
        index_name: str,
        credential: Any,
        embedding_client: Any | None = None,
    ) -> None:
        self._client = SearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=credential,
        )
        self._embedding_client = embedding_client

    async def search_documents(
        self,
        query: str,
        user_id: str,
        group_ids: list[str],
        top: int = 5,
    ) -> list[SearchResult]:
        """Search for documents matching the query with security trimming.

        Args:
            query: Natural language search query.
            user_id: Authenticated user's Entra object ID.
            group_ids: User's Entra group IDs for ACL filtering.
            top: Maximum number of results to return.

        Returns:
            List of SearchResult objects sorted by relevance.
        """
        # Build ACL security trimming filter
        acl_filter = self._build_security_filter(user_id, group_ids)

        # Build search kwargs
        search_kwargs: dict[str, Any] = {
            "search_text": query,
            "filter": acl_filter,
            "top": top,
            "query_type": "semantic",
            "semantic_configuration_name": "default",
        }

        # Add vector query if embedding client is available
        if self._embedding_client is not None:
            try:
                embedding = await self._get_embedding(query)
                vector_query = VectorizedQuery(
                    vector=embedding,
                    k_nearest_neighbors=top,
                    fields="content_vector",
                )
                search_kwargs["vector_queries"] = [vector_query]
            except Exception:
                logger.warning("Failed to generate embedding, falling back to keyword search")

        logger.info(
            "Searching documents",
            extra={"user_id": user_id, "query_length": len(query)},
        )

        # Execute search
        results = self._client.search(**search_kwargs)

        # Map to SearchResult models
        search_results: list[SearchResult] = []
        for result in results:
            try:
                last_modified_raw = result.get("last_modified")
                if isinstance(last_modified_raw, str):
                    last_modified = datetime.fromisoformat(last_modified_raw.replace("Z", "+00:00"))
                elif isinstance(last_modified_raw, datetime):
                    last_modified = last_modified_raw
                else:
                    last_modified = datetime.now(tz=UTC)

                search_results.append(
                    SearchResult(
                        chunk_id=result["id"],
                        document_title=result["title"],
                        content=result["content"],
                        source_url=result.get("source_url", ""),
                        file_type=result.get("file_type", "unknown"),
                        last_modified=last_modified,
                        relevance_score=result.get("@search.score", 0.0),
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed search result: %s", e)
                continue

        return search_results

    def _build_security_filter(self, user_id: str, group_ids: list[str]) -> str:
        """Build an OData filter for ACL-based security trimming.

        Args:
            user_id: User's Entra object ID.
            group_ids: User's Entra group IDs.

        Returns:
            OData filter string for security trimming.
        """
        parts: list[str] = [f"UserIds/any(u: u eq '{user_id}')"]
        for gid in group_ids:
            parts.append(f"GroupIds/any(g: g eq '{gid}')")
        return " or ".join(parts)

    async def _get_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for the given text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as list of floats.
        """
        response = await self._embedding_client.embeddings.create(
            input=text,
            model="text-embedding-ada-002",
        )
        return response.data[0].embedding


# Backward-compatible alias
SearchService = IndexerSearchService
