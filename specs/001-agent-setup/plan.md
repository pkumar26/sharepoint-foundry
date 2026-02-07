# Implementation Plan: SharePoint Document Q&A Agent

**Branch**: `001-agent-setup` | **Date**: 2026-02-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-agent-setup/spec.md`

## Summary

Build a SharePoint document Q&A agent using the Microsoft Agent Framework Python SDK that authenticates users via Microsoft Entra ID, retrieves and searches documents from SharePoint via Microsoft Graph API + Azure AI Search (hybrid vector + keyword), persists conversation history in Azure Cosmos DB, and grounds every response exclusively in SharePoint document content with source citations. The agent enforces document-level permissions, maintains per-conversation context for follow-up questions, rate-limits users at 20 queries/minute, emits structured JSON logs with an audit trail, and targets ≤5s response time for single-document answers at 50 concurrent users.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: Microsoft Agent Framework Python SDK (`autogen-agentchat==0.7.5`, `autogen-ext[openai,azure]==0.7.5`), `azure-identity`, `azure-search-documents`, `azure-cosmos`, `msal`, `fastapi`, `uvicorn`, `pydantic`  
**Storage**: Azure Cosmos DB (conversation history), Azure AI Search (document index with vector embeddings)  
**Testing**: `pytest` with `pytest-asyncio`  
**Target Platform**: Azure Container Apps (single-region, auto-scale, managed identity)  
**Project Type**: single  
**Performance Goals**: ≤5s p95 for single-document answers, ≤10s p95 for multi-document synthesis, 50 concurrent users  
**Constraints**: 99.5% monthly uptime, 4,000 char max input, 20 queries/min/user rate limit, single Entra tenant  
**Scale/Scope**: 50 concurrent users, SharePoint document libraries (DOCX, PPTX, XLSX, PDF, TXT)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Research Check

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Clean Code | ✅ PASS | Plan enforces single-responsibility modules, docstrings, ruff + pyright in CI |
| II | Minimal Dependencies | ✅ PASS | 5 runtime dependencies, all justified: SDK (core), azure-identity (auth), azure-search-documents (retrieval), azure-cosmos (persistence), openai (embeddings + LLM). No redundant utility libraries |
| III | Agent Framework First | ✅ PASS | All agent/workflow logic uses `microsoft-agents` SDK. No LangChain, CrewAI, or hand-rolled orchestration |
| IV | Orchestration Versatility | ✅ PASS | Sequential pattern for single-agent Q&A (simplest sufficient pattern); durable workflow support via SDK checkpoints for conversation recovery |
| V | SharePoint-Only Integration | ✅ PASS | All external data comes from SharePoint via Graph API. Azure AI Search and Cosmos DB are infrastructure services, not external data integrations |
| VI | Test-Driven Quality | ✅ PASS | Plan includes pytest structure with contract/integration/unit dirs, fixtures for SharePoint mocks, TDD workflow |

**Pre-research gate: PASS — no violations.**

### Post-Design Re-Check

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Clean Code | ✅ PASS | Single-responsibility modules: models in `src/models/`, services in `src/services/`, agent in `src/agents/`. All public APIs documented in OpenAPI contract |
| II | Minimal Dependencies | ✅ PASS | 9 runtime packages total, all justified in research.md. No stdlib-duplicating libraries |
| III | Agent Framework First | ✅ PASS | `autogen-agentchat` is the agent runtime. Tools registered via SDK's `FunctionTool`. No alternative frameworks |
| IV | Orchestration Versatility | ✅ PASS | Sequential single-agent pattern selected (simplest sufficient). `save_state()`/`load_state()` for durability. SDK supports multi-agent upgrade path |
| V | SharePoint-Only Integration | ✅ PASS | All external data from SharePoint via Graph API. `msal` used for OBO flow per constitution (user-delegation flows use MSAL). `DefaultAzureCredential` used for service-to-service auth |
| VI | Test-Driven Quality | ✅ PASS | Test structure: `tests/contract/`, `tests/integration/`, `tests/unit/`, `tests/fixtures/`. TDD workflow enforced |

**Post-design gate: PASS — no violations.**

## Project Structure

### Documentation (this feature)

```text
specs/001-agent-setup/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/
├── agents/              # Agent definitions (Microsoft Agent Framework)
│   ├── __init__.py
│   └── sharepoint_qa.py # Main Q&A agent with tools
├── models/              # Data models (Pydantic)
│   ├── __init__.py
│   ├── conversation.py  # Conversation, Message entities
│   ├── document.py      # Document, SourceReference entities
│   └── user.py          # User entity
├── services/            # Business logic services
│   ├── __init__.py
│   ├── auth.py          # Entra ID authentication + token management
│   ├── search.py        # Azure AI Search client (hybrid retrieval)
│   ├── conversation.py  # Cosmos DB conversation persistence
│   ├── rate_limiter.py  # Per-user rate limiting
│   └── audit.py         # Audit trail logging
├── config.py            # Environment-based configuration
├── logging_config.py    # Structured JSON logging setup
└── main.py              # Application entry point (HTTP server)

tests/
├── fixtures/            # Shared SharePoint response mocks/fakes
│   ├── sharepoint_responses.json
│   └── sample_documents/
├── contract/            # API contract tests
│   └── test_chat_api.py
├── integration/         # End-to-end workflow tests
│   ├── test_qa_flow.py
│   ├── test_auth_flow.py
│   └── test_conversation_persistence.py
└── unit/                # Unit tests per module
    ├── test_search.py
    ├── test_conversation.py
    ├── test_rate_limiter.py
    └── test_audit.py

pyproject.toml           # Project metadata + dependencies with justifications
```

**Structure Decision**: Single project layout. The agent is a single Python service with no separate frontend — the agent exposes an HTTP API consumed by any chat client. This is the simplest structure that satisfies the requirements.

## Complexity Tracking

> No violations. Constitution Principle V explicitly permits MSAL for user-delegation (OBO) flows.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *(none)* | — | — |
