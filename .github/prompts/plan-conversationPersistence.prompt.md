## Plan: Conversation Persistence with Cosmos DB

Wire up the existing `ConversationService` and `Conversation` model to make multi-turn conversations real. The model, service, Cosmos CRUD, and frontend sidebar are already built — the gap is that `POST /chat` never reads or writes to Cosmos. This plan covers: Cosmos DB provisioning + RBAC, backend persistence in the chat endpoint, LLM-generated titles, Cosmos client lifecycle optimization, and frontend integration for loading history.

**Steps**

1. **Provision Cosmos DB database + container** — Run Azure CLI to create database `sharepoint-agent` and container `conversations` with partition key `/user_id` and TTL enabled (`--default-ttl -1`) in the existing `cosmos-xc4icdh2gdp6` account in `rg-ai-landing-zone-eastus2`

2. **Assign Cosmos RBAC roles** — Grant `Cosmos DB Built-in Data Contributor` (role `00000000-0000-0000-0000-000000000002`) to:
   - Container App Managed Identity (`80f72e51-b892-4640-bf80-78397395fc03`)
   - Developer identity (for local dev via `DefaultAzureCredential`)
   - Scope to `/dbs/sharepoint-agent/colls/conversations`

3. **Optimize Cosmos client lifecycle** in [src/main.py](src/main.py) — Move `AsyncCosmosClient` + `ConversationService` creation from per-request to `app.state` in the `lifespan()` function. Initialize once, reuse across requests. Add a `_get_conversation_service()` FastAPI dependency

4. **Wire persistence into `POST /chat`** in [src/main.py](src/main.py):
   - If `body.conversation_id` is provided: load conversation via `ConversationService.get_conversation()`, extract `conversation_history` from stored messages
   - If no `conversation_id`: create new conversation via `ConversationService.create_conversation()`
   - Pass `conversation_history` to `agent.answer_question()`
   - After getting agent response: save user message + assistant message (with `source_references`) via `ConversationService.add_message()` (two calls)
   - Return the real persisted `conversation_id` in `ChatResponse`

5. **Add LLM-generated conversation titles** — Create a `generate_title()` utility function in [src/services/conversation.py](src/services/conversation.py) using the `openai` SDK (`AsyncAzureOpenAI`). Call it after the first exchange (when creating a new conversation), requesting a 5-10 word title from `gpt-4o` with `max_tokens=30, temperature=0.3`. Update the conversation title asynchronously (fire-and-forget via `asyncio.create_task` so it doesn't block the response). Add `title` field to `ChatResponse` so the frontend can update the sidebar with the real title

6. **Update frontend** ([static/js/conversations.js](static/js/conversations.js), [static/js/chat.js](static/js/chat.js)) — Update `onNewMessage()` to use `title` from the chat response when available instead of truncating the user message. No other frontend changes needed — the sidebar already calls `GET /conversations`, loads history, and sends `conversation_id` back

7. **Add `COSMOS_ENDPOINT` to Container App env vars** — Update the container app configuration with `az containerapp update --set-env-vars COSMOS_ENDPOINT=https://cosmos-xc4icdh2gdp6.documents.azure.com:443/`

8. **Tests** — Update [tests/integration/test_conversation_persistence.py](tests/integration/test_conversation_persistence.py) to cover the new flow: create conversation on first message, load history on follow-up, title generation. Add happy-path contract tests for `GET /conversations` in [tests/contract/test_conversations_api.py](tests/contract/test_conversations_api.py)

**Verification**
- Local: Start server, send first message → verify Cosmos document created with generated title. Send follow-up → verify message appended and history used in response. Hit `GET /conversations` → verify list. Click sidebar item → verify history loads
- Azure: Redeploy, confirm Cosmos RBAC works with Managed Identity (no 403s), verify multi-turn in the web UI
- Run `pytest tests/integration/test_conversation_persistence.py` and `pytest tests/contract/test_conversations_api.py`

**Decisions**
- **Cosmos auth**: Managed Identity (RBAC) via `DefaultAzureCredential` — no keys
- **Title generation**: LLM-generated via `openai` SDK (lightweight, no AutoGen overhead), fire-and-forget async task
- **Cosmos client**: Singleton on `app.state` (not per-request) for connection reuse
- **Scope**: Full stack — backend + frontend sidebar wiring
