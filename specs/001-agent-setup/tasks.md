# Tasks: SharePoint Document Q&A Agent

**Input**: Design documents from `/specs/001-agent-setup/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Included — Constitution Principle VI mandates test-driven quality.

**Organization**: Tasks grouped by user story (US1–US4) per priority order from spec.md.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Exact file paths included in every task description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependency management, and basic structure

- [x] T001 Create project directory structure per plan.md (`src/agents/`, `src/models/`, `src/services/`, `tests/unit/`, `tests/integration/`, `tests/contract/`, `tests/fixtures/`)
- [x] T002 Create pyproject.toml with all dependencies (`autogen-agentchat==0.7.5`, `autogen-ext[openai,azure]==0.7.5`, `azure-identity`, `azure-search-documents`, `azure-cosmos`, `msal`, `fastapi`, `uvicorn`, `pydantic`) and dev dependencies (`pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `pyright`, `httpx`)
- [x] T003 [P] Create .env.example with all required environment variables per quickstart.md
- [x] T004 [P] Configure ruff.toml (linting + formatting rules) and pyproject.toml pyright settings (strict mode)
- [x] T005 [P] Create Dockerfile per research.md (Python 3.11, uvicorn entrypoint, port 8000)
- [x] T006 [P] Create `src/__init__.py`, `src/agents/__init__.py`, `src/models/__init__.py`, `src/services/__init__.py`, `tests/__init__.py` package init files

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T007 Implement environment-based configuration loader in `src/config.py` — load all env vars from quickstart.md (Azure OpenAI, AI Search, Cosmos DB, Entra ID, app settings) with validation using pydantic `BaseSettings`
- [x] T008 [P] Implement structured JSON logging setup in `src/logging_config.py` — configure Python `logging` with JSON formatter, log levels from config (FR-015)
- [x] T009 [P] Create User model in `src/models/user.py` — Pydantic model with `user_id`, `display_name`, `email`, `tenant_id` fields per data-model.md; class method to construct from JWT claims (`oid`, `name`, `preferred_username`, `tid`)
- [x] T010 [P] Create SourceReference model in `src/models/document.py` — Pydantic model with `document_title`, `document_url`, `site_name`, `excerpt`, `relevance_score` per data-model.md
- [x] T011 [P] Create SearchResult model in `src/models/document.py` — Pydantic model with `chunk_id`, `document_title`, `content`, `source_url`, `site_name`, `file_type`, `last_modified`, `relevance_score` per data-model.md
- [x] T012 [P] Create ErrorResponse model in `src/models/errors.py` — Pydantic model matching `ErrorResponse` schema from openapi.yaml (error code enum + message)
- [x] T013 Create FastAPI application skeleton in `src/main.py` — app factory with lifespan handler, CORS middleware, health endpoint (`GET /health` returning `HealthResponse`), structured logging integration
- [x] T014 Create AuditEntry model and audit service in `src/services/audit.py` — Pydantic model per data-model.md; async `log_query()` function that writes structured JSON audit log entries (FR-016); include unit test in `tests/unit/test_audit.py`
- [x] T015 Unit test for config loader in `tests/unit/test_config.py`
- [x] T016 [P] Unit test for User model JWT parsing in `tests/unit/test_user_model.py`

**Checkpoint**: Foundation ready — config, logging, base models, FastAPI skeleton, audit. User story implementation can now begin.

---

## Phase 3: User Story 1 — Ask a Question About SharePoint Documents (Priority: P1) 🎯 MVP

**Goal**: An authenticated user asks a natural-language question and receives a grounded answer with source citations from SharePoint documents. The agent refuses out-of-scope questions.

**Independent Test**: Send a question whose answer exists in a known SharePoint document → verify the response matches document content with source references. Send an out-of-scope question → verify refusal.

### Tests for User Story 1

- [x] T017 [P] [US1] Contract test for `POST /chat` in `tests/contract/test_chat_api.py` — verify request/response shapes match openapi.yaml `ChatRequest`/`ChatResponse` schemas, 200/400/503 status codes
- [x] T018 [P] [US1] Unit test for search service in `tests/unit/test_search.py` — mock `SearchClient`, verify hybrid query construction (vector + keyword + semantic), verify security trimming filter applied, verify `SearchResult` mapping
- [x] T019 [P] [US1] Integration test for Q&A flow in `tests/integration/test_qa_flow.py` — end-to-end test: question → search → agent → grounded answer with citations; out-of-scope question → refusal

### Implementation for User Story 1

- [x] T020 [US1] Implement Azure AI Search service in `src/services/search.py` — `SearchService` class with `search_documents(query, user_id, group_ids)` method; hybrid search (vector HNSW + BM25 + semantic ranking via `VectorizedQuery`); ACL security trimming with `UserIds`/`GroupIds` filter; return `list[SearchResult]`; authenticate with `DefaultAzureCredential`
- [x] T021 [US1] Implement SharePoint Q&A agent in `src/agents/sharepoint_qa.py` — `AssistantAgent` from `autogen_agentchat` with system prompt enforcing document-grounded answers only (FR-003, FR-009); register `search_documents` as `FunctionTool`; use `AzureOpenAIChatCompletionClient` with `AzureTokenProvider`; format responses with source citations (FR-004)
- [x] T022 [US1] Implement `POST /chat` endpoint in `src/main.py` — accept `ChatRequest`, validate input length ≤4,000 chars (FR-012), invoke agent, return `ChatResponse` with `AgentMessage` + `SourceReference` list; handle `400`/`503` errors per openapi.yaml
- [x] T023 [US1] Add input validation and error handling for chat endpoint in `src/main.py` — reject inputs exceeding max length with `input_too_long` error, handle SharePoint unavailability with `service_unavailable` error and retry logic (FR-012, FR-014)
- [x] T024 [US1] Integrate audit logging into chat flow in `src/main.py` — call `audit.log_query()` after each agent response with user_id, conversation_id, documents_accessed, response_summary, latency_ms, was_refused (FR-016)

**Checkpoint**: User Story 1 complete — agent answers grounded questions with citations, refuses out-of-scope, validates input, logs audit trail. Testable independently with stubbed auth.

---

## Phase 4: User Story 2 — Authenticate via Microsoft Entra ID (Priority: P2)

**Goal**: Users must sign in through Entra ID before the agent accepts input. The agent only permits access to documents the user is authorised to view in SharePoint (OBO flow).

**Independent Test**: Send request without auth token → verify 401 rejection. Send request with valid token → verify agent responds. Send request with expired token → verify re-auth prompt.

### Tests for User Story 2

- [x] T025 [P] [US2] Unit test for auth service in `tests/unit/test_auth.py` — mock MSAL `ConfidentialClientApplication`, verify OBO token exchange, verify JWT claim extraction, verify expired token detection
- [x] T026 [P] [US2] Integration test for auth flow in `tests/integration/test_auth_flow.py` — unauthenticated request → 401; valid token → 200; expired token → 401 with `token_expired` error; insufficient permissions → documents filtered from results

### Implementation for User Story 2

- [x] T027 [US2] Implement Entra ID auth service in `src/services/auth.py` — `AuthService` class with: (1) `validate_token(authorization_header)` to verify JWT signature, `aud`, `iss`, `exp` claims; (2) `get_graph_token(user_assertion)` using MSAL `ConfidentialClientApplication.acquire_token_on_behalf_of()` with scopes `Sites.Read.All`, `Files.Read.All`; (3) `extract_user(token)` returning `User` model from JWT claims; (4) `SerializableTokenCache` partitioned per user
- [x] T028 [US2] Create FastAPI auth dependency in `src/main.py` — `get_current_user()` dependency that extracts Bearer token, calls `auth.validate_token()`, returns `User`; raise `HTTPException(401)` with `unauthorized` or `token_expired` error codes (FR-001, FR-013)
- [x] T029 [US2] Wire auth dependency into all protected endpoints in `src/main.py` — add `current_user: User = Depends(get_current_user)` to `/chat`, `/conversations`, `/conversations/{id}` (FR-001)
- [x] T030 [US2] Pass user permissions to search service in `src/main.py` — extract user_id and group_ids from Graph token, pass to `search_documents()` for ACL security trimming (FR-008)

**Checkpoint**: User Story 2 complete — all endpoints require Entra auth, OBO flow exchanges user token for Graph token, document-level permissions enforced via security trimming. Testable independently.

---

## Phase 5: User Story 3 — Continue a Previous Conversation (Priority: P3)

**Goal**: Returning users see their previous conversations, can continue them with follow-up questions, and the agent maintains conversational context. Conversations are isolated.

**Independent Test**: Have a multi-turn conversation, close the session, return and verify the agent recalls prior context. Start a new conversation and verify no context bleed.

### Tests for User Story 3

- [x] T031 [P] [US3] Unit test for conversation service in `tests/unit/test_conversation.py` — mock Cosmos DB client, verify create/get/update/list operations, verify TTL reset on upsert, verify partition key scoping by user_id
- [x] T032 [P] [US3] Contract test for `GET /conversations` and `GET /conversations/{id}` in `tests/contract/test_conversations_api.py` — verify response shapes match openapi.yaml `ConversationListResponse`/`ConversationDetail` schemas, pagination params, 401/404 status codes
- [x] T033 [P] [US3] Integration test for conversation persistence in `tests/integration/test_conversation_persistence.py` — multi-turn conversation → close → resume → verify agent resolves references to prior context; verify conversation isolation (no context bleed)

### Implementation for User Story 3

- [x] T034 [US3] Create Conversation and Message models in `src/models/conversation.py` — Pydantic models per data-model.md: `Conversation` (id, user_id, title, messages, status, created_at, last_active_at, ttl), `Message` (id, role, content, source_references, timestamp); methods for Cosmos DB serialization/deserialization
- [x] T035 [US3] Implement conversation persistence service in `src/services/conversation.py` — `ConversationService` class with Cosmos DB client (`DefaultAzureCredential`); methods: `create_conversation()`, `get_conversation(id, user_id)`, `add_message(conversation_id, message)` with TTL reset via upsert, `list_conversations(user_id, status, limit, offset)` with partition-scoped queries; auto-create database/container on init (FR-005, FR-006)
- [x] T036 [US3] Integrate conversation context into agent in `src/agents/sharepoint_qa.py` — load agent state via `load_state()` from stored conversation; use `BufferedChatCompletionContext` for sliding-window history; save state via `save_state()` after each response (FR-007)
- [x] T037 [US3] Update `POST /chat` to handle `conversation_id` in `src/main.py` — if `conversation_id` provided, load existing conversation and agent state; if omitted, create new conversation; append user message + agent response; save conversation after agent responds
- [x] T038 [US3] Implement `GET /conversations` endpoint in `src/main.py` — query user's conversations from Cosmos DB via `ConversationService.list_conversations()`, support `status`, `limit`, `offset` query params, return `ConversationListResponse` per openapi.yaml
- [x] T039 [US3] Implement `GET /conversations/{conversation_id}` endpoint in `src/main.py` — load full conversation with messages from Cosmos DB, verify ownership (user_id matches), return `ConversationDetail` or 404 per openapi.yaml

**Checkpoint**: User Story 3 complete — conversations persisted in Cosmos DB, follow-up questions use prior context, conversation isolation enforced, conversation listing with pagination. Testable independently.

---

## Phase 6: User Story 4 — Receive Fast Responses (Priority: P4)

**Goal**: Agent responses arrive within acceptable time windows (≤5s single-doc, ≤10s multi-doc, ≤15s at 50 concurrent users). Rate limiting prevents abuse.

**Independent Test**: Measure end-to-end latency under normal load. Exceed 20 queries/minute from one user → verify rate limit response.

### Tests for User Story 4

- [x] T040 [P] [US4] Unit test for rate limiter in `tests/unit/test_rate_limiter.py` — verify 20 queries/minute window, verify sliding window reset, verify per-user isolation, verify concurrent access safety with asyncio
- [x] T041 [P] [US4] Integration test for rate limiting in `tests/integration/test_rate_limiting.py` — send 21 requests in 1 minute → verify 21st returns 429 with `rate_limit_exceeded` error; verify different users have independent limits

### Implementation for User Story 4

- [x] T042 [US4] Implement per-user rate limiter in `src/services/rate_limiter.py` — `RateLimiter` class with sliding-window algorithm using `asyncio.Lock` + `collections.deque` of timestamps per user_id; `check_rate_limit(user_id)` returns remaining count or raises; configurable limit from config (FR-017)
- [x] T043 [US4] Integrate rate limiter into chat endpoint in `src/main.py` — call `rate_limiter.check_rate_limit(user_id)` before agent invocation; return 429 with `rate_limit_exceeded` error and helpful message when exceeded; do NOT discard conversation context on rate limit (FR-017)
- [x] T044 [US4] Add response timing and performance logging in `src/main.py` — measure end-to-end latency per request, log to structured JSON logs, include `latency_ms` in audit entry; log warning if response exceeds 5s threshold
- [x] T044b [US4] Integration test for concurrent user isolation in `tests/integration/test_concurrent_users.py` — send 10 parallel requests with different user tokens, verify no identity or conversation cross-contamination (FR-010)

**Checkpoint**: User Story 4 complete — rate limiting enforced at 20 queries/min/user, response timing measured and logged, performance targets achievable. Testable independently.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T045 [P] Create SharePoint mock fixtures in `tests/fixtures/sharepoint_responses.json` — realistic Graph API and AI Search response payloads for test reuse
- [x] T046 [P] Create sample test documents in `tests/fixtures/sample_documents/` — small DOCX, PDF, and TXT files for integration test scenarios
- [x] T047 [P] Add `__all__` exports and module docstrings to all `__init__.py` files in `src/`
- [x] T048 Run full lint and type check pass — `ruff check src/ tests/` + `ruff format --check src/ tests/` + `pyright src/` — fix all issues
- [x] T049 Run full test suite — `pytest --cov=src --cov-report=term-missing` — verify ≥80% line coverage per module
- [x] T050 Validate quickstart.md — follow the quickstart steps end-to-end (install, configure, run, test) and verify they complete successfully

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — core Q&A functionality
- **US2 (Phase 4)**: Depends on Phase 2 — can run in parallel with US1
- **US3 (Phase 5)**: Depends on Phase 2 — can run in parallel with US1/US2
- **US4 (Phase 6)**: Depends on Phase 2 — can run in parallel with US1/US2/US3
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: No dependency on other stories — standalone after foundational
- **US2 (P2)**: No dependency on US1 — auth is independent; integration with US1 is wiring auth dependency into existing endpoints
- **US3 (P3)**: Lightly depends on US1 (chat endpoint exists to add conversation_id handling) — but can be built with stubbed chat
- **US4 (P4)**: No dependency on other stories — rate limiter is independent middleware

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Core implementation before integration with other stories
- Story complete before moving to next priority (in sequential mode)

### Parallel Opportunities

- **Phase 1**: T003, T004, T005, T006 can all run in parallel
- **Phase 2**: T008, T009, T010, T011, T012 can all run in parallel; T015, T016 after their targets exist
- **Phase 3–6**: All user story test tasks marked [P] can run in parallel within each story
- **Across stories**: US1, US2, US3, US4 can all proceed in parallel once Phase 2 completes (different files, independent concerns)

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests in parallel:
Task T017: "Contract test for POST /chat in tests/contract/test_chat_api.py"
Task T018: "Unit test for search service in tests/unit/test_search.py"
Task T019: "Integration test for Q&A flow in tests/integration/test_qa_flow.py"

# Then implement sequentially (service → agent → endpoint):
Task T020: "Implement search service in src/services/search.py"
Task T021: "Implement Q&A agent in src/agents/sharepoint_qa.py"
Task T022: "Implement POST /chat endpoint in src/main.py"
Task T023: "Add input validation and error handling"
Task T024: "Integrate audit logging into chat flow"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test US1 independently — agent answers grounded questions with citations
5. Deploy/demo if ready — this is the minimum viable product

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → Test independently → Deploy/Demo (**MVP!**)
3. Add US2 → Test independently → Deploy/Demo (now secured)
4. Add US3 → Test independently → Deploy/Demo (now persistent)
5. Add US4 → Test independently → Deploy/Demo (now performant)
6. Polish → Final quality pass

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (core Q&A)
   - Developer B: User Story 2 (auth)
   - Developer C: User Story 3 (conversation persistence)
   - Developer D: User Story 4 (rate limiting + performance)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable after Phase 2
- Tests are written FIRST and must FAIL before implementation (TDD per constitution Principle VI)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- All 9 runtime dependencies justified in research.md — no additions allowed without constitution review
