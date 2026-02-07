# Quickstart: SharePoint Document Q&A Agent

**Feature**: `001-agent-setup` | **Date**: 2026-02-07

## Prerequisites

- Python 3.11+
- Azure subscription with:
  - Azure OpenAI (GPT-4o + text-embedding-3-small deployed)
  - Azure AI Search (Standard tier for semantic ranking)
  - Azure Cosmos DB (NoSQL, serverless mode)
  - Microsoft Entra ID app registration (backend API)
  - SharePoint Online with test documents
- `uv` or `pip` for package management

## 1. Clone and Install

```bash
git clone <repo-url>
cd sharepoint-foundryagent
git checkout 001-agent-setup

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

## 2. Configure Environment

Copy the example env file and fill in your Azure resource details:

```bash
cp .env.example .env
```

Required environment variables:

```env
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://<your-instance>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
AZURE_OPENAI_API_VERSION=2024-06-01

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://<your-instance>.search.windows.net
AZURE_SEARCH_INDEX_NAME=sharepoint-docs-index

# Azure Cosmos DB
COSMOS_ENDPOINT=https://<your-instance>.documents.azure.com:443/
COSMOS_DATABASE=sharepoint-agent
COSMOS_CONTAINER=conversations

# Microsoft Entra ID (for OBO flow)
ENTRA_TENANT_ID=<your-tenant-id>
ENTRA_CLIENT_ID=<backend-app-client-id>
ENTRA_CLIENT_SECRET=<backend-app-client-secret>

# Application
LOG_LEVEL=INFO
MAX_INPUT_LENGTH=4000
RATE_LIMIT_PER_MINUTE=20
```

## 3. Set Up Azure AI Search Index

Configure the SharePoint indexer and search index. This is a one-time setup:

```bash
# Use the Azure portal or REST API to:
# 1. Create a data source (type: sharepoint) connected to your SharePoint tenant
# 2. Create a skillset with Text Split + AzureOpenAIEmbedding skills
# 3. Create the search index with vector + keyword fields (see data-model.md)
# 4. Create an indexer that connects data source → skillset → index
# 5. Run the indexer to populate the index
```

## 4. Initialize Cosmos DB

```bash
# The app auto-creates the database and container on first startup
# if they don't exist (with correct TTL and partition key config).
# Alternatively, create manually via Azure portal.
```

## 5. Run Locally

```bash
# Login to Azure (for DefaultAzureCredential)
az login

# Start the development server
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

## 6. Test

```bash
# Health check
curl http://localhost:8000/health

# Send a question (requires valid Entra token)
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <your-entra-token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the company leave policy?"}'

# List conversations
curl http://localhost:8000/conversations \
  -H "Authorization: Bearer <your-entra-token>"
```

## 7. Run Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests (requires Azure resources)
pytest tests/integration/ -v

# All tests with coverage
pytest --cov=src --cov-report=term-missing
```

## 8. Lint and Type Check

```bash
ruff check src/ tests/
ruff format --check src/ tests/
pyright src/
```

## Architecture Overview

```
User → [Entra Auth] → FastAPI → Agent (autogen-agentchat)
                                    │
                                    ├── Tool: search_documents()
                                    │     └── Azure AI Search (hybrid)
                                    │           └── SharePoint indexer
                                    │
                                    ├── Tool: get_conversation_context()
                                    │     └── Cosmos DB
                                    │
                                    └── Azure OpenAI (GPT-4o)
                                          └── Grounded answer + citations
```
