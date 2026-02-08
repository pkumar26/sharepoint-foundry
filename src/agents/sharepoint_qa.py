"""SharePoint Q&A Agent using Microsoft Agent Framework (autogen-agentchat)."""

from __future__ import annotations

import logging
from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

from src.models.document import SearchResult, SourceReference
from src.services.search import SearchService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a SharePoint Document Q&A Agent. Your purpose is to answer questions \
about documents stored in SharePoint.

RULES:
1. ONLY answer questions using information found in the provided SharePoint documents.
2. If the search results do not contain relevant information to answer the question, \
respond with: "I couldn't find relevant information in the available SharePoint documents \
to answer your question."
3. NEVER make up information. Every claim must be grounded in document content.
4. Always cite your sources by referencing the document title and location.
5. If asked about topics unrelated to SharePoint documents (weather, general knowledge, \
personal opinions, etc.), respond with: "I can only answer questions about documents \
stored in SharePoint. Please ask a question related to your organization's documents."
6. Be concise and direct in your answers.
7. When multiple documents contain relevant information, synthesize the answer and \
cite all relevant sources.
"""


class SharePointQAAgent:
    """Agent that answers questions grounded in SharePoint document content.

    Uses Azure AI Search for document retrieval and Azure OpenAI for response
    generation via the Microsoft Agent Framework (autogen-agentchat).
    """

    def __init__(
        self,
        search_service: SearchService,
        model_client: AzureOpenAIChatCompletionClient,
    ) -> None:
        self._search_service = search_service
        self._model_client = model_client
        self._agent: AssistantAgent | None = None

    def _create_agent(self, search_context: str) -> AssistantAgent:
        """Create an AssistantAgent with search context in the system prompt."""
        system_message = (
            f"{SYSTEM_PROMPT}\n\n"
            f"DOCUMENT CONTEXT:\n{search_context}\n\n"
            "Use the above document context to answer the user's question. "
            "Cite sources by document title."
        )
        return AssistantAgent(
            name="sharepoint_qa_agent",
            model_client=self._model_client,
            system_message=system_message,
        )

    async def answer_question(
        self,
        question: str,
        user_id: str,
        group_ids: list[str],
        conversation_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Answer a user question using SharePoint documents.

        Args:
            question: The user's natural-language question.
            user_id: Authenticated user's Entra object ID.
            group_ids: User's Entra group IDs for security trimming.
            conversation_history: Previous messages for context continuity.

        Returns:
            Dict with 'content' (answer text), 'source_references' (citations),
            and 'was_refused' (whether the agent refused to answer).
        """
        # Step 1: Search for relevant documents
        search_results = await self._search_service.search_documents(
            query=question,
            user_id=user_id,
            group_ids=group_ids,
        )

        # Step 2: Build context from search results
        search_context = self._format_search_context(search_results)

        # Step 3: Create agent with context
        agent = self._create_agent(search_context)

        # Step 4: Build message with optional conversation history
        messages: list[TextMessage] = []
        if conversation_history:
            for msg in conversation_history:
                messages.append(
                    TextMessage(
                        content=msg["content"],
                        source=msg.get("role", "user"),
                    )
                )

        # Add current question
        messages.append(TextMessage(content=question, source="user"))

        # Step 5: Get agent response
        try:
            response = await agent.on_messages(messages, cancellation_token=None)
            content = response.chat_message.content if response.chat_message else ""
            if not isinstance(content, str):
                content = str(content)
        except Exception:
            logger.exception("Agent failed to generate response")
            raise

        # Step 6: Build source references from search results
        source_references = self._build_source_references(search_results)

        # Step 7: Detect if agent refused
        was_refused = self._is_refusal(content)

        return {
            "content": content,
            "source_references": source_references,
            "was_refused": was_refused,
        }

    def _format_search_context(self, results: list[SearchResult]) -> str:
        """Format search results as context text for the agent."""
        if not results:
            return "No documents found matching the query."

        parts: list[str] = []
        for i, r in enumerate(results, 1):
            parts.append(
                f"[Document {i}]\n"
                f"Title: {r.document_title}\n"
                f"Source: {r.source_url}\n"
                f"Site: {r.site_name}\n"
                f"Content:\n{r.content}\n"
            )
        return "\n---\n".join(parts)

    def _build_source_references(self, results: list[SearchResult]) -> list[SourceReference]:
        """Convert search results to source reference citations."""
        return [
            SourceReference(
                document_title=r.document_title,
                document_url=r.source_url,
                site_name=r.site_name,
                excerpt=r.content[:500] if r.content else None,
                relevance_score=r.relevance_score,
            )
            for r in results
        ]

    def _is_refusal(self, content: str) -> bool:
        """Check if the agent's response is a refusal to answer."""
        refusal_phrases = [
            "I can only answer questions about documents stored in SharePoint",
            "I couldn't find relevant information",
            "not able to answer",
            "cannot answer",
            "outside my scope",
        ]
        content_lower = content.lower()
        return any(phrase.lower() in content_lower for phrase in refusal_phrases)
