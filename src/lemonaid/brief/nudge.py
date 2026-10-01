"""The line that reminds a lemon whose brief waits on Peter to keep its Status true.

A lemon Peter has answered tends to stay `blocked` while it works on the answer,
so his to-do list keeps asks he has already answered. The line rides on
something the lemon receives anyway: an answer from the brief view, a message
queued into a Codex thread, or the first tool call of a Claude turn.
"""

from . import now, questions, status

WAITING_ON_PETER = frozenset({"blocked", "alert", "merge"})
_ANSWERS = "This answers"


def _quoted(labels: list[str]) -> str:
    return ", ".join(f'"{label}"' for label in labels)


def note(text: str) -> str:
    """The reminder for a brief whose Status waits on Peter, or ""."""
    parts = status.split(text)
    if parts.status not in WAITING_ON_PETER:
        return ""

    found = now.parse(parts.now)
    on = _quoted(questions.labels(found.needs)) or f"nothing under {found.needs_label}"
    return (
        f"Your brief's Status is `{parts.status}`, on: {on}. If this turn answers or changes "
        "any of these, update Status before ending; otherwise ignore this."
    )


def after_answer(text: str, label: str) -> str:
    """The line to append to an answer to *label*, or "" when the Status doesn't wait on Peter."""
    parts = status.split(text)
    if parts.status not in WAITING_ON_PETER:
        return ""

    found = now.parse(parts.now)
    rest = _quoted(questions.labels(found.needs, without=label))
    on = f"on: {rest}" if rest else f"with nothing else under {found.needs_label}"
    return (
        f'{_ANSWERS} "{label}". Your brief says `{parts.status}` {on}. '
        "Update Status if that changes."
    )


def carries_note(message: str) -> bool:
    return f"\n\n{_ANSWERS} " in message
