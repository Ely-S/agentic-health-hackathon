"""SafetyFilter — the runtime output gate on every chatbot reply.

``SafetyPolicy`` (in ``models.py``) is a static annotation; for a health chatbot
the contract must be ENFORCED at runtime, on every LLM output, regardless of what
the prompt asked the model to do. ``SafetyFilter.apply(text, *, had_tool_calls)``:

  - BLOCKS prescriptive verbs ("you should (take|start|stop)", "I recommend",
    "the best treatment for you"), safety claims ("is safe", "safe for you",
    "no side effects"), and dosing (``\\d+\\s?mg``) → rewrites to a safe pivot and
    sets ``blocked=True``.
  - ALWAYS appends the :class:`SafetyPolicy` disclaimer.
  - FLAGS a bare percentage when ``had_tool_calls`` is False (a number that did
    not come from a grounded tool call is ungrounded — surface it as a caveat).

Pure python, no LLM, no I/O — deterministic and unit-testable offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agentic_health_hackathon.shared_decision.models import SafetyPolicy

# Prescriptive language — the bot reports a signal, it never directs the user.
_PRESCRIPTIVE = [
    re.compile(
        r"\byou\s+should\s+(?:take|start|stop|try|use|begin|switch|increase|decrease)\b", re.I
    ),
    re.compile(r"\bi\s+(?:recommend|suggest|advise)\b", re.I),
    re.compile(r"\b(?:i'?d|i\s+would)\s+recommend\b", re.I),
    re.compile(r"\bthe\s+best\s+treatment\s+for\s+you\b", re.I),
    re.compile(r"\byou\s+(?:ought\s+to|need\s+to|must)\s+(?:take|start|stop|try|use)\b", re.I),
]
# Safety claims — the bot cannot assess safety.
_SAFETY_CLAIM = [
    re.compile(r"\bis\s+safe\b", re.I),
    re.compile(r"\bsafe\s+for\s+you\b", re.I),
    re.compile(r"\bperfectly\s+safe\b", re.I),
    re.compile(r"\bno\s+side\s+effects?\b", re.I),
    re.compile(r"\bwell[\s-]tolerated\b", re.I),
]
# Dosing — any milligram figure (or explicit dose language).
_DOSING = [
    re.compile(r"\b\d+(?:\.\d+)?\s?mg\b", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s?(?:mcg|micrograms?|milligrams?)\b", re.I),
    re.compile(r"\b(?:start|titrate|dose)\s+at\b", re.I),
]
# A bare percentage (for the ungrounded-number flag).
_BARE_PCT = re.compile(r"\b\d+(?:\.\d+)?\s?%")

_PIVOT = (
    "I can't tell you what to take, what's safe for you, or any dosing — I only show what "
    "patients reported, as decision-support input for a conversation with your doctor. "
    "I can instead show you the reported signal for a drug class (the % positive with its "
    "confidence interval and sample size, plus what patients said). Which class would you like?"
)


@dataclass
class SafetyResult:
    """The gated output: possibly-rewritten text + disclaimers + flags."""

    text: str
    blocked: bool = False
    disclaimers: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


class SafetyFilter:
    """Deterministic runtime gate enforcing the SafetyPolicy on chatbot output."""

    def __init__(self, policy: SafetyPolicy | None = None) -> None:
        self._policy = policy or SafetyPolicy()

    def apply(self, text: str, *, had_tool_calls: bool) -> SafetyResult:
        text = text or ""
        disclaimers = [self._policy.disclaimer]
        flags: list[str] = []

        triggered = (
            any(rx.search(text) for rx in _PRESCRIPTIVE)
            or any(rx.search(text) for rx in _SAFETY_CLAIM)
            or any(rx.search(text) for rx in _DOSING)
        )

        if triggered:
            # Rewrite wholesale to the safe pivot — we do NOT try to surgically
            # excise a dose or a "you should" from otherwise-fine prose, because a
            # partial scrub can leave the prescriptive intent intact. Replace the
            # whole reply with the pivot and flag the block.
            return SafetyResult(
                text=_PIVOT,
                blocked=True,
                disclaimers=disclaimers,
                flags=["blocked: prescriptive/safety/dosing content removed"],
            )

        # Ungrounded-number flag: a bare % when no tool call produced data means
        # the figure is not traceable to the dataset. Surface it as a caveat
        # rather than blocking (the number may still be fine in prose form).
        if not had_tool_calls and _BARE_PCT.search(text):
            flags.append("ungrounded-figure: a percentage appeared without a grounded data call")
            disclaimers.append(
                "Note: a figure above was not drawn from a live data lookup — treat it as "
                "illustrative, not a dataset result."
            )

        return SafetyResult(text=text, blocked=False, disclaimers=disclaimers, flags=flags)
