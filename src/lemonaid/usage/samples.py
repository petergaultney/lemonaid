"""Current usage of each provider's limit windows, as {window name: Sample}."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import paths

_CODEX_FILES_SCANNED = 5
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


def _last_codex_limits(rollout: Path) -> tuple[str, dict] | None:
    found = None
    for line in rollout.read_text(errors="replace").splitlines():
        if '"rate_limits"' not in line:
            continue

        try:
            event = json.loads(line)
        except ValueError:
            continue

        limits = (event.get("payload") or {}).get("rate_limits")
        if limits:
            found = (event["timestamp"], limits)

    return found


def codex_samples(sessions: Path) -> dict[str, Sample]:
    """Newest rate_limits event among the most recently modified rollouts."""
    rollouts = sorted(sessions.glob("*/*/*/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime)
    newest = max(
        filter(None, (_last_codex_limits(r) for r in rollouts[-_CODEX_FILES_SCANNED:])),
        default=None,
    )
    if not newest:
        return {}

    return {
        f"codex {name} ({w['window_minutes']}min)": Sample(
            w["used_percent"], int(w["resets_at"]), int(w["window_minutes"])
        )
        for name in ("primary", "secondary")
        if (w := newest[1].get(name))
    }


def current_samples() -> dict[str, Sample]:
    return {
        **claude_samples(claude_limits_file()),
        **codex_samples(Path.home() / ".codex" / "sessions"),
    }
