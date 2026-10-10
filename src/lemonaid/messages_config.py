"""The `[messages]` table: which harnesses `tell` resumes when they won't read a message, and how often."""

import sys
from dataclasses import dataclass

from .inbox import snooze_time

_HARNESSES = frozenset({"claude", "codex"})
_AUTORESUME = {"on": _HARNESSES, "off": frozenset(), "claude": {"claude"}, "codex": {"codex"}}


@dataclass(frozen=True)
class MessagesConfig:
    autoresume: frozenset[str] = _HARNESSES
    autoresume_max: int = 3  # starts of one lemon allowed within autoresume_window
    autoresume_window: float = 20 * 60.0


def _warn(key: str, expected: str) -> None:
    print(f"Warning: [messages] {key} must be {expected}", file=sys.stderr)


def _autoresume(raw: object) -> frozenset[str]:
    if raw is True or raw is False:
        raw = "on" if raw else "off"
    if raw not in _AUTORESUME:
        _warn("autoresume", f"one of {', '.join(_AUTORESUME)}")
        return MessagesConfig.autoresume

    return frozenset(_AUTORESUME[str(raw)])


def _max(raw: object) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        _warn("autoresume_max", "a whole number of at least 1")
        return MessagesConfig.autoresume_max

    return raw


def _window(raw: object) -> float:
    seconds = snooze_time.parse_duration(raw) if isinstance(raw, str) else None
    if seconds is None:
        _warn("autoresume_window", 'a duration such as "20m" or "1h"')
        return MessagesConfig.autoresume_window

    return seconds


def parse(data: dict) -> MessagesConfig:
    return MessagesConfig(
        autoresume=_autoresume(data.get("autoresume", "on")),
        autoresume_max=_max(data.get("autoresume_max", MessagesConfig.autoresume_max)),
        autoresume_window=_window(data.get("autoresume_window", "20m")),
    )
