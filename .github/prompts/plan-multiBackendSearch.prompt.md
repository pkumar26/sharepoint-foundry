## Plan: Multi-Backend Search with Configurable Approach

The agent currently hardcodes Approach 1 (direct index query via `SearchClient` SDK). The goal is to let operators select between all 3 search approaches via a configuration setting, while keeping the agent layer unchanged. The key architectural insight: all 3 approaches can share the same `search_documents() → list[SearchResult]` contract — only the search service implementation differs.

**Steps**

1. **Add config settings** in [src/config.py](src/config.py): Add a `search_approach` field (literal `"indexer" | "foundryiq" | "indexed_sharepoint"`, default `"indexer"`), plus `azure_search_api_key`, `azure_search_api_version` (default `"2025-11-01-preview"`), `knowledge_base_name`, and `knowledge_source_name` — all optional with defaults so existing deployments don't break.

2. **Define a search protocol** in [src/services/search.py](src/services/search.py): Extract an `ABC` or `Protocol` class (`SearchBackend`) with a single method `search_documents(query, user_id, group_ids, top) → list[SearchResult]`. Rename the current `SearchService` to `IndexerSearchService` implementing this protocol.

3. **Create `KnowledgeBaseSearchService`** in a new file `src/services/kb_search.py`: Implements the same protocol for both Approach 2 (FoundryIQ) and Approach 3 (Indexed SharePoint KS). It calls `POST knowledgebases('{name}')/retrieve` via `requests`, maps the KB response (`response[].content[].text` → `content`, `references[].webUrl` → `source_url`, `references[].rerankerScore` → `relevance_score`) into `SearchResult` models. Constructor takes a `kind` parameter (`"remoteSharePoint"` vs `"indexedSharePoint"`) and an optional `user_token` (required for FoundryIQ only).

4. **Add OBO token exchange for FoundryIQ** in [src/services/auth.py](src/services/auth.py): Add a method `get_search_token(user_assertion)` that exchanges the user's bearer token for a token scoped to `https://search.azure.com/.default` via OBO flow.

5. **Wire up the factory** in [src/main.py](src/main.py#L218-L240): In the `/chat` endpoint, use `settings.search_approach` to instantiate the correct backend:
   - `"indexer"` → `IndexerSearchService` (current behavior)
   - `"foundryiq"` → `KnowledgeBaseSearchService(kind="remoteSharePoint", user_token=search_token)`
   - `"indexed_sharepoint"` → `KnowledgeBaseSearchService(kind="indexedSharePoint")`

6. **Update the agent type hint** in [src/agents/sharepoint_qa.py](src/agents/sharepoint_qa.py): Change the `search_service` parameter type from `SearchService` to `SearchBackend` protocol. Also fix the latent `site_name` bug (referenced at lines ~145 and ~156 but not defined on any model).

7. **Add `SEARCH_APPROACH` to Bicep** in [infra/main.bicep](infra/main.bicep): Add a new env var `SEARCH_APPROACH` with the selected approach and any additional KB-related env vars (`KNOWLEDGE_BASE_NAME`, `KNOWLEDGE_SOURCE_NAME`, `AZURE_SEARCH_API_KEY`).

8. **Update tests** in [tests/unit/test_search.py](tests/unit/test_search.py) and add `tests/unit/test_kb_search.py`: Unit tests for the new KB search service with mocked HTTP responses.

**Verification**

- Run `pytest tests/unit/` — all existing tests should pass (Approach 1 unchanged)
- Set `SEARCH_APPROACH=indexed_sharepoint` with KB env vars → verify the agent calls the KB retrieve API instead
- Set `SEARCH_APPROACH=foundryiq` → verify user token is exchanged and passed in `x-ms-query-source-authorization` header
- `pyright src/` — no type errors

**Decisions**

- **Protocol over ABC**: Use `typing.Protocol` for `SearchBackend` so existing `SearchService` doesn't need to explicitly inherit — duck typing is sufficient
- **Combined KB service**: One class `KnowledgeBaseSearchService` handles both Approach 2 and 3 since the retrieve API is identical — only the `kind` and auth headers differ
- **Config-driven, not UI dropdown**: The "dropdown" is an environment variable (`SEARCH_APPROACH`) — operators set it at deployment time. A runtime UI toggle would require architectural changes to the frontend
