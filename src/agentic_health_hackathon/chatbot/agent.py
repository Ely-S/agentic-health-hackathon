"""DashboardChatbot — the tool-using Dervish for the "Patients Like Me" dashboard.

A :class:`rumi.Dervish` subclass whose single Voice carries the grounding/safety
SYSTEM_PROMPT and whose tools (registered in ``tools.py``) read the dashboard's
query layer. ``agent_id`` is supplied per conversation by the runtime, giving free
multi-turn memory via Rumi's tablet replay.

CRITICAL: ``from . import tools`` runs at module load so the ``@tool`` functions
register in Rumi's global registry BEFORE the Dervish is constructed — otherwise
the agent would build with zero tools (Rumi snapshots the registry at __init__).
"""

from __future__ import annotations

from pathlib import Path

from rumi import Dervish, HeartConfig

from . import tools  # noqa: F401  — registers @tool fns before the Dervish is built
from .brain.builder import build_voice
from .brain.prompts import SYSTEM_PROMPT

_BRAIN_DIR = Path(__file__).parent / "brain"


class DashboardChatbot(Dervish):
    """Data-grounded, tool-using assistant docked in the dashboard.

    One Voice (model + sampling from ``brain/brain.json``, instructions =
    SYSTEM_PROMPT). The grounding contract lives in the prompt; the runtime
    SafetyFilter (owned by the route) is the deterministic second gate.
    """

    heart_config = HeartConfig(voices=[build_voice(_BRAIN_DIR, SYSTEM_PROMPT)])
