# Research: SharePoint Document Q&A Agent

**Feature**: `001-agent-setup` | **Date**: 2026-02-07

## 1. Microsoft Agent Framework Python SDK

- **Decision**: Use `autogen-agentchat==0.7.5`, `autogen-core==0.7.5`, `autogen-ext[openai,azure]==0.7.5`
- **Rationale**: This is Microsoft's unified Agent Framework for Python. The constitution mandates it. No PyPI package called `microsoft-agents` exists — the correct packages are in the `autogen-*` namespace.
- **Alternatives considered**: None — constitution mandates this SDK.

### Key Findings

- **Agent definition**: Use `AssistantAgent` from `autogen_agentchat.agents`. Tools are plain Python async functions auto-wrapped in `FunctionTool`.
- **Model client**: Use `AzureOpenAIChatCompletionClient` from `autogen_ext.models.openai` with `AzureTokenProvider` for managed identity auth.
- **Conversation context**: Pluggable via `model_context` parameter. `BufferedChatCompletionContext(buffer_size=N)` for sliding-window history. `UnboundedChatCompletionContext` to keep all messages.
- **State persistence**: `save_state()` / `load_state()` on agents and teams return JSON-serializable dicts. Store in Cosmos DB per conversation. Reload per request.
- **HTTP serving**: SDK does not include an HTTP server. Use FastAPI + uvicorn. Load agent state from DB per request, process, save state back.
- **Orchestration patterns available**:
  - `RoundRobinGroupChat` — sequential round-robin
  - `SelectorGroupChat` — LLM-based or custom next-agent selection
  - `Swarm` — agent-to-agent handoff via `HandoffMessage`
  - `MagenticOneGroupChat` — Magentic-One multi-agent collaboration
  - `GraphFlow` + `DiGraphBuilder` — directed graph with parallel fan-out/join, conditional edges, loops
- **For this feature**: Sequential single-agent pattern is sufficient (simplest pattern per constitution Principle IV).

## 2. Azure AI Search + SharePoint Integration

- **Decision**: Use Azure AI Search with SharePoint Online indexer (preview) + integrated vectorization + hybrid search (vector + BM25 + semantic ranking) + ACL-based security trimming.
- **Rationale**: Provides a turnkey pipeline: SharePoint → document cracking → chunking → embedding → index. No custom ETL code needed. Security trimming respects user permissions at query time.
- **Alternatives considered**:
  - SharePoint Remote Knowledge Source (Copilot Retrieval API) — no vector search, no custom ranking
  - Custom pipeline (SharePoint Webhooks → Blob → Blob indexer) — more infrastructure, but GA
  - Microsoft Copilot Studio — less customisable, platform lock-in

### Key Findings

- **SharePoint indexer**: Preview status (REST API `2025-11-01-preview`). Supports incremental indexing via change detection. Cracks DOCX, PPTX, XLSX, PDF, TXT, HTML, CSV, and more.
- **Integrated vectorization**: GA for Azure OpenAI skill/vectorizer pair. Skillset with Text Split + AzureOpenAIEmbedding skill. Eliminates separate embedding pipeline.
- **Hybrid search**: Single request with `search` (BM25) + `vectorQueries` (HNSW cosine) + semantic ranking. Results merged via Reciprocal Rank Fusion.
- **Security trimming**: SharePoint ACL ingestion stores `UserIds` and `GroupIds` in index. At query time, pass user's Entra token or apply OData filter. AI Search validates token against stored ACLs.
- **Python SDK**: `azure-search-documents`. Key classes: `SearchClient`, `VectorizedQuery`, `SearchField`.
- **Index schema**: Fields for `id`, `title`, `content`, `content_vector` (Collection(Edm.Single), 1536 dims), `source_url`, `last_modified`, `file_type`, `UserIds`, `GroupIds`.
- **Caveat**: SharePoint indexer is preview and "not recommended for production" by Microsoft. Fallback: custom webhook pipeline. For this project, preview is acceptable given the scope and timeline.

## 3. Azure Cosmos DB for Conversation Persistence

- **Decision**: Use Azure Cosmos DB NoSQL API with `azure-cosmos` Python SDK (v4.14.x). Partition by `/user_id`. Container-level TTL = 7,776,000 seconds (90 days). Session consistency. Serverless mode.
- **Rationale**: JSON document model fits conversation objects natively. Partition by user_id keeps all user conversations co-located. Serverless mode is cost-effective for bursty agent workloads. Session consistency guarantees read-your-own-writes.
- **Alternatives considered**:
  - Cosmos DB for PostgreSQL — relational overhead for flexible JSON docs
  - Azure Table Storage — no TTL, limited querying
  - Azure SQL — schema-heavy for nested arrays
  - Redis Cache — volatile, not designed for 90-day persistence

### Key Findings

- **Partition key**: `/user_id` — single-partition queries for user's conversations. 50 users = 50 logical partitions, well within limits.
- **TTL**: Set `default_ttl=7776000` at container creation. Timer resets on any upsert (based on `_ts`).
- **Auth**: `CosmosClient(url, DefaultAzureCredential())` with managed identity. Requires RBAC role `Cosmos DB Built-in Data Contributor`.
- **Operations**: `upsert_item()` for create/update, `read_item()` for point reads, `query_items()` with single-partition scope.
- **Cost**: Serverless mode recommended. ~400 RU/s handles 50 concurrent users comfortably.

## 4. Microsoft Entra ID On-Behalf-Of (OBO) Flow

- **Decision**: Use `msal` Python library (v1.34.x) with `ConfidentialClientApplication.acquire_token_on_behalf_of()`. Do NOT use `DefaultAzureCredential` for OBO.
- **Rationale**: OBO is the only flow that lets the backend call Graph API on behalf of the user while respecting the user's SharePoint permissions. `DefaultAzureCredential` is for app-identity only.
- **Alternatives considered**:
  - `DefaultAzureCredential` — cannot perform OBO; app-identity only
  - Client credentials flow (app-only) — bypasses user permissions, violates least-privilege
  - Direct token pass-through — cannot add Graph scopes

### Key Findings

- **Flow**: Frontend authenticates user → backend receives user token → `acquire_token_on_behalf_of(user_assertion=token, scopes=[...])` → exchanges for Graph token with user's permissions.
- **Scopes**: `Sites.Read.All` + `Files.Read.All` (delegated). These respect user's actual SharePoint permissions.
- **App registration**: Backend API app with client secret/certificate, exposed scope `api://<id>/access_as_user`, Graph delegated permissions.
- **Token validation**: Validate incoming token's `aud`, `iss`, `exp` claims. Use `PyJWT` or framework middleware.
- **Token cache**: MSAL handles caching/refresh. Use `SerializableTokenCache` partitioned per user for web servers.
- **Note on constitution**: Constitution says "Authentication MUST use Azure Identity (DefaultAzureCredential or managed identity)". For OBO specifically, `DefaultAzureCredential` cannot be used — `msal` is required. `DefaultAzureCredential` is still used for service-to-service auth (Cosmos DB, AI Search, OpenAI). This is a justified exception documented in Complexity Tracking.

## 5. Azure Container Apps Deployment

- **Decision**: Deploy as single Container App running FastAPI + Uvicorn. System-assigned managed identity. HTTP-based auto-scaling (10 concurrent requests/replica, min 1, max 10). Single region.
- **Rationale**: Purpose-built for containerised HTTP services. Auto-scale covers 50-user target with 2x headroom. Managed identity simplifies auth to all Azure services. No Kubernetes expertise required.
- **Alternatives considered**:
  - Azure App Service — less granular scaling controls
  - AKS — overkill for single-service deployment
  - Azure Functions — cold starts conflict with ≤5s response target
  - Azure VM — no managed auto-scaling

### Key Findings

- **Image**: Dockerfile with `uvicorn main:app --host 0.0.0.0 --port 8000`
- **Managed identity RBAC roles**:
  - Cosmos DB: `Cosmos DB Built-in Data Contributor`
  - AI Search: `Search Index Data Reader`
  - Azure OpenAI: `Cognitive Services OpenAI User`
- **Health probes**: HTTP `GET /health` on port 8000. Startup (5s delay, 30 retries), Liveness (10s period), Readiness (3s delay).
- **Auto-scaling**: 10 concurrent requests/replica × 10 max replicas = 100 max concurrent (2x headroom over 50 users).
- **Secrets**: Use Container Apps secrets for Entra client secret (OBO). All other auth via managed identity.

## 6. Rate Limiting in Async Python

- **Decision**: Implement in-memory sliding-window rate limiter using `asyncio` primitives. No external dependency needed.
- **Rationale**: 20 queries/minute/user is simple enough for an in-memory counter with timestamp tracking. stdlib `asyncio.Lock` + `collections.deque` of timestamps per user. Resets naturally when container scales (acceptable — rate limit is protective, not billing-critical).
- **Alternatives considered**:
  - Redis-backed rate limiter — adds a dependency (violates minimal dependencies principle) for a simple counter
  - `limits` PyPI package — unnecessary dependency for a straightforward sliding-window algorithm
  - Azure API Management — adds infrastructure complexity; rate limiting is application-level concern here

## Dependency Summary

| Package | Version | Justification |
|---------|---------|--------------|
| `autogen-agentchat` | 0.7.5 | Agent Framework SDK — agent definitions, orchestration |
| `autogen-ext[openai,azure]` | 0.7.5 | Azure OpenAI model client, Azure token provider |
| `azure-identity` | latest | DefaultAzureCredential for managed identity auth to Azure services |
| `azure-search-documents` | latest | Azure AI Search client for hybrid vector + keyword search |
| `azure-cosmos` | 4.14.x | Cosmos DB client for conversation persistence |
| `msal` | 1.34.x | Entra ID OBO flow — exchange user token for Graph API token |
| `fastapi` | latest | HTTP server framework for agent API |
| `uvicorn` | latest | ASGI server to run FastAPI |
| `pydantic` | latest (v2) | Data models (also a FastAPI dependency) |

**Total runtime dependencies**: 9 packages (6 Azure/Microsoft, 3 server framework). All justified per constitution Principle II.
