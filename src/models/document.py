"""Document-related models for search results and source references."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SourceReference(BaseModel):
    """Citation linking an agent answer to a SharePoint document.

    Embedded within Message.source_references to provide provenance
    for grounded agent responses.
    """

    document_title: str = Field(..., max_length=500, description="Title of the source document")
    document_url: str = Field(..., description="SharePoint URL to the document")
    excerpt: str | None = Field(None, max_length=500, description="Relevant snippet from document")
    relevance_score: float | None = Field(
        None, ge=0.0, le=1.0, description="Search relevance score"
    )


class SearchResult(BaseModel):
    """Document chunk retrieved from Azure AI Search.

    Transient — used internally during query processing.
    Not stored in Cosmos DB.
    """

    chunk_id: str = Field(..., description="Azure AI Search document ID")
    document_title: str = Field(..., description="Original document title")
    content: str = Field(..., description="Text chunk content")
    source_url: str = Field(..., description="SharePoint URL")
    file_type: str = Field(..., description="File format (docx, pdf, etc.)")
    last_modified: datetime = Field(..., description="Document last-modified date")
    relevance_score: float = Field(..., description="Hybrid search score")
