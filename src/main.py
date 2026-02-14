"""FastAPI application entry point for the SharePoint Document Q&A Agent."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.config import Settings, get_settings
from src.logging_config import setup_logging
from src.models.document import SourceReference
from src.models.errors import ErrorCode, ErrorResponse
from src.models.user import User
from src.services.audit import AuditEntry, log_query
from src.services.rate_limiter import RateLimiter, RateLimitExceededError

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    version: str
    timestamp: str


class ChatRequest(BaseModel):
    """Request body for POST /chat matching openapi.yaml ChatRequest."""

    message: str = Field(..., description="User's question text")
    conversation_id: str | None = Field(None, description="Existing conversation ID to continue")


class AgentMessage(BaseModel):
    """Agent response message matching openapi.yaml AgentMessage."""

    id: str
    role: str = "assistant"
    content: str
    source_references: list[SourceReference] = Field(default_factory=list)
    timestamp: str


class ChatResponse(BaseModel):
    """Response body for POST /chat matching openapi.yaml ChatResponse."""

    conversation_id: str
    message: AgentMessage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler for startup/shutdown."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("SharePoint Q&A Agent starting up")

    # Store settings on app state for access in endpoints
    app.state.settings = settings

    yield

    logger.info("SharePoint Q&A Agent shutting down")


async def get_current_user(request: Request) -> User:
    """FastAPI dependency: extract and validate Bearer token.

    Returns a User from JWT claims. Raises 401 if token is missing or invalid.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error=ErrorCode.UNAUTHORIZED,
                message="Missing or invalid Authorization header. Bearer token required.",
            ).model_dump(),
        )

    # Token validation will be fully implemented in US2 (T027-T028).
    # For now, extract token and create a placeholder user for testing.
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error=ErrorCode.UNAUTHORIZED,
                message="Empty bearer token.",
            ).model_dump(),
        )

    # Placeholder: in US2, this will validate JWT and extract real claims
    try:
        from src.services.auth import AuthService

        settings: Settings = request.app.state.settings
        auth_service = AuthService(settings)
        user = await auth_service.validate_token(auth_header)
        return user
    except ImportError:
        # Auth service not yet implemented — stub for US1
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error=ErrorCode.UNAUTHORIZED,
                message="Authentication service not available.",
            ).model_dump(),
        ) from None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error=ErrorCode.UNAUTHORIZED,
                message=str(e),
            ).model_dump(),
        ) from None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="SharePoint Document Q&A Agent API",
        version="0.1.0",
        description="REST API for the SharePoint Document Q&A Agent",
        lifespan=lifespan,
    )

    # CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Per-user rate limiter (US4)
    rate_limiter = RateLimiter(
        max_requests=20,
        window_seconds=60,
    )
    application.state.rate_limiter = rate_limiter

    @application.get("/")
    async def root() -> dict:
        """Root endpoint with API info."""
        return {
            "name": "SharePoint Document Q&A Agent",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/health",
        }

    @application.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Health check endpoint used by Container Apps probes."""
        return HealthResponse(
            status="healthy",
            version="0.1.0",
            timestamp=datetime.now(tz=UTC).isoformat(),
        )

    @application.post("/chat", response_model=ChatResponse)
    async def send_message(
        body: ChatRequest,
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> ChatResponse:
        """Send a message to the SharePoint Q&A agent.

        Validates input, searches documents, generates a grounded answer,
        and returns with source citations.
        """
        start_time = time.monotonic()
        settings: Settings = request.app.state.settings

        # T043: Rate limit check — before any processing
        try:
            rate_limiter_inst: RateLimiter = request.app.state.rate_limiter
            await rate_limiter_inst.check_rate_limit(current_user.user_id)
        except RateLimitExceededError as exc:
            raise HTTPException(
                status_code=429,
                detail=ErrorResponse(
                    error=ErrorCode.RATE_LIMIT_EXCEEDED,
                    message=f"Rate limit exceeded. Try again in {exc.retry_after:.0f} seconds.",
                ).model_dump(),
            ) from exc

        # T023: Input validation — reject if message exceeds max length
        if len(body.message) > settings.max_input_length:
            return JSONResponse(  # type: ignore[return-value]
                status_code=400,
                content=ErrorResponse(
                    error=ErrorCode.INPUT_TOO_LONG,
                    message=f"Message exceeds maximum length of {settings.max_input_length} characters.",
                ).model_dump(),
            )

        if not body.message.strip():
            return JSONResponse(  # type: ignore[return-value]
                status_code=400,
                content=ErrorResponse(
                    error=ErrorCode.INVALID_REQUEST,
                    message="Message cannot be empty.",
                ).model_dump(),
            )

        # Determine conversation_id
        conversation_id = body.conversation_id or str(uuid.uuid4())

        try:
            # Import agent and search service
            from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
            from azure.identity import DefaultAzureCredential

            from src.agents.sharepoint_qa import SharePointQAAgent
            from src.services.search import IndexerSearchService, SearchBackend

            credential = DefaultAzureCredential()

            # ── Search backend factory ──────────────────────────────────
            search_service: SearchBackend

            if settings.search_approach == "indexer":
                # Approach 1: direct Azure AI Search index query
                # Use API key when available, otherwise DefaultAzureCredential
                if settings.azure_search_api_key:
                    from azure.core.credentials import AzureKeyCredential

                    search_cred: Any = AzureKeyCredential(settings.azure_search_api_key)
                else:
                    search_cred = credential

                search_service = IndexerSearchService(
                    endpoint=settings.azure_search_endpoint,
                    index_name=settings.azure_search_index_name,
                    credential=search_cred,
                )
            else:
                # Approaches 2 & 3: Knowledge Base retrieve API
                from src.services.kb_search import KnowledgeBaseSearchService

                token_provider = None
                if settings.search_approach == "foundryiq":
                    # OBO token provider for FoundryIQ (delegated user identity)
                    from src.services.auth import AuthService

                    auth_service = AuthService(settings)
                    auth_header = request.headers.get("Authorization", "")
                    user_token = auth_header.removeprefix("Bearer ").strip()

                    async def _search_token_provider() -> str:
                        return await auth_service.get_search_token(user_token)

                    token_provider = _search_token_provider

                search_service = KnowledgeBaseSearchService(
                    endpoint=settings.azure_search_endpoint,
                    api_version=settings.azure_search_api_version,
                    knowledge_base_name=settings.knowledge_base_name,
                    knowledge_source_name=settings.knowledge_source_name,
                    approach=settings.search_approach,
                    api_key=settings.azure_search_api_key,
                    token_provider=token_provider,
                )

            model_client = AzureOpenAIChatCompletionClient(
                azure_deployment=settings.azure_openai_deployment,
                azure_endpoint=settings.azure_openai_endpoint,
                api_version=settings.azure_openai_api_version,
                **(
                    {"api_key": settings.azure_openai_api_key}
                    if settings.azure_openai_api_key
                    else {
                        "azure_ad_token_provider": lambda: (
                            credential.get_token(
                                "https://cognitiveservices.azure.com/.default"
                            ).token
                        )
                    }
                ),
                model=settings.azure_openai_deployment,
            )

            agent = SharePointQAAgent(
                search_service=search_service,
                model_client=model_client,
            )

            # TODO: In US3, load conversation history from Cosmos DB
            result = await agent.answer_question(
                question=body.message,
                user_id=current_user.user_id,
                group_ids=[],  # TODO: In US2, extract from Graph token
            )

            latency_ms = int((time.monotonic() - start_time) * 1000)

            # T024: Audit logging
            source_urls = [sr.document_url for sr in result.get("source_references", [])]
            audit_entry = AuditEntry(
                user_id=current_user.user_id,
                conversation_id=conversation_id,
                query=body.message,
                documents_accessed=source_urls,
                response_summary=result["content"][:500],
                latency_ms=latency_ms,
                was_refused=result.get("was_refused", False),
            )
            await log_query(audit_entry)

            # Log performance warning
            if latency_ms > 5000:
                logger.warning(
                    "Response exceeded 5s target",
                    extra={"latency_ms": latency_ms, "user_id": current_user.user_id},
                )
            else:
                logger.info(
                    "Chat response completed",
                    extra={"latency_ms": latency_ms, "user_id": current_user.user_id},
                )

            agent_msg = AgentMessage(
                id=str(uuid.uuid4()),
                role="assistant",
                content=result["content"],
                source_references=[sr.model_dump() for sr in result.get("source_references", [])],
                timestamp=datetime.now(tz=UTC).isoformat(),
            )

            return ChatResponse(
                conversation_id=conversation_id,
                message=agent_msg,
            )

        except HTTPException:
            raise
        except Exception:
            logger.exception("Chat endpoint error")
            return JSONResponse(  # type: ignore[return-value]
                status_code=503,
                content=ErrorResponse(
                    error=ErrorCode.SERVICE_UNAVAILABLE,
                    message="The service is temporarily unavailable. Please try again later.",
                ).model_dump(),
            )

    # --- Conversation Endpoints (US3) ---

    class ConversationSummary(BaseModel):
        """Summary of a conversation for listing."""

        id: str
        title: str
        last_active_at: str
        status: str
        preview: str = ""

    class ConversationListResponse(BaseModel):
        """Response for GET /conversations."""

        conversations: list[ConversationSummary]
        total: int
        limit: int
        offset: int

    class MessageItem(BaseModel):
        """Message in a conversation detail."""

        id: str
        role: str
        content: str
        source_references: list[dict] = Field(default_factory=list)
        timestamp: str

    class ConversationDetail(BaseModel):
        """Full conversation detail for GET /conversations/{id}."""

        id: str
        user_id: str
        title: str
        messages: list[MessageItem]
        status: str
        created_at: str
        last_active_at: str

    @application.get("/conversations", response_model=ConversationListResponse)
    async def list_conversations(
        request: Request,
        current_user: User = Depends(get_current_user),
        status: str = "active",
        limit: int = 20,
        offset: int = 0,
    ) -> ConversationListResponse:
        """List user's conversations, ordered by most recent first."""
        settings: Settings = request.app.state.settings

        try:
            from azure.cosmos.aio import CosmosClient as AsyncCosmosClient
            from azure.identity.aio import DefaultAzureCredential as AsyncCredential

            from src.services.conversation import ConversationService

            credential = AsyncCredential()
            cosmos_client = AsyncCosmosClient(settings.cosmos_endpoint, credential=credential)
            service = ConversationService(
                client=cosmos_client,
                database=settings.cosmos_database,
                container=settings.cosmos_container,
            )

            convs = await service.list_conversations(
                user_id=current_user.user_id,
                status=status,
                limit=min(limit, 50),
                offset=max(offset, 0),
            )

            summaries = [
                ConversationSummary(
                    id=c.id,
                    title=c.title,
                    last_active_at=c.last_active_at.isoformat()
                    if hasattr(c.last_active_at, "isoformat")
                    else str(c.last_active_at),
                    status=c.status,
                    preview=c.messages[-1].content[:200] if c.messages else "",
                )
                for c in convs
            ]

            return ConversationListResponse(
                conversations=summaries,
                total=len(summaries),
                limit=limit,
                offset=offset,
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Error listing conversations")
            return JSONResponse(  # type: ignore[return-value]
                status_code=503,
                content=ErrorResponse(
                    error=ErrorCode.SERVICE_UNAVAILABLE,
                    message="Unable to retrieve conversations.",
                ).model_dump(),
            )

    @application.get("/conversations/{conversation_id}", response_model=ConversationDetail)
    async def get_conversation(
        conversation_id: str,
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> ConversationDetail:
        """Get a conversation with full message history."""
        settings: Settings = request.app.state.settings

        try:
            from azure.cosmos.aio import CosmosClient as AsyncCosmosClient
            from azure.identity.aio import DefaultAzureCredential as AsyncCredential

            from src.services.conversation import ConversationService

            credential = AsyncCredential()
            cosmos_client = AsyncCosmosClient(settings.cosmos_endpoint, credential=credential)
            service = ConversationService(
                client=cosmos_client,
                database=settings.cosmos_database,
                container=settings.cosmos_container,
            )

            conv = await service.get_conversation(
                conversation_id=conversation_id,
                user_id=current_user.user_id,
            )

            if conv is None:
                return JSONResponse(  # type: ignore[return-value]
                    status_code=404,
                    content=ErrorResponse(
                        error=ErrorCode.NOT_FOUND,
                        message="Conversation not found.",
                    ).model_dump(),
                )

            messages = [
                MessageItem(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    source_references=[sr.model_dump() for sr in m.source_references],
                    timestamp=m.timestamp.isoformat()
                    if hasattr(m.timestamp, "isoformat")
                    else str(m.timestamp),
                )
                for m in conv.messages
            ]

            return ConversationDetail(
                id=conv.id,
                user_id=conv.user_id,
                title=conv.title,
                messages=messages,
                status=conv.status,
                created_at=conv.created_at.isoformat()
                if hasattr(conv.created_at, "isoformat")
                else str(conv.created_at),
                last_active_at=conv.last_active_at.isoformat()
                if hasattr(conv.last_active_at, "isoformat")
                else str(conv.last_active_at),
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Error getting conversation")
            return JSONResponse(  # type: ignore[return-value]
                status_code=503,
                content=ErrorResponse(
                    error=ErrorCode.SERVICE_UNAVAILABLE,
                    message="Unable to retrieve conversation.",
                ).model_dump(),
            )

    return application


app = create_app()
