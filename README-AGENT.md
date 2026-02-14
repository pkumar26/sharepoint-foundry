# SharePoint Q&A Agent — Setup & Configuration

This guide covers how to configure and run the FastAPI-based SharePoint Document Q&A Agent locally and in production (Azure Container Apps).

> **Prerequisite**: Before running the agent you must set up at least one search backend. See [README-SHAREPOINT.md](README-SHAREPOINT.md) for indexing setup and notebook instructions.

---

## Architecture Overview

```
┌──────────────┐     Bearer JWT      ┌─────────────────────────────────┐
│  Client /    │ ──────────────────►  │  FastAPI Agent Backend          │
│  Frontend    │                      │  (src/main.py)                  │
└──────────────┘                      ├─────────────────────────────────┤
                                      │  Auth (OBO)    Rate Limiter     │
                                      │  Audit Logger  Conversation Svc │
                                      ├──────────┬──────────────────────┤
                                      │          │  SEARCH_APPROACH     │
                                      │          ▼                      │
                                      │  ┌─────────────────────────┐   │
                                      │  │  Search Backend Factory  │   │
                                      │  │  (SearchBackend protocol)│   │
                                      │  └────┬────────┬────────┬──┘   │
                                      │       │        │        │      │
                                      │   indexer  foundryiq  indexed  │
                                      │   (Approach 1) (2)    _sp (3)  │
                                      ├─────────────────────────────────┤
                                      │  AutoGen Agent (SharePointQA)  │
                                      │  → Azure OpenAI (gpt-4o)       │
                                      └─────────────────────────────────┘
                                                    │
                              ┌──────────────────────┼──────────────────┐
                              ▼                      ▼                  ▼
                      Azure AI Search         Azure Cosmos DB    Azure OpenAI
                      (search index or        (conversations)    (chat + embeddings)
                       knowledge base)
```

---

## Search Approaches

The agent supports three search backends, selectable via a single environment variable:

| Value | Approach | Backend Class | Auth | Notes |
|-------|----------|---------------|------|-------|
| `indexer` (default) | 1 — Direct Index Query | `IndexerSearchService` | Managed identity / `DefaultAzureCredential` | ACL security trimming via OData filter |
| `foundryiq` | 2 — FoundryIQ (Remote SharePoint) | `KnowledgeBaseSearchService` | OBO user token (`search.azure.com` scope) | Requires M365 Copilot license |
| `indexed_sharepoint` | 3 — Indexed SharePoint KB | `KnowledgeBaseSearchService` | Admin API key | No Copilot license needed |

Set `SEARCH_APPROACH` in your `.env` file or as an environment variable to switch.

---

## Environment Variables

Create a `.env` file in the project root (gitignored):

```bash
cp .env.template .env   # if a template exists, otherwise create manually
```

### Required (all approaches)

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | `https://myoai.openai.azure.com` |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search endpoint URL | `https://mysearch.search.windows.net` |
| `COSMOS_ENDPOINT` | Azure Cosmos DB endpoint URL | `https://mycosmos.documents.azure.com:443` |
| `ENTRA_TENANT_ID` | Microsoft Entra tenant ID | `cc4fb710-...` |
| `ENTRA_CLIENT_ID` | Backend app registration client ID | `806458c7-...` |

### Optional (with defaults)

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o` | Chat completion deployment name |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | `text-embedding-3-small` | Embedding deployment name |
| `AZURE_OPENAI_API_VERSION` | `2024-06-01` | Azure OpenAI API version |
| `AZURE_SEARCH_INDEX_NAME` | `sharepoint-docs-index` | Search index name (Approach 1) |
| `COSMOS_DATABASE` | `sharepoint-agent` | Cosmos DB database name |
| `COSMOS_CONTAINER` | `conversations` | Cosmos DB container name |
| `ENTRA_CLIENT_SECRET` | `""` | Client secret (not needed with managed identity) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `MAX_INPUT_LENGTH` | `4000` | Max characters per user message |
| `RATE_LIMIT_PER_MINUTE` | `20` | Per-user rate limit |

### Search approach selection

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARCH_APPROACH` | `indexer` | One of: `indexer`, `foundryiq`, `indexed_sharepoint` |

### Additional vars for Knowledge Base approaches (2 & 3)

| Variable | Default | Required When | Description |
|----------|---------|---------------|-------------|
| `AZURE_SEARCH_API_KEY` | `""` | `indexed_sharepoint` (required), `foundryiq` (fallback) | Azure AI Search admin API key |
| `AZURE_SEARCH_API_VERSION` | `2025-11-01-preview` | `foundryiq` or `indexed_sharepoint` | API version for KB retrieve calls |
| `KNOWLEDGE_BASE_NAME` | `""` | `foundryiq` or `indexed_sharepoint` | Name of the knowledge base |
| `KNOWLEDGE_SOURCE_NAME` | `""` | `foundryiq` or `indexed_sharepoint` | Name of the knowledge source |

### Azure OpenAI authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_OPENAI_API_KEY` | `""` | Azure OpenAI API key. When set, uses key-based auth instead of `DefaultAzureCredential`. **Recommended for local development** to avoid slow managed-identity probing. |

> **Tip**: On local machines, `DefaultAzureCredential` tries multiple credential sources (managed identity, CLI, etc.) which can add 10–30 seconds to the first request. Setting `AZURE_OPENAI_API_KEY` bypasses this entirely.

---

## Local Development — Setup

### Prerequisites

- Python 3.11+ (tested with 3.11 and 3.13)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- At least one search backend configured (see [README-SHAREPOINT.md](README-SHAREPOINT.md))
- Azure resources provisioned: Azure OpenAI, Azure AI Search, Entra ID app registration

### 1. Clone and install dependencies

```bash
git clone https://github.com/pkumar26/sharepoint-foundry.git
cd sharepoint-foundry

# Option A: uv (recommended — faster)
python -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Option B: pip
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Create the `.env` file

Copy the template and fill in your values:

```bash
cp .env.template .env
```

Minimal `.env` for Approach 3 (Indexed SharePoint):

```env
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://<your-openai>.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_KEY=<your-openai-api-key>    # Recommended for local dev

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://<your-search>.search.windows.net
SEARCH_APPROACH=indexed_sharepoint
AZURE_SEARCH_API_KEY=<your-search-admin-key>
KNOWLEDGE_BASE_NAME=<your-kb-name>
KNOWLEDGE_SOURCE_NAME=<your-ks-name>

# Azure Cosmos DB
COSMOS_ENDPOINT=https://<your-cosmos>.documents.azure.com:443

# Microsoft Entra ID
ENTRA_TENANT_ID=<your-tenant-id>
ENTRA_CLIENT_ID=<your-app-client-id>
```

Minimal `.env` for Approach 1 (Indexer — direct index query):

```env
AZURE_OPENAI_ENDPOINT=https://<your-openai>.openai.azure.com
AZURE_OPENAI_API_KEY=<your-openai-api-key>
AZURE_SEARCH_ENDPOINT=https://<your-search>.search.windows.net
AZURE_SEARCH_API_KEY=<your-search-admin-key>    # Or use az login + RBAC
AZURE_SEARCH_INDEX_NAME=sharepoint-docs-index
SEARCH_APPROACH=indexer
COSMOS_ENDPOINT=https://<your-cosmos>.documents.azure.com:443
ENTRA_TENANT_ID=<your-tenant-id>
ENTRA_CLIENT_ID=<your-app-client-id>
```

### 3. Start the server

```bash
uvicorn src.main:app --reload --port 8000
```

> **Note**: First startup takes 15–30 seconds due to Python cold-importing `autogen-agentchat`, `opentelemetry`, and `pydantic`. Subsequent restarts (with `--reload`) are faster.

The agent will be available at `http://localhost:8000`.

---

## Local Development — Testing

### Step 1: Health check

```bash
curl http://localhost:8000/health
```

Expected:
```json
{"status": "healthy", "version": "0.1.0", "timestamp": "..."}
```

### Step 2: Test the chat endpoint

The `/chat` endpoint requires a valid Entra ID JWT in the `Authorization` header. For local testing you can generate a mock JWT:

```bash
# Generate a mock JWT with required claims
TOKEN=$(python3 -c "
import base64, json
h = base64.urlsafe_b64encode(json.dumps({'typ':'JWT','alg':'RS256'}).encode()).decode().rstrip('=')
p = base64.urlsafe_b64encode(json.dumps({
    'aud': '<your-ENTRA_CLIENT_ID>',
    'iss': 'https://login.microsoftonline.com/<your-ENTRA_TENANT_ID>/v2.0',
    'sub': 'test-user-001',
    'name': 'Test User',
    'oid': 'test-user-001',
    'tid': '<your-ENTRA_TENANT_ID>',
    'preferred_username': 'test@contoso.com',
    'exp': 9999999999
}).encode()).decode().rstrip('=')
print(f'{h}.{p}.' + base64.urlsafe_b64encode(b'fake').decode().rstrip('='))
")

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "What is the travel expense policy?"}'
```

> **Note**: The mock JWT bypasses cryptographic verification (which is disabled in dev by default). In production, Entra ID issues real signed tokens.

Expected response (with documents):
```json
{
  "conversation_id": "<uuid>",
  "message": {
    "id": "<uuid>",
    "role": "assistant",
    "content": "According to the Travel Expense Policy document...",
    "source_references": [
      {
        "document_title": "Travel Expense Policy",
        "document_url": "https://sharepoint.com/...",
        "excerpt": "...",
        "relevance_score": 0.95
      }
    ],
    "timestamp": "..."
  }
}
```

If the search backend has no matching documents, you'll get:
```json
{
  "conversation_id": "<uuid>",
  "message": {
    "content": "I couldn't find relevant information in the available SharePoint documents to answer your question.",
    "source_references": []
  }
}
```

### Step 3: Run unit tests

```bash
# All unit tests
pytest tests/unit/ -v

# With coverage
pytest tests/unit/ --cov=src --cov-report=term-missing
```

### Step 4: Run contract tests

```bash
pytest tests/contract/ -v
```

### Step 5: Integration tests (requires running server)

```bash
# Start the server first, then in another terminal:
pytest tests/integration/ -v
```

### Troubleshooting local setup

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: No module named 'src'` | Package not installed | Run `pip install -e .` or add `PYTHONPATH=.` |
| Server hangs on first request (30+ seconds) | `DefaultAzureCredential` probing managed identity | Set `AZURE_OPENAI_API_KEY` in `.env` |
| `error while attempting to bind on address` | Port 8000 in use | `kill -9 $(lsof -ti :8000)` then restart |
| `{"detail":{"error":"unauthorized","message":"'tid'"}}` | JWT missing required claims | Regenerate mock JWT with `tid`, `oid`, `name`, `preferred_username` |
| `400 Bad Request` from KB retrieve API | Wrong API version or body format | Ensure `AZURE_SEARCH_API_VERSION=2025-11-01-preview` |
| `403 Forbidden` from Search index | No RBAC role or missing API key | Set `AZURE_SEARCH_API_KEY` or assign *Search Index Data Reader* role |

---

## Switching Search Approaches

### Approach 1 — Indexer (default)

Ensure you've run `notebooks/setup-indexer-approach.ipynb` first.

```env
SEARCH_APPROACH=indexer
AZURE_SEARCH_INDEX_NAME=sharepoint-docs-index
```

No additional configuration needed — uses `DefaultAzureCredential` for auth.

### Approach 2 — FoundryIQ

Ensure you've run `notebooks/setup-foundryiq-approach.ipynb` first.

```env
SEARCH_APPROACH=foundryiq
AZURE_SEARCH_API_KEY=<your-admin-key>
KNOWLEDGE_BASE_NAME=<your-kb-name>
KNOWLEDGE_SOURCE_NAME=<your-ks-name>
```

> **Note**: This approach requires the user's JWT to be exchanged via OBO for an Azure AI Search token (`https://search.azure.com/.default` scope). The `ENTRA_CLIENT_SECRET` must be set for the OBO exchange. A Microsoft 365 Copilot license is required for the calling user.

### Approach 3 — Indexed SharePoint

Ensure you've run `notebooks/setup-indexed-sharepoint-approach.ipynb` first.

```env
SEARCH_APPROACH=indexed_sharepoint
AZURE_SEARCH_API_KEY=<your-admin-key>
KNOWLEDGE_BASE_NAME=sharepoint-indexed-kb
KNOWLEDGE_SOURCE_NAME=sharepoint-indexed-ks
```

No user token delegation needed — uses the admin API key for authentication.

---

## Docker

### Build

```bash
docker build -t sharepoint-agent .
```

### Run

```bash
docker run -p 8000:8000 --env-file .env sharepoint-agent
```

---

## Azure Container Apps — Deployment

Infrastructure is defined in `infra/main.bicep`. The deploy script automates the full flow.

### Prerequisites

- Azure CLI installed and logged in (`az login`)
- An Azure subscription selected (`az account set -s <subscription-id>`)
- A resource group created (`az group create -n <rg-name> -l <region>`)
- Azure OpenAI, AI Search, and Cosmos DB resources provisioned
- Parameter file filled in: `infra/main.bicepparam`

### Deploy

```bash
./scripts/deploy.sh -g <resource-group> -e <environment-name> [-t <image-tag>]
```

The script executes 4 steps:
1. **Infrastructure**: Deploys Bicep template (ACR, Container Apps Environment, Container App with system-assigned managed identity + RBAC)
2. **Build**: Builds Docker image in ACR using `az acr build`
3. **Update**: Points the Container App to the new image
4. **Verify**: Prints the app URL for health check

### Key Bicep parameters for search approach

| Parameter | Default | Description |
|-----------|---------|-------------|
| `searchApproach` | `indexer` | Search backend to use |
| `azureSearchApiKey` | `""` | Admin key (stored as Container App secret) |
| `azureSearchApiVersion` | `2025-11-01-preview` | KB API version |
| `knowledgeBaseName` | `""` | KB name |
| `knowledgeSourceName` | `""` | KS name |

### Auth in Azure vs locally

In Azure Container Apps, the system-assigned managed identity is used automatically via `DefaultAzureCredential`. The deploy script assigns the required RBAC roles:
- **Cognitive Services OpenAI User** → Azure OpenAI
- **Search Index Data Reader** → Azure AI Search (Approach 1)
- **Cosmos DB Data Contributor** → Cosmos DB

You do **not** need `AZURE_OPENAI_API_KEY` or `AZURE_SEARCH_API_KEY` when deployed — managed identity handles everything. These keys are only needed for local development.

---

## Azure Container Apps — Post-Deployment Testing

After `deploy.sh` completes, verify the deployment:

### Step 1: Health check

```bash
# Get the app FQDN
FQDN=$(az containerapp show -g <resource-group> -n ca-<environment-name> \
  --query "properties.configuration.ingress.fqdn" -o tsv)

curl https://$FQDN/health
```

Expected:
```json
{"status": "healthy", "version": "0.1.0", "timestamp": "..."}
```

### Step 2: Check container logs

```bash
az containerapp logs show \
  -g <resource-group> \
  -n ca-<environment-name> \
  --type console \
  --tail 50
```

Look for:
- `INFO: Uvicorn running on http://0.0.0.0:8000` — server started
- No `ERROR` lines during startup

### Step 3: Test with a real Entra ID token

To test the `/chat` endpoint in Azure, you need a real Entra ID token (not the mock JWT used locally):

```bash
# Acquire a token for your app registration
TOKEN=$(az account get-access-token \
  --resource api://<your-ENTRA_CLIENT_ID> \
  --query accessToken -o tsv)

# Send a chat request
curl -X POST https://$FQDN/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "What is the travel expense policy?"}'
```

### Step 4: Verify search backend connectivity

If the chat response returns a 503 error, check:

```bash
# Check environment variables are set correctly
az containerapp show -g <resource-group> -n ca-<environment-name> \
  --query "properties.template.containers[0].env[].name" -o tsv

# Check managed identity role assignments
PRINCIPAL_ID=$(az containerapp show -g <resource-group> -n ca-<environment-name> \
  --query "identity.principalId" -o tsv)
az role assignment list --assignee $PRINCIPAL_ID -o table
```

### Step 5: Scale and monitor

```bash
# View revision status
az containerapp revision list -g <resource-group> -n ca-<environment-name> -o table

# Stream live logs
az containerapp logs show -g <resource-group> -n ca-<environment-name> \
  --type console --follow

# Check metrics (requests, latency, errors)
az monitor metrics list \
  --resource $(az containerapp show -g <resource-group> -n ca-<environment-name> --query id -o tsv) \
  --metric Requests --interval PT1M
```

### Troubleshooting Azure deployment

| Symptom | Cause | Fix |
|---------|-------|-----|
| Container keeps restarting | Missing required env vars | Check `az containerapp show` for missing settings |
| 503 on `/chat` | Search service unreachable | Verify `AZURE_SEARCH_ENDPOINT`, check firewall rules |
| 401 on `/chat` | Token audience mismatch | Ensure token `aud` matches `ENTRA_CLIENT_ID` |
| `DefaultAzureCredential` errors | Missing RBAC roles | Re-run `az role assignment create` for the managed identity |
| Slow first response (15-30s) | Cold start | Normal for first request — Python imports are heavy. Consider min replicas ≥ 1 |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check (used by Container Apps probes) |
| `POST` | `/chat` | Send a message to the Q&A agent |
| `GET` | `/conversations` | List user's conversations |
| `GET` | `/conversations/{id}` | Get conversation with message history |

### POST /chat

**Request:**
```json
{
  "message": "What is the travel expense policy?",
  "conversation_id": null
}
```

**Response:**
```json
{
  "conversation_id": "uuid",
  "message": {
    "id": "uuid",
    "role": "assistant",
    "content": "According to the Travel Expense Policy document...",
    "source_references": [
      {
        "document_title": "Travel Expense Policy",
        "document_url": "https://sharepoint.com/...",
        "excerpt": "...",
        "relevance_score": 0.95
      }
    ],
    "timestamp": "2026-02-14T..."
  }
}
```

---

## Project Structure

```
src/
├── main.py                    # FastAPI app, /chat endpoint, search backend factory
├── config.py                  # Environment-based settings (pydantic BaseSettings)
├── logging_config.py          # Structured logging setup
├── agents/
│   └── sharepoint_qa.py       # AutoGen-based Q&A agent
├── models/
│   ├── conversation.py        # Conversation & message models
│   ├── document.py            # SearchResult & SourceReference models
│   ├── errors.py              # Error codes & response models
│   └── user.py                # User model (from JWT claims)
└── services/
    ├── search.py              # SearchBackend protocol + IndexerSearchService (Approach 1)
    ├── kb_search.py           # KnowledgeBaseSearchService (Approaches 2 & 3)
    ├── auth.py                # Entra ID JWT validation + OBO token exchange
    ├── audit.py               # Query audit logging
    ├── conversation.py        # Cosmos DB conversation persistence
    └── rate_limiter.py        # Per-user rate limiting
```

---

## Testing

### Unit tests

```bash
pytest tests/unit/ -v
```

### Contract tests

Validate API request/response schemas:

```bash
pytest tests/contract/ -v
```

### Integration tests

Requires a running server (`uvicorn src.main:app --port 8000`):

```bash
pytest tests/integration/ -v
```

### All tests with coverage

```bash
pytest --cov=src --cov-report=term-missing tests/
```

### Quick smoke test checklist

Use this to verify a deployment (local or Azure):

1. **Health**: `GET /health` → 200 with `{"status":"healthy"}`
2. **Chat**: `POST /chat` with valid JWT → 200 with `conversation_id` and `message`
3. **Rate limit**: Send 21 requests in 1 minute → 429 on the 21st
4. **Bad input**: `POST /chat` with empty message → 400
5. **No auth**: `POST /chat` without `Authorization` header → 401
