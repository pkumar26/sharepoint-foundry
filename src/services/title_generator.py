"""Generate concise conversation titles using Azure OpenAI."""

from __future__ import annotations

import logging

from openai import AsyncAzureOpenAI

from src.config import Settings

logger = logging.getLogger(__name__)

_TITLE_PROMPT = (
    "Generate a short, descriptive title (max 8 words) for a conversation "
    "that starts with the following exchange. Return ONLY the title text, "
    "no quotes, no punctuation at the end.\n\n"
    "User: {user_message}\n\n"
    "Assistant: {assistant_message}"
)


async def generate_title(
    user_message: str,
    assistant_message: str,
    settings: Settings,
) -> str:
    """Call Azure OpenAI to produce a short conversation title.

    Args:
        user_message: The first user message in the conversation.
        assistant_message: The agent's first reply.
        settings: Application settings (contains OpenAI config).

    Returns:
        A concise title string (≤ 200 chars).
    """
    client = AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        api_key=settings.azure_openai_api_key or None,
    )

    try:
        response = await client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[
                {
                    "role": "user",
                    "content": _TITLE_PROMPT.format(
                        user_message=user_message[:500],
                        assistant_message=assistant_message[:500],
                    ),
                },
            ],
            max_tokens=30,
            temperature=0.3,
        )
        title = (response.choices[0].message.content or "").strip().strip('"').strip("'")
        return title[:200] if title else "New conversation"
    except Exception:
        logger.warning("Title generation LLM call failed", exc_info=True)
        # Fallback: use first ~50 chars of user message
        return user_message[:50].strip() or "New conversation"
    finally:
        await client.close()
