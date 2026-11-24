"""A Codex lemon's context window, which its hooks don't report but its rollout does."""

import json
from pathlib import Path

_TAIL = 256 * 1024  # a `token_count` event follows every model request, so the end has one


def read(rollout: str) -> int:
    """The window the newest `token_count` event in the rollout's tail reports; 0 if none."""
    try:
        with Path(rollout).open("rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - _TAIL))
            lines = f.read().splitlines()
    except OSError:
        return 0

    for line in reversed(lines):
        if b'"token_count"' not in line:
            continue

        try:
            payload = json.loads(line).get("payload")
        except json.JSONDecodeError:  # the first line of the tail may be cut mid-record
            continue

        window = (payload.get("info") or {}).get("model_context_window")
        if isinstance(window, int) and window > 0:
            return window

    return 0
