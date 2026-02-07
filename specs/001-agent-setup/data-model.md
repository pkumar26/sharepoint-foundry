# Data Model: SharePoint Document Q&A Agent

**Feature**: `001-agent-setup` | **Date**: 2026-02-07

## Entities

### User

Represents an authenticated person interacting with the agent. Populated from Entra ID claims after OBO authentication.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `user_id` | `str` | Entra ID object ID (GUID) | Required, UUID format |
| `display_name` | `str` | User's display name from Entra | Required, max 256 chars |
| `email` | `str` | User's email address | Required, valid email format |
| `tenant_id` | `str` | Entra ID tenant ID | Required, UUID format |

**Source**: Extracted from JWT claims (`oid`, `name`, `preferred_username`, `tid`) of the incoming Entra token.

**Notes**: Not persisted as a separate entity. Derived on each request from the authentication token. Used to scope Cosmos DB queries and AI Search security trimming.

---

### Conversation

A threaded exchange between one user and the agent. Persisted as a single document in Azure Cosmos DB.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `id` | `str` | Unique conversation ID (UUID) | Required, auto-generated |
| `user_id` | `str` | Owner's Entra object ID | Required, UUID format (partition key) |
| `title` | `str` | Auto-generated summary of first message | Max 200 chars |
| `messages` | `list[Message]` | Ordered list of conversation turns | Required, min 1 |
| `status` | `str` | `"active"` or `"archived"` | Required, enum |
| `created_at` | `datetime` | UTC timestamp of creation | Required, ISO 8601 |
| `last_active_at` | `datetime` | UTC timestamp of last message | Required, ISO 8601 |
| `ttl` | `int` | Time-to-live in seconds (90 days = 7,776,000) | Set automatically |

**Partition key**: `/user_id`  
**Cosmos DB container**: `conversations`  
**TTL behaviour**: Cosmos DB auto-deletes the document after `ttl` seconds from last write (`_ts`). The 90-day window resets on every new message (upsert).

**State transitions**:
```
[created] → active → archived (manual or on 90-day TTL expiry)
                  ↑
                  └── reactivated (user continues conversation)
```

---

### Message

A single turn in a conversation. Embedded within the `Conversation.messages` array (not a separate Cosmos DB document).

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `id` | `str` | Unique message ID (UUID) | Required, auto-generated |
| `role` | `str` | `"user"` or `"assistant"` | Required, enum |
| `content` | `str` | Message text content | Required, max 4,000 chars (user), max 10,000 chars (assistant) |
| `source_references` | `list[SourceReference]` | Citations (assistant messages only) | Optional, empty for user messages |
| `timestamp` | `datetime` | UTC timestamp of message creation | Required, ISO 8601 |

**Notes**: Embedded in `Conversation.messages[]` rather than stored as separate documents. This avoids cross-document queries and keeps all conversation data in a single Cosmos DB point read.

---

### SourceReference

A citation linking an agent answer back to a specific SharePoint document. Embedded within `Message.source_references`.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `document_title` | `str` | Title of the source document | Required, max 500 chars |
| `document_url` | `str` | SharePoint URL to the document | Required, valid URL |
| `site_name` | `str` | SharePoint site display name | Required |
| `excerpt` | `str` | Relevant snippet from the document | Optional, max 500 chars |
| `relevance_score` | `float` | Search relevance score (0.0–1.0) | Optional |

---

### SearchResult (transient — not persisted)

Represents a document chunk retrieved from Azure AI Search. Used internally during query processing. Not stored in Cosmos DB.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `chunk_id` | `str` | Azure AI Search document ID | Required |
| `document_title` | `str` | Original document title | Required |
| `content` | `str` | Text chunk content | Required |
| `source_url` | `str` | SharePoint URL | Required |
| `site_name` | `str` | SharePoint site name | Required |
| `file_type` | `str` | File format (docx, pdf, etc.) | Required |
| `last_modified` | `datetime` | Document last-modified date | Required |
| `relevance_score` | `float` | Hybrid search score | Required |

---

### AuditEntry (write-only log — not queried by agent)

An audit trail record capturing each user interaction for compliance. Written to structured logs (JSON) and optionally to a dedicated Cosmos DB container.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `id` | `str` | Unique audit entry ID | Required, auto-generated |
| `user_id` | `str` | User's Entra object ID | Required |
| `conversation_id` | `str` | Conversation context | Required |
| `query` | `str` | User's question text | Required |
| `documents_accessed` | `list[str]` | SharePoint URLs of documents searched | Required |
| `response_summary` | `str` | First 500 chars of agent response | Required |
| `timestamp` | `datetime` | UTC timestamp | Required, ISO 8601 |
| `latency_ms` | `int` | End-to-end response time | Required |
| `was_refused` | `bool` | Whether agent refused to answer | Required |

---

## Entity Relationships

```
User (1) ──────── (many) Conversation
                            │
                            ├── (many) Message
                            │            │
                            │            └── (many) SourceReference
                            │
                            └── status: active | archived

SearchResult ← transient, produced by AI Search, consumed by agent
AuditEntry ← write-only, one per user query
```

## Cosmos DB Container Design

| Container | Partition Key | TTL | Purpose |
|-----------|--------------|-----|---------|
| `conversations` | `/user_id` | 7,776,000 (90 days) | Conversation + embedded messages |
| `audit` (optional) | `/user_id` | 31,536,000 (365 days) | Audit trail (if not only in structured logs) |

## Azure AI Search Index Schema

| Field | Type | Searchable | Filterable | Retrievable |
|-------|------|-----------|-----------|-------------|
| `id` | Edm.String (key) | No | Yes | Yes |
| `title` | Edm.String | Yes | No | Yes |
| `content` | Edm.String | Yes | No | Yes |
| `content_vector` | Collection(Edm.Single) | Yes (vector) | No | No |
| `source_url` | Edm.String | No | Yes | Yes |
| `site_name` | Edm.String | No | Yes | Yes |
| `file_type` | Edm.String | No | Yes | Yes |
| `last_modified` | Edm.DateTimeOffset | No | Yes | Yes |
| `UserIds` | Collection(Edm.String) | No | Yes (permission) | No |
| `GroupIds` | Collection(Edm.String) | No | Yes (permission) | No |

**Vector config**: HNSW algorithm, cosine metric, 1536 dimensions (text-embedding-3-small).  
**Semantic config**: Title field = `title`, Content field = `content`.  
**Permission filter**: Enabled. Security trimming via Entra token at query time.
