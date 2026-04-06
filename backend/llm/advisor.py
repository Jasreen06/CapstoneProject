"""
advisor.py
==========
LangChain + Groq AI advisor for DockWise AI v2.
"""

from __future__ import annotations
import logging
from typing import Any

from config import GROQ_API_KEY
from llm.knowledge import SYSTEM_PROMPT, MARITIME_KNOWLEDGE

logger = logging.getLogger(__name__)

_MAX_TURNS = 8  # keep last 8 exchanges in history


def _get_llm():
    try:
        from langchain_groq import ChatGroq
    except ImportError:
        raise RuntimeError("langchain-groq not installed. Run: pip install langchain-groq")

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in environment")

    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=GROQ_API_KEY,
        temperature=0.3,
        max_tokens=1024,
    )


async def get_ai_response(
    user_message: str,
    context: str = "",
    chat_history: list[dict[str, str]] | None = None,
) -> str:
    """
    Send a message to the AI advisor with maritime context.

    Args:
        user_message: The user's question.
        context: Live data context string (from knowledge.build_context).
        chat_history: List of {"role": "user"|"assistant", "content": "..."} dicts.

    Returns:
        The AI's response as a string.
    """
    if chat_history is None:
        chat_history = []

    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

    llm = _get_llm()

    full_input = f"{MARITIME_KNOWLEDGE}\n\n{context}\n\nUser question: {user_message}"

    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    # Add history (last N turns)
    recent_history = chat_history[-(2 * _MAX_TURNS):]
    for msg in recent_history:
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg.get("role") == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=full_input))

    import asyncio
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, llm.invoke, messages)
    return response.content.strip()


async def answer_chat(
    message: str,
    port_context: str | None = None,
    vessel_context: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> str:
    """
    High-level chat function for the API endpoint.
    Combines port and vessel contexts.
    """
    context_parts = []
    if port_context:
        context_parts.append(port_context)
    if vessel_context:
        context_parts.append(vessel_context)

    combined_context = "\n\n".join(context_parts)

    return await get_ai_response(
        user_message=message,
        context=combined_context,
        chat_history=history or [],
    )
