"""Knowledge Base search service for FoundryIQ and Indexed SharePoint approaches.

Implements the SearchBackend protocol by calling the Azure AI Search
Knowledge Base retrieve API (Approaches 2 and 3).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

import httpx

from src.models.document import SearchResult

logger = logging.getLogger(__name__)

# Map our config values to the KB API `kind` field
_KIND_MAP: dict[str, str] = {
    "foundryiq": "remoteSharePoint",
    "indexed_sharepoint": "indexedSharePoint",
}


class KnowledgeBaseSearchService:
    """Search via the Azure AI Search Knowledge Base retrieve API.

    Supports both Approach 2 (FoundryIQ / remoteSharePoint) and
    Approach 3 (Indexed SharePoint / indexedSharePoint).

    The two approaches share the same API shape — only the `kind` field
    and authentication mechanism differ:
      - indexedSharePoint: uses admin API key
      - remoteSharePoint:  uses a delegated (OBO) user token
    """

    def __init__(
        self,
        *,
        endpoint: str,
        api_version: str,
        knowledge_base_name: str,
        knowledge_source_name: str,
        approach: Literal["foundryiq", "indexed_sharepoint"],
        api_key: str = "",
        token_provider: object | None = None,
    ) -> None:
        """Initialise the KB search service.

        Args:
            endpoint: Azure AI Search endpoint URL.
            api_version: API version string (e.g. '2025-11-01-preview').
            knowledge_base_name: Name of the knowledge base resource.
            knowledge_source_name: Name of the knowledge source.
            approach: Which KB approach to use.
            api_key: Admin API key (for indexed_sharepoint).
            token_provider: Async callable returning a bearer token (for foundryiq).
        """
        self._endpoint = endpoint.rstrip("/")
        self._api_version = api_version
        self._kb_name = knowledge_base_name
        self._ks_name = knowledge_source_name
        self._kind = _KIND_MAP[approach]
        self._api_key = api_key
        self._token_provider = token_provider

    async def search_documents(
        self,
        query: str,
        user_id: str,
        group_ids: list[str],
        top: int = 5,
    ) -> list[SearchResult]:
        """Retrieve documents from the knowledge base.

        Args:
            query: Natural language search query.
            user_id: Authenticated user's Entra object ID (used for audit logging).
            group_ids: User's Entra group IDs (not used directly — ACLs are
                       enforced server-side by the KB API).
            top: Maximum number of results.

        Returns:
            List of SearchResult objects.
        """
        url = (
            f"{self._endpoint}/knowledgebases('{self._kb_name}')/retrieve"
            f"?api-version={self._api_version}"
        )

        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": query}],
                }
            ],
            "knowledgeSourceParams": [
                {
                    "knowledgeSourceName": self._ks_name,
                    "kind": self._kind,
                    "includeReferences": True,
                    "includeReferenceSourceData": True,
                }
            ],
        }

        headers = await self._build_headers()

        logger.info(
            "KB retrieve request",
            extra={
                "user_id": user_id,
                "kb_name": self._kb_name,
                "kind": self._kind,
                "query_length": len(query),
            },
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=body, headers=headers)
            if response.status_code >= 400:
                logger.error(
                    "KB retrieve failed",
                    extra={
                        "status": response.status_code,
                        "body": response.text[:500],
                    },
                )
            response.raise_for_status()
            data = response.json()

        return self._map_results(data)

    async def _build_headers(self) -> dict[str, str]:
        """Build request headers based on the authentication method."""
        headers: dict[str, str] = {"Content-Type": "application/json"}

        if self._kind == "indexedSharePoint":
            # Approach 3: admin API key auth
            headers["api-key"] = self._api_key
        elif self._token_provider is not None:
            # Approach 2: delegated user token (OBO)
            token = await self._token_provider()  # type: ignore[operator]
            headers["Authorization"] = f"Bearer {token}"
        else:
            # Fallback: try API key
            if self._api_key:
                headers["api-key"] = self._api_key

        return headers

    def _map_results(self, data: dict) -> list[SearchResult]:
        """Map the KB retrieve API response to SearchResult models.

        The retrieve API returns:
        - ``response``: synthesised answer (we ignore this — the agent generates its own)
        - ``references``: list of source chunks with metadata
        - ``activity``: pipeline activity log
        """
        results: list[SearchResult] = []
        references = data.get("references", [])

        logger.info(
            "KB retrieve response",
            extra={
                "num_references": len(references),
                "has_response": bool(data.get("response")),
                "has_activity": bool(data.get("activity")),
            },
        )

        for item in references:
            try:
                # The KB retrieve API nests most fields inside "sourceData"
                source_data = item.get("sourceData", {})

                content = source_data.get("snippet", source_data.get("content", ""))
                doc_url = source_data.get("doc_url", source_data.get("webUrl", ""))

                # Derive title from doc_url (last path segment, cleaned up)
                raw_title = item.get("title", source_data.get("title", ""))
                if not raw_title and doc_url:
                    # e.g. "/drives/.../root:/Travel_Expense_Policy.pdf" → "Travel Expense Policy"
                    raw_title = doc_url.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("_", " ")
                title = raw_title or "Untitled"

                url = doc_url
                chunk_id = item.get("chunkId", item.get("id", source_data.get("uid", "")))
                score = item.get("rerankerScore", item.get("score", 0.0))
                file_type = source_data.get("fileType", "unknown")
                if file_type == "unknown" and doc_url:
                    # Derive from extension
                    ext = doc_url.rsplit(".", 1)[-1].lower() if "." in doc_url else "unknown"
                    file_type = ext

                # Parse last_modified if present
                last_modified_raw = item.get("lastModified")
                if isinstance(last_modified_raw, str):
                    last_modified = datetime.fromisoformat(
                        last_modified_raw.replace("Z", "+00:00")
                    )
                else:
                    last_modified = datetime.now(tz=UTC)

                results.append(
                    SearchResult(
                        chunk_id=str(chunk_id),
                        document_title=title,
                        content=content,
                        source_url=url,
                        file_type=file_type,
                        last_modified=last_modified,
                        relevance_score=float(score) if score else 0.0,
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed KB reference: %s", e)
                continue

        return results
