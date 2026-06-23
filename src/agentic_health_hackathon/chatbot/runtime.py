"""Ephemeral Rumi runtime for the DashboardChatbot.

``get_world()`` caches one :class:`rumi.World` per process (Rumi's history is
on-disk; one World holds the openrouter client + tablet root). If ``RUMI_DATA_DIR``
is unset we point it at an OS-temp dir so the chat history is ephemeral/transient
and never pollutes the repo.

``answer(...)`` builds a ``DashboardChatbot(world=get_world(), agent_id=conversation_id)``
— ``conversation_id`` as ``agent_id`` gives free multi-turn memory via Rumi's
tablet replay — and runs one ``whirl(build_message(...))``. It does NOT run the
SafetyFilter; the route owns that output gate.
"""

from __future__ import annotations

import os
import tempfile
from typing import TYPE_CHECKING

from rumi import World
from rumi.ideas.types import ToolRequestIdea, ToolResultIdea

from .brain.prompts import build_message

if TYPE_CHECKING:
    from rumi import Dervish

_WORLD: World | None = None


def get_world() -> World:
    """One cached :class:`rumi.World` per process, with ephemeral on-disk history.

    Points ``RUMI_DATA_DIR`` at a throwaway temp dir unless the caller pinned one.
    The OpenRouter client is built lazily inside the World on first LLM call, so
    importing/constructing this needs no API key.
    """
    global _WORLD
    if _WORLD is None:
        if not os.environ.get("RUMI_DATA_DIR"):
            os.environ["RUMI_DATA_DIR"] = tempfile.mkdtemp(prefix="dashboard-chat-")
        _WORLD = World()
    return _WORLD


def _had_tool_calls(agent: Dervish) -> bool:
    """True if any tool was requested/returned during this conversation.

    Inspects the agent's idea history for ToolRequest/ToolResult ideas (the
    authoritative signal). Falls back to a heuristic if the history shape ever
    changes under us: no ideas inspected → assume False.
    """
    try:
        for idea in agent.ideas:
            if isinstance(idea, (ToolRequestIdea, ToolResultIdea)):
                return True
    except Exception:
        return False
    return False


def answer(
    message: str,
    conversation_id: str,
    profile: dict,
    predictions: list[dict],
) -> dict:
    """Run one chatbot turn. Returns ``{raw_text, had_tool_calls, sources}``.

    ``conversation_id`` is the Rumi ``agent_id`` → multi-turn memory via tablet
    replay. ``sources`` collects any post_ids cited by tool results (best-effort).
    """
    world = get_world()
    agent = DashboardChatbot(world=world, agent_id=conversation_id)
    final = agent.whirl(build_message(message, profile, predictions))
    raw_text = getattr(final, "content", "") or ""
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)

    had = _had_tool_calls(agent)

    sources: list[str] = []
    try:
        for idea in agent.ideas:
            if isinstance(idea, ToolResultIdea):
                content = getattr(idea, "content", "") or ""
                for token in str(content).split():
                    if token.startswith("post_id="):
                        pid = token.split("=", 1)[1].rstrip(")\"',.")
                        if pid and pid not in sources:
                            sources.append(pid)
    except Exception:
        pass

    return {"raw_text": raw_text, "had_tool_calls": had, "sources": sources}


# Imported AFTER get_world so a bare `from .runtime import answer` doesn't drag the
# Dervish (and its tool registration) in before the caller wants it. The Dervish
# itself imports tools.py at its module top, preserving @tool registration order.
from .agent import DashboardChatbot  # noqa: E402
