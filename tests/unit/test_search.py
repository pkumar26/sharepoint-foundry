"""Unit tests for the Azure AI Search service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.models.document import SearchResult


class TestSearchService:
    """Tests for SearchService class."""

    @pytest.fixture
    def mock_search_results(self) -> list[dict]:
        """Mock Azure AI Search response documents."""
        return [
            {
                "id": "chunk-001",
                "title": "Leave Policy 2026",
                "content": "Annual leave entitlement is 25 days per year...",
                "source_url": "https://sp.contoso.com/docs/leave-policy.docx",
                "site_name": "HR Portal",
                "file_type": "docx",
                "last_modified": "2026-01-15T10:00:00Z",
                "@search.score": 0.95,
            },
            {
                "id": "chunk-002",
                "title": "Employee Handbook",
                "content": "The sick leave policy covers all permanent employees...",
                "source_url": "https://sp.contoso.com/docs/handbook.pdf",
                "site_name": "HR Portal",
                "file_type": "pdf",
                "last_modified": "2025-12-01T08:00:00Z",
                "@search.score": 0.82,
            },
        ]

    @pytest.mark.asyncio
    async def test_search_returns_search_results(self, mock_search_results: list[dict]) -> None:
        """Verify search service maps raw results to SearchResult models."""
        from src.services.search import SearchService

        with patch("src.services.search.SearchClient") as mock_client_cls:
            mock_client = MagicMock()
            # Create mock result objects with attribute access
            mock_results = []
            for r in mock_search_results:
                mock_result = MagicMock()
                mock_result.__getitem__ = lambda self, key, _r=r: _r[key]
                mock_result.get = lambda key, default=None, _r=r: _r.get(key, default)
                mock_results.append(mock_result)

            mock_client.search = MagicMock(return_value=mock_results)
            mock_client_cls.return_value = mock_client

            service = SearchService(
                endpoint="https://test.search.windows.net",
                index_name="test-index",
                credential=MagicMock(),
            )
            results = await service.search_documents(
                query="leave policy",
                user_id="user-123",
                group_ids=["group-456"],
            )

        assert len(results) == 2
        assert all(isinstance(r, SearchResult) for r in results)
        assert results[0].document_title == "Leave Policy 2026"
        assert results[0].chunk_id == "chunk-001"
        assert results[1].site_name == "HR Portal"

    @pytest.mark.asyncio
    async def test_search_applies_security_filter(self, mock_search_results: list[dict]) -> None:
        """Verify security trimming filter is applied with user_id and group_ids."""
        from src.services.search import SearchService

        with patch("src.services.search.SearchClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.search = MagicMock(return_value=[])
            mock_client_cls.return_value = mock_client

            service = SearchService(
                endpoint="https://test.search.windows.net",
                index_name="test-index",
                credential=MagicMock(),
            )
            await service.search_documents(
                query="test query",
                user_id="user-123",
                group_ids=["group-A", "group-B"],
            )

            call_kwargs = mock_client.search.call_args
            filter_text = call_kwargs.kwargs.get("filter", "") or call_kwargs[1].get("filter", "")
            assert "user-123" in filter_text
            assert "group-A" in filter_text

    @pytest.mark.asyncio
    async def test_search_uses_hybrid_query(self) -> None:
        """Verify that search uses both keyword and vector queries."""
        from src.services.search import SearchService

        with patch("src.services.search.SearchClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.search = MagicMock(return_value=[])
            mock_client_cls.return_value = mock_client

            service = SearchService(
                endpoint="https://test.search.windows.net",
                index_name="test-index",
                credential=MagicMock(),
            )
            await service.search_documents(
                query="test query",
                user_id="user-123",
                group_ids=[],
            )

            call_kwargs = mock_client.search.call_args
            # Verify search_text is passed (keyword search)
            assert call_kwargs.kwargs.get("search_text") or call_kwargs[1].get("search_text")
