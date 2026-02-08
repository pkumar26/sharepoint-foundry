"""Unit tests for configuration loader."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.config import Settings, get_settings


class TestSettings:
    """Tests for the Settings configuration model."""

    def _env_vars(self) -> dict[str, str]:
        """Return a complete set of required environment variables."""
        return {
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            "AZURE_OPENAI_DEPLOYMENT": "gpt-4o",
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
            "AZURE_OPENAI_API_VERSION": "2024-06-01",
            "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
            "AZURE_SEARCH_INDEX_NAME": "test-index",
            "COSMOS_ENDPOINT": "https://test.documents.azure.com:443/",
            "COSMOS_DATABASE": "test-db",
            "COSMOS_CONTAINER": "test-container",
            "ENTRA_TENANT_ID": "tenant-123",
            "ENTRA_CLIENT_ID": "client-456",
            "ENTRA_CLIENT_SECRET": "secret-789",
            "LOG_LEVEL": "DEBUG",
            "MAX_INPUT_LENGTH": "5000",
            "RATE_LIMIT_PER_MINUTE": "30",
        }

    def test_settings_loads_all_env_vars(self) -> None:
        env = self._env_vars()
        with patch.dict(os.environ, env, clear=False):
            settings = Settings()  # type: ignore[call-arg]

        assert settings.azure_openai_endpoint == "https://test.openai.azure.com/"
        assert settings.azure_search_endpoint == "https://test.search.windows.net"
        assert settings.cosmos_endpoint == "https://test.documents.azure.com:443/"
        assert settings.entra_tenant_id == "tenant-123"
        assert settings.entra_client_id == "client-456"
        assert settings.entra_client_secret == "secret-789"
        assert settings.log_level == "DEBUG"
        assert settings.max_input_length == 5000
        assert settings.rate_limit_per_minute == 30

    def test_settings_uses_defaults(self) -> None:
        minimal = {
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
            "COSMOS_ENDPOINT": "https://test.documents.azure.com:443/",
            "ENTRA_TENANT_ID": "t",
            "ENTRA_CLIENT_ID": "c",
            "ENTRA_CLIENT_SECRET": "s",
        }
        with patch.dict(os.environ, minimal, clear=False):
            settings = Settings()  # type: ignore[call-arg]

        assert settings.azure_openai_deployment == "gpt-4o"
        assert settings.azure_search_index_name == "sharepoint-docs-index"
        assert settings.cosmos_database == "sharepoint-agent"
        assert settings.log_level == "INFO"
        assert settings.max_input_length == 4000
        assert settings.rate_limit_per_minute == 20

    def test_settings_missing_required_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True), pytest.raises(ValidationError):
            Settings()  # type: ignore[call-arg]

    def test_get_settings_returns_instance(self) -> None:
        env = self._env_vars()
        with patch.dict(os.environ, env, clear=False):
            settings = get_settings()

        assert isinstance(settings, Settings)
