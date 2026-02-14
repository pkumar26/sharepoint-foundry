"""Environment-based configuration loader using pydantic BaseSettings."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All Azure and application configuration is loaded from environment
    variables (or a .env file) and validated at startup.
    """

    # Azure OpenAI
    azure_openai_endpoint: str
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_api_version: str = "2024-06-01"
    azure_openai_api_key: str = ""  # Optional — uses DefaultAzureCredential when empty

    # Azure AI Search
    azure_search_endpoint: str
    azure_search_index_name: str = "sharepoint-docs-index"

    # Search approach: which backend to use for document retrieval
    #   indexer           – Direct Azure AI Search index query (Approach 1)
    #   foundryiq         – FoundryIQ remote SharePoint knowledge base (Approach 2)
    #   indexed_sharepoint – Indexed SharePoint knowledge base (Approach 3)
    search_approach: Literal["indexer", "foundryiq", "indexed_sharepoint"] = "indexer"

    # Knowledge Base settings (required for foundryiq / indexed_sharepoint)
    azure_search_api_key: str = ""
    azure_search_api_version: str = "2025-11-01-preview"
    knowledge_base_name: str = ""
    knowledge_source_name: str = ""

    # Azure Cosmos DB
    cosmos_endpoint: str
    cosmos_database: str = "sharepoint-agent"
    cosmos_container: str = "conversations"

    # Microsoft Entra ID (OBO flow)
    entra_tenant_id: str
    entra_client_id: str
    entra_client_secret: str = ""  # Optional — not needed when using managed identity

    # Application
    log_level: str = "INFO"
    max_input_length: int = 4000
    rate_limit_per_minute: int = 20

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    """Create and return a validated Settings instance."""
    return Settings()  # type: ignore[call-arg]
