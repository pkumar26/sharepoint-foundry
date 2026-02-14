# SharePoint + Azure AI Search Setup Guide

This guide walks through setting up the Azure AI Search pipeline to index SharePoint documents with **text chunking**, **vector embeddings**, **semantic ranking**, and **ACL-based security trimming**.

> **API Version**: `2025-11-01-preview` (SharePoint indexer is in public preview)

---

## Prerequisites

| Resource | Requirements |
|----------|-------------|
| **Azure AI Search** | Basic tier or higher, **system-assigned managed identity enabled** |
| **Azure OpenAI** | With an embedding model deployed (e.g. `text-embedding-ada-002`) |
| **SharePoint Online** | Site with documents in a document library |
| **Entra ID App Registration** | Application permissions for the indexer |

### Tools

- [VS Code](https://code.visualstudio.com/) with the [REST Client extension](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) to execute requests from `setup.rest`
- Alternatively, use the **Jupyter notebooks** in `notebooks/` — no copying commands needed

---

## Setup Options

There are **three approaches** to connect SharePoint to Azure AI Search, and **two ways** to run them:

### Approach 1: Indexer Pipeline (Traditional)

Builds a full indexing pipeline: Data Source → Index → Skillset → Indexer. Documents are crawled, chunked, embedded, and stored in a search index you control.

- ✅ Cross-tenant supported
- ✅ Custom chunking, embeddings, field mappings
- ✅ App permissions (no user token needed for indexing)
- ⚠️ More setup steps (4 REST calls)

### Approach 2: FoundryIQ / Agentic Retrieval (New)

Uses `RemoteSharePointKnowledgeSource` + Knowledge Base. No index is built — the [Copilot Retrieval API](https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/api/ai-services/retrieval/overview) queries SharePoint live at query time.

- ✅ Minimal setup (2 REST calls + query)
- ✅ Automatic security trimming via user identity
- ⚠️ **Microsoft 365 Copilot license required** (usage billed through M365)
- ❌ Same-tenant only (Azure & M365 must share Entra ID tenant)
- ❌ 200 requests/user/hour, 1,500 char query limit, max 25 results
- ❌ Requires a chat model (`gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-5`, `gpt-5-mini`, `gpt-5-nano`)
- ❌ Hybrid queries only for `.doc`, `.docx`, `.pptx`, `.pdf`, `.aspx`, `.one`

**Authentication**: The retrieve call requires two headers:
1. `api-key` — authenticates to Azure AI Search
2. `x-ms-query-source-authorization` — user identity JWT scoped to `https://search.azure.com/.default` (raw token, no `Bearer` prefix). Azure AI Search uses this to call the Copilot Retrieval API on behalf of the user.

> **Reference**: [Create a remote SharePoint knowledge source](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-sharepoint-remote?pivots=python)

### Approach 3: Indexed SharePoint Knowledge Source (New)

Uses `IndexedSharePointKnowledgeSource` to **auto-generate** a full indexer pipeline (data source, index, skillset, indexer) from a single knowledge source definition. Combines the benefits of indexed data with the simplicity of agentic retrieval.

- ✅ Auto-generates indexer pipeline from one API call
- ✅ Cross-tenant supported
- ✅ No Copilot license required
- ✅ Standard search rate limits (no 200 req/user/hour cap)
- ✅ Embedding model for vector search
- ✅ Optional image verbalization via chat model
- ⚠️ Requires Azure OpenAI API key (passed in knowledge source definition)
- ⚠️ Auto-generated objects should not be edited manually
- ❌ Less customization than manual indexer pipeline (Approach 1)

**Pipeline**: Knowledge Source (auto-generates data source + index + skillset + indexer) → Knowledge Base → Retrieve

> **Reference**: [Create an indexed SharePoint knowledge source](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-sharepoint-indexed?pivots=python)

### How to run

| Method | Files | Best for |
|--------|-------|----------|
| **REST Client** (VS Code extension) | `setup.rest` | Indexer approach only; quick send-request workflow |
| **Jupyter Notebooks** | `notebooks/setup-indexer-approach.ipynb` | Indexer approach; executable cells, no copying |
| **Jupyter Notebooks** | `notebooks/setup-foundryiq-approach.ipynb` | FoundryIQ approach; executable cells, no copying |
| **Jupyter Notebooks** | `notebooks/setup-indexed-sharepoint-approach.ipynb` | Indexed knowledge source approach; executable cells, no copying |

#### Notebook setup

1. Copy the env template:
   ```bash
   cp notebooks/.env.template notebooks/.env
   ```
2. Fill in your values in `notebooks/.env`
3. Install dependencies: `pip install requests python-dotenv`
4. Open the notebook and run cells top-to-bottom

> Both `notebooks/.env` and `.vscode/settings.json` are gitignored — secrets stay local.

---

## 1. Register the Entra ID Application

The indexer needs an app registration to authenticate against SharePoint.

1. **Azure Portal** → **Microsoft Entra ID** → **App registrations** → **+ New registration**
   - Name: e.g. `sharepoint-search-indexer`
   - Account type: **Single tenant**
   - Redirect URI: skip
2. **Create a client secret**: App registration → **Certificates & secrets** → **+ New client secret** → copy the **Value**
3. **Grant API permissions**: App registration → **API permissions** → **+ Add a permission** → **Microsoft Graph** → **Application permissions**:
   - `Files.Read.All`
   - `Sites.FullControl.All` (required for ACL ingestion; use `Sites.Read.All` if ACLs not needed)
4. **Grant admin consent**: Click **Grant admin consent for \<tenant\>** (requires tenant admin)
5. **Enable public client flow**: **Authentication** tab → **Allow public client flows** → **Yes** → Add platform **Mobile and desktop** → check `https://login.microsoftonline.com/common/oauth2/nativeclient`

> **Note**: This app is separate from the backend API app used for OBO (On-Behalf-Of) query flow. The indexer app uses Application permissions to crawl content; the backend app uses Delegated permissions to query on behalf of users.

---

## 2. Configure Managed Identity & RBAC

The search service uses its managed identity to call Azure OpenAI for embeddings. Without this, the embedding skill will fail with: *"Error authenticating to skill 'AzureOpenAIEmbeddingSkill' using managed identity set up."*

### Enable managed identity on AI Search

1. **Azure Portal** → your AI Search service → **Settings** → **Identity**
2. **System assigned** tab → **Status: On** → **Save**

### Grant AI Search access to Azure OpenAI

1. **Azure Portal** → your Azure OpenAI resource → **Access control (IAM)**
2. **+ Add** → **Add role assignment**
3. Role: **Cognitive Services OpenAI User**
4. Members → **Managed identity** → **Select members**
5. Select your **AI Search** service
6. **Review + assign**

> Role assignment propagation can take 1-2 minutes.

---

## 3. Configure Variables

1. Copy the template settings file:
   ```bash
   cp .vscode/settings.template.json .vscode/settings.json
   ```
2. Open `.vscode/settings.json` and fill in your values under `rest-client.environmentVariables` → `dev`:

| Variable | Where to find it |
|----------|-----------------|
| `searchUrl` | Azure Portal → AI Search → Overview → URL |
| `apiKey` | Azure Portal → AI Search → Settings → Keys → **Primary admin key** |
| `aoaiEndpoint` | Azure Portal → Azure OpenAI → Keys and Endpoint |
| `aoaiDeploymentName` | Azure AI Foundry portal → Deployments → your embedding deployment name |
| `aoaiModelName` | The model behind the deployment (e.g. `text-embedding-ada-002`) |
| `spoEndpoint` | Your SharePoint site URL (e.g. `https://contoso.sharepoint.com/sites/HRDocs`) |
| `spoAppId` | App registration → Overview → Application (client) ID |
| `spoAppSecret` | The client secret value from step 1 |
| `spoTenantId` | Entra ID → Overview → Tenant ID |

3. Open `setup.rest` in VS Code, then select the **"dev"** environment from the status bar (bottom-right) or via **Cmd+Shift+P** → **"Rest Client: Switch Environment"**

> **Note**: `.vscode/settings.json` is gitignored — your secrets stay local.

---

## 4. Run the Setup Steps (in order)

Execute each request in `setup.rest` sequentially using the REST Client extension (click "Send Request" above each block).

### Step 1: Create Data Source

Creates the SharePoint connection with ACL ingestion enabled.

**Connection string format:**
```
SharePointOnlineEndpoint=<site-url>;ApplicationId=<app-id>;ApplicationSecret=<client-secret>;TenantId=<tenant-id>
```

| Parameter | Value |
|-----------|-------|
| `SharePointOnlineEndpoint` | Your SharePoint site URL (e.g. `https://contoso.sharepoint.com/sites/HRDocs`) |
| `ApplicationId` | App registration → Overview → Application (client) ID |
| `ApplicationSecret` | The client secret value from step 1 |
| `TenantId` | Entra ID → Overview → Tenant ID |

**Container options:**

| `name` value | Behavior |
|---|---|
| `defaultSiteLibrary` | Index the site's default document library |
| `allSiteLibraries` | Index all document libraries in the site |
| `useQuery` | Target specific libraries via `query` parameter |

### Step 2: Create Search Index

Creates the index with the following field types:

| Field | Type | Purpose |
|-------|------|---------|
| `id` | String (key, keyword analyzer) | Document/chunk identifier |
| `parent_id` | String | Links chunk back to parent document |
| `metadata_spo_item_path` | String | SharePoint file path (required for ACL) |
| `title` | String | Document name |
| `content` | String | Chunk text (BM25 keyword search) |
| `content_vector` | Collection(Edm.Single) | 1536-dim embedding (HNSW cosine vector search) |
| `source_url` | String | SharePoint URL for citations |
| `last_modified` | DateTimeOffset | Document modification date |
| `file_type` | String | File extension |
| `UserIds` | Collection(String) | ACL - permitted user IDs |
| `GroupIds` | Collection(String) | ACL - permitted group IDs |

**Key configuration:**
- `permissionFilterOption: "enabled"` — enables automatic ACL filtering at query time
- `vectorSearch` — HNSW algorithm with cosine metric + Azure OpenAI vectorizer for query-time text-to-vector
- `semantic` — semantic ranking configuration for reranking results
- Key field (`id`) must have `"analyzer": "keyword"` when using index projections

### Step 3: Create Skillset

Creates the AI enrichment pipeline with two skills:

1. **Text Split skill** — chunks documents into ~2000-character pages with 500-character overlap
2. **Azure OpenAI Embedding skill** — generates 1536-dimensional embeddings per chunk

**Index projections** map chunk outputs + parent metadata (title, URL, ACLs) into the search index. This is how ACL fields propagate from parent documents to individual chunks.

### Step 4: Create Indexer

Ties everything together and starts the pipeline:
- Connects: data source → skillset → index
- Runs on a schedule (default: every 2 hours)
- Filters to supported file types: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.txt`
- Maps SharePoint metadata and ACL fields

---

## 5. Verify the Pipeline

### Check indexer status
```http
GET {{searchUrl}}/indexers/sharepoint-indexer/status?api-version={{apiVersion}}
api-key: {{apiKey}}
```

Look for `"status": "success"` in `lastResult`.

### Check document count
```http
GET {{searchUrl}}/indexes/sharepoint-docs-index/docs/$count?api-version={{apiVersion}}
api-key: {{apiKey}}
```

### Manually trigger a run
```http
POST {{searchUrl}}/indexers/sharepoint-indexer/run?api-version={{apiVersion}}
api-key: {{apiKey}}
```

### Test a search query
```http
POST {{searchUrl}}/indexes/sharepoint-docs-index/docs/search?api-version={{apiVersion}}
Content-Type: application/json
api-key: {{apiKey}}

{
  "search": "your search query here",
  "queryType": "semantic",
  "semanticConfiguration": "default",
  "select": "title, content, source_url",
  "top": 5,
  "vectorQueries": [
    {
      "kind": "text",
      "text": "your search query here",
      "fields": "content_vector",
      "k": 5
    }
  ]
}
```

---

## 6. Change the Indexer Schedule

Update using `PUT` with the full indexer definition. Common intervals:

| Interval | ISO 8601 Value |
|----------|---------------|
| Every 5 minutes (minimum) | `PT5M` |
| Every 30 minutes | `PT30M` |
| Every 1 hour | `PT1H` |
| Every 2 hours (default) | `PT2H` |
| Every 24 hours | `PT24H` |

---

## 7. Testing Without ACLs

The production index has `permissionFilterOption: "enabled"`, which blocks all search queries that don't include a user identity token (e.g. Foundry playground, Search Explorer, curl).

To test, **temporarily toggle the ACL filter off** using the requests in `setup.rest`:

1. Run **"Disable ACL filter"** — PUTs the index definition with `permissionFilterOption: "disabled"`
2. Test your queries in the playground / Search Explorer
3. Run **"Re-enable ACL filter"** — restores `permissionFilterOption: "enabled"`

The toggle JSON files are in `scripts/`:
- `scripts/index-acl-disabled.json`
- `scripts/index-acl-enabled.json`

> **Important**: Always re-enable before production use. With ACLs disabled, any API-key-authenticated request can see all documents regardless of SharePoint permissions.

> **Why not a separate test index?** The SharePoint data source with ACL ingestion forces `permissionFilter` fields on any target index. Creating a separate data source without ACLs requires a new OAuth device-code authorization flow.

---

## 8. Cleanup / Reset

If you need to start over, delete resources in reverse order:

```http
DELETE {{searchUrl}}/indexers/sharepoint-indexer?api-version={{apiVersion}}
api-key: {{apiKey}}

DELETE {{searchUrl}}/skillsets/sharepoint-vectorization-skillset?api-version={{apiVersion}}
api-key: {{apiKey}}

DELETE {{searchUrl}}/indexes/sharepoint-docs-index?api-version={{apiVersion}}
api-key: {{apiKey}}

DELETE {{searchUrl}}/datasources/sharepoint-datasource?api-version={{apiVersion}}
api-key: {{apiKey}}
```

---

## Important Caveats

| Item | Detail |
|------|--------|
| **Preview API** | SharePoint indexer requires `2025-11-01-preview`. Not GA — not recommended for production. |
| **ACL sync** | ACLs are captured on first ingestion only during preview. Use `/resync` or `/resetdocs` to refresh permissions. |
| **Application permissions required** | Delegated permissions do **not** support ACL ingestion. |
| **Don't mix ACLs + sensitivity labels** | Use separate indexers/indexes for each feature during preview. |
| **Managed identity RBAC** | AI Search managed identity **must** have `Cognitive Services OpenAI User` role on the Azure OpenAI resource, otherwise the embedding skill fails. |
| **Embedding model** | Must be created via Azure Portal (not Foundry portal). |
| **Key field analyzer** | Index key field **must** use `"analyzer": "keyword"` when index projections are configured. |
| **metadata_spo_item_path** | This field is **required** in the index when ACL ingestion is enabled. |
| **Semantic config field name** | API version `2025-11-01-preview` uses `prioritizedContentFields` (not `contentFields`) in semantic config. |
| **Execution order** | Index must be created **before** skillset (index projections reference the index). |

---

## Cross-Tenant Setup (Search & SharePoint in Different Tenants)

If your Azure AI Search service and SharePoint site live in **different Microsoft Entra tenants**, the indexer still works but requires specific configuration changes.

> **Reference**: [Index data from SharePoint document libraries — Step 1](https://learn.microsoft.com/en-us/azure/search/search-howto-index-sharepoint-online#step-1-optional-enable-system-assigned-managed-identity) and [Connection string format](https://learn.microsoft.com/en-us/azure/search/search-howto-index-sharepoint-online#connection-string-format)

### What changes

| Item | Same tenant | Cross-tenant |
|------|------------|--------------|
| **`TenantId` in connection string** | Optional (auto-detected via managed identity) | **Required** — must be the SharePoint tenant's ID |
| **System-assigned managed identity** | Used for tenant detection | **Skip** — managed identity cannot detect a foreign tenant |
| **Secretless auth (federated credentials)** | Supported | **Not supported** — must use a client secret |
| **App registration tenant** | Same tenant as Search service | Must be registered (or consented) **in the SharePoint tenant** |

### Step-by-step differences

1. **Skip managed identity for tenant detection** (Step 1 in the setup guide)
   - The system-assigned managed identity is only used to auto-detect the tenant where the search service is provisioned. It cannot discover a foreign tenant.
   - You still need managed identity enabled if using it for Azure OpenAI RBAC — that part is unaffected.

2. **Include `TenantId` in the connection string** (Step 4)
   ```
   SharePointOnlineEndpoint=https://contoso.sharepoint.com/sites/MySite;ApplicationId=<app-id>;ApplicationSecret=<secret>;TenantId=<sharepoint-tenant-id>
   ```
   The `TenantId` value must be the **SharePoint site's tenant**, not the search service's tenant.

3. **Use client secret authentication**
   - Secretless auth (federated credentials with managed identity) does not work cross-tenant.
   - You must configure a client secret on the Entra app registration.

4. **App registration & consent in the SharePoint tenant**
   - The Entra app needs Microsoft Graph permissions (`Files.Read.All`, `Sites.FullControl.All`) to read SharePoint content.
   - These permissions must be **consented in the tenant that owns the SharePoint site**.
   - Two approaches:
     - **Option A**: Register the app directly in the SharePoint tenant and reference it from the connection string.
     - **Option B**: Make the app registration **multi-tenant** (change from "Single tenant" to "Accounts in any organizational directory") and have a tenant admin in the SharePoint tenant grant admin consent.

5. **Update `spoTenantId`** in your `.vscode/settings.json` to the SharePoint tenant ID (not the search service tenant).

### Quick checklist

- [ ] `TenantId` included in connection string → set to SharePoint's tenant ID
- [ ] Client secret configured (not secretless)
- [ ] App registration has Graph permissions consented **in the SharePoint tenant**
- [ ] Tenant admin in the SharePoint tenant has granted admin consent
- [ ] Managed identity step skipped for tenant detection (still enabled for Azure OpenAI RBAC if needed)

---

## Architecture

### Approach 1: Indexer Pipeline

```
SharePoint Online
       │
       ▼
┌─────────────────────────────────┐
│  Azure AI Search Indexer        │  ← Crawls SharePoint via Application permissions
│  (schedule: every 2 hours)      │
├─────────────────────────────────┤
│  Skillset                       │
│  ├── Text Split (chunking)      │  ← 2000 chars/page, 500 overlap
│  └── Azure OpenAI Embedding     │  ← text-embedding-ada-002, 1536 dims
├─────────────────────────────────┤
│  Index: sharepoint-docs-index   │
│  ├── content (BM25 keyword)     │
│  ├── content_vector (HNSW)      │  ← Hybrid search: vector + keyword + semantic
│  ├── UserIds / GroupIds (ACL)   │  ← Security trimming at query time
│  └── title, source_url, etc.    │
└─────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│  FastAPI Agent Backend          │  ← Queries index via OBO token (user permissions)
│  (SearchService in search.py)   │     Hybrid search + ACL filtering
└─────────────────────────────────┘
```

### Approach 2: FoundryIQ / Agentic Retrieval

```
SharePoint Online
       │  (live query at request time — no index built)
       ▼
┌─────────────────────────────────┐
│  RemoteSharePointKnowledgeSource│  ← No site URL needed at creation time
│  (optional: KQL filter,         │     User token determines access at query time
│   resourceMetadata)             │
├─────────────────────────────────┤
│  Knowledge Base                 │
│  ├── Knowledge Source(s)        │  ← Can combine multiple sources
│  └── Azure OpenAI (gpt-4o)     │  ← Query planning & decomposition
├─────────────────────────────────┤
│  Retrieve Action                │
│  ├── api-key header             │  ← Authenticates to Azure AI Search
│  ├── x-ms-query-source-auth    │  ← User JWT (scope: search.azure.com)
│  └── Copilot Retrieval API      │  ← Requires M365 Copilot license
└─────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│  Your Application / Agent       │  ← 200 req/user/hour, 25 results/query
└─────────────────────────────────┘
```

### Approach 3: Indexed SharePoint Knowledge Source

```
SharePoint Online
       │
       ▼
┌─────────────────────────────────┐
│  IndexedSharePointKnowledgeSource│  ← One API call creates everything below
│  ├── connectionString (app creds)│
│  ├── embeddingModel (required)   │  ← text-embedding-ada-002 / 3-small / 3-large
│  └── chatCompletionModel (opt.)  │  ← gpt-4o for image verbalization
├──── Auto-Generated ─────────────┤
│  Data Source  → Skillset         │  ← Chunking + embedding pipeline
│  Index        → Indexer          │  ← Named after knowledge source
├─────────────────────────────────┤
│  Knowledge Base                  │
│  ├── Knowledge Source(s)         │  ← includeReferenceSourceData: true
│  └── Azure OpenAI (gpt-4o)      │  ← Query planning & answer synthesis
├─────────────────────────────────┤
│  Retrieve Action                 │
│  └── api-key header only         │  ← No user token needed (data is indexed)
└─────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│  Your Application / Agent        │  ← Standard search limits, no Copilot license
└─────────────────────────────────┘
```
