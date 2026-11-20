"""Current usage of each provider's limit windows, as {window name: Sample}."""

import json
import os
import tempfile
from collections import abc
from dataclasses import dataclass
from pathlib import Path

from ..codex import limits
from . import paths

_CLAUDE_WINDOW_MINUTES = {"five_hour": 300, "seven_day": 10080}


@dataclass(frozen=True)
class Sample:
    used_percent: float
    resets_at: int  # epoch seconds
    window_minutes: int


def claude_limits_file() -> Path:
    return paths.usage_dir() / "claude-rate-limits.json"


def save_claude_limits(statusline_data: dict) -> None:
    """Keep the `rate_limits` Claude Code passes to its statusLine command, if it passed any."""
    limits = statusline_data.get("rate_limits")
    if not limits:
        return

    target = claude_limits_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=target.parent, delete=False) as tmp:
        json.dump(limits, tmp)
    os.replace(tmp.name, target)


def claude_samples(limits_file: Path) -> dict[str, Sample]:
    if not limits_file.exists():
        return {}

    return {
        f"claude {window}": Sample(
            w["used_percentage"], int(w["resets_at"]), _CLAUDE_WINDOW_MINUTES[window]
        )
        for window, w in json.loads(limits_file.read_text()).items()
        if window in _CLAUDE_WINDOW_MINUTES
        and isinstance(w, dict)
        and "used_percentage" in w
        and "resets_at" in w
    }


def codex_samples(windows: abc.Iterable[limits.Window]) -> dict[str, Sample]:
    return {
        f"codex {w.name} ({w.minutes}min)": Sample(w.used_percent, w.resets_at, w.minutes)
        for w in windows
    }


def current_samples() -> dict[str, Sample]:
    return {
        **claude_samples(claude_limits_file()),
        **codex_samples(limits.windows()),
    }
