"""``shared-decision-chat`` — an offline REPL for adversarial testing of the chatbot.

Drives the same ``runtime.answer`` + ``SafetyFilter`` path the route uses, so you
can throw "tell me what to take" / "is this safe" / "what dose" at it from a
terminal and watch the gate fire. Needs ``OPENROUTER_API_KEY`` set (Rumi is
OpenRouter-only). Not part of the import surface — purely a convenience.
"""

from __future__ import annotations

import uuid

import typer

app = typer.Typer(add_completion=False, help="Offline REPL for the dashboard chatbot.")


@app.command()
def chat(
    conditions: str = typer.Option("pots,dysautonomia", help="Comma-separated condition keys."),
    severity: str = typer.Option("mobility_limited", help="Functional-severity key."),
) -> None:
    """Interactive chat loop against the data-grounded dashboard chatbot."""
    from agentic_health_hackathon.chatbot.runtime import answer
    from agentic_health_hackathon.shared_decision.safety import SafetyFilter

    conds = [c.strip() for c in conditions.split(",") if c.strip()]
    profile = {"conditions": conds, "severity": severity or None}
    conv_id = f"cli-{uuid.uuid4().hex[:12]}"
    flt = SafetyFilter()
    typer.echo(f"Profile: {conds} severity={severity}  (conversation {conv_id})")
    typer.echo("Type a question (Ctrl-C to quit).")
    while True:
        try:
            msg = typer.prompt("you")
        except (KeyboardInterrupt, EOFError):
            typer.echo("\nbye")
            raise typer.Exit() from None
        result = answer(msg, conv_id, profile, [])
        gated = flt.apply(result["raw_text"], had_tool_calls=result["had_tool_calls"])
        typer.echo(f"\nassistant{' [BLOCKED]' if gated.blocked else ''}: {gated.text}")
        for d in gated.disclaimers:
            typer.echo(f"  · {d}")
        typer.echo("")


if __name__ == "__main__":
    app()
