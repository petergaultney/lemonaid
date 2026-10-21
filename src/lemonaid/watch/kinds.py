"""The identifiers a user's notes (see notes.py) attach to: one per kind of watcher event.

Only kinds a detector actually tags are listed, so a note can't name an event that never
carries it.
"""

from ..brief import store

# How a watched lemon came to be watched: a child link, a `### Lemons` row, or an orphan scan.
ORIGINS = {
    "child": "your child",
    "watched": "a lemon your ### Lemons table lists that isn't your child",
    "orphan": "a brief no live lemon owns (watch briefs --orphans)",
}

_PROBLEMS = {
    "exited": "its harness exited",
    "gone": "its tmux session, directory or attachment is gone",
    "deaf": "a message sent to it would not be read",
}


def status(origin: str, state: str) -> str:
    return f"{origin}.{state or 'none'}"


def needs(origin: str) -> str:
    return f"{origin}.needs"


def problem(origin: str, kind: str) -> str:
    return f"{origin}.{kind}"


def _described() -> dict[str, str]:
    found: dict[str, str] = {}
    for origin, who in ORIGINS.items():
        for state in (*store.STATES, ""):
            found[status(origin, state)] = (
                f"Status of {who} became {state}" if state else f"Status of {who} was cleared"
            )
        found[needs(origin)] = f"{who.capitalize()} has a new or changed Needs ask"
        for kind, what in _PROBLEMS.items():
            found[problem(origin, kind)] = f"{who.capitalize()}: {what}"
    return found


KINDS: dict[str, str] = _described()
