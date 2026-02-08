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

## Architecture

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
