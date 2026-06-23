"""Rumi data-grounded chatbot for the "Patients Like Me" dashboard.

A tool-using :class:`rumi.Dervish` (``DashboardChatbot``) that answers questions
about the on-screen profile + per-drug-class predictions + similar-patient
evidence + literature. It cites every figure, shows what patients reported
(never recommends), and refuses safety/dosing questions. The route layer owns
the runtime safety gate (:class:`agentic_health_hackathon.shared_decision.safety.SafetyFilter`).

Public entry point: :func:`agentic_health_hackathon.chatbot.runtime.answer`.
"""

from __future__ import annotations
