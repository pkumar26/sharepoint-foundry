# SharePoint Foundry — Document Q&A Agent

An AI-powered Q&A agent that answers questions from your SharePoint document libraries. Built with [Microsoft AutoGen](https://github.com/microsoft/autogen), FastAPI, Azure OpenAI, and Azure AI Search.

Users sign in with their Microsoft Entra ID account, ask natural-language questions, and receive grounded answers with source citations — all respecting SharePoint document-level permissions (ACLs).

---

## Key Features

- **Grounded answers** — responses cite specific documents with titles, URLs, and relevance scores
- **Three search backends** — choose between a full indexer pipeline, FoundryIQ (live SharePoint), or an indexed knowledge base
- **Security trimming** — ACL-based filtering ensures users only see documents they have access to
- **Conversation persistence** — chat history stored in Azure Cosmos DB with LLM-generated titles
- **Web frontend** — single-page app with Microsoft Entra ID sign-in (MSAL.js)
- **On-Behalf-Of (OBO) flow** — user identity propagated through the full request chain
- **Per-user rate limiting** and structured audit logging
- **One-command Azure deployment** via Bicep + Container Apps

---

## Architecture

```
                              ┌─────────────────────────────────────────┐
  Browser (SPA)               │  Azure Container App                    │
  ┌──────────┐  Bearer JWT    │  ┌───────────────────────────────────┐  │
  │ index.html│──────────────►│  │  FastAPI (src/main.py)            │  │
  │ MSAL.js   │               │  │  Auth · Rate Limiter · Audit     │  │
  └──────────┘               │  │  ┌─────────────────────────────┐  │  │
                              │  │  │  SearchBackend Factory       │  │  │
                              │  │  │  indexer | foundryiq |       │  │  │
                              │  │  │  indexed_sharepoint          │  │  │
                              │  │  └─────────────────────────────┘  │  │
                              │  │  AutoGen Agent (SharePointQA)     │  │
                              │  └───────────────────────────────────┘  │
                              └──────────┬──────────┬──────────┬───────┘
                                         │          │          │
                                         ▼          ▼          ▼
                                   Azure AI     Azure       Azure
                                   Search      Cosmos DB   OpenAI
                                   (docs)     (history)   (gpt-4o)
```

---

## Search Approaches

| # | Approach | How it works | Copilot license? |
|---|----------|--------------|------------------|
| 1 | **Indexer** (default) | Full pipeline: Data Source → Index → Skillset → Indexer. Documents crawled, chunked, embedded. | No |
| 2 | **FoundryIQ** | Live query via Copilot Retrieval API — no index built | **Yes** |
| 3 | **Indexed SharePoint** | Auto-generated pipeline from a single knowledge source definition | No |

Set `SEARCH_APPROACH=indexer|foundryiq|indexed_sharepoint` to switch.

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Azure OpenAI, Azure AI Search, Azure Cosmos DB, and an Entra ID app registration
- At least one search backend configured (see [README-SHAREPOINT.md](README-SHAREPOINT.md))

### 1. Clone & install

```bash
git clone https://github.com/pkumar26/sharepoint-foundry.git
cd sharepoint-foundry
python -m venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"       # or: pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.template .env
# Fill in your Azure endpoints, keys, and Entra IDs
```

### 3. Run

```bash
uvicorn src.main:app --reload --port 8000
```

Open `http://localhost:8000` for the web UI, or test via curl:

```bash
curl http://localhost:8000/health
```

See [README-AGENT.md](README-AGENT.md) for full environment variable reference, mock JWT testing, and troubleshooting.

---

## Deploy to Azure

Infrastructure is defined in Bicep and deployed via a single script:

```bash
./scripts/deploy.sh -g <resource-group> -e <environment-name> [-t <image-tag>]
```

This provisions an ACR, Container Apps Environment, and Container App with managed identity and RBAC. See [README-AGENT.md § Azure Container Apps](README-AGENT.md#azure-container-apps--deployment) for details.

---

## Project Structure

```
├── src/
│   ├── main.py                    # FastAPI app & endpoints
│   ├── config.py                  # Pydantic BaseSettings
│   ├── agents/sharepoint_qa.py    # AutoGen Q&A agent
│   ├── models/                    # Pydantic data models
│   └── services/                  # Auth, search, conversation, audit, rate limiting
├── static/                        # SPA frontend (HTML/CSS/JS + MSAL.js)
├── notebooks/                     # Jupyter setup notebooks (one per approach)
├── infra/                         # Bicep IaC templates
├── scripts/deploy.sh              # Azure deployment script
├── tests/                         # Unit, contract, and integration tests
├── Dockerfile                     # Production container image
└── pyproject.toml                 # Dependencies & project metadata
```

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | No | Health check |
| `GET` | `/approaches` | No | Available search backends |
| `GET` | `/auth/config` | No | Entra ID config for the SPA |
| `POST` | `/chat` | Yes | Send a message and get a grounded answer |
| `GET` | `/conversations` | Yes | List user's conversations |
| `GET` | `/conversations/{id}` | Yes | Full conversation with messages |

---

## Testing

```bash
pytest tests/unit/ -v                # Unit tests
pytest tests/contract/ -v            # API contract tests
pytest tests/integration/ -v         # Integration tests (requires running server)
pytest --cov=src tests/              # All tests with coverage
```

---

## Documentation

| Document | Contents |
|----------|----------|
| [README-AGENT.md](README-AGENT.md) | Agent configuration, environment variables, local dev, Docker, Azure deployment, troubleshooting |
| [README-SHAREPOINT.md](README-SHAREPOINT.md) | SharePoint + Azure AI Search setup, Entra app registration, indexing notebooks |

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
