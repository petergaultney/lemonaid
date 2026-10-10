"""The `[messages]` config table: which harnesses `tell` resumes when they won't read a message."""

import sys
from dataclasses import dataclass

_HARNESSES = frozenset({"claude", "codex"})
_AUTORESUME = {"on": _HARNESSES, "off": frozenset(), "claude": {"claude"}, "codex": {"codex"}}


@dataclass(frozen=True)
class MessagesConfig:
    autoresume: frozenset[str] = _HARNESSES


def parse(data: dict) -> MessagesConfig:
    raw = data.get("autoresume", "on")
    if raw is True or raw is False:
        raw = "on" if raw else "off"
    if raw not in _AUTORESUME:
        print(
            f"Warning: [messages] autoresume must be one of {', '.join(_AUTORESUME)}",
            file=sys.stderr,
        )
        return MessagesConfig()

    return MessagesConfig(autoresume=frozenset(_AUTORESUME[raw]))
