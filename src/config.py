"""Environment-based configuration loader using pydantic BaseSettings."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All Azure and application configuration is loaded from environment
    variables (or a .env file) and validated at startup.
    """

    # Azure OpenAI
    azure_openai_endpoint: str
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-ada-002"
    azure_openai_api_version: str = "2024-06-01"

    # Azure AI Search
    azure_search_endpoint: str
    azure_search_index_name: str = "sharepoint-docs-index"

    # Azure Cosmos DB
    cosmos_endpoint: str
    cosmos_database: str = "sharepoint-agent"
    cosmos_container: str = "conversations"

    # Microsoft Entra ID (OBO flow)
    entra_tenant_id: str
    entra_client_id: str
    entra_client_secret: str

    # Application
    log_level: str = "INFO"
    max_input_length: int = 4000
    rate_limit_per_minute: int = 20

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    """Create and return a validated Settings instance."""
    return Settings()  # type: ignore[call-arg]
