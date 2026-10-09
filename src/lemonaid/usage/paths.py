"""Where usage data lives under the lemonaid state directory."""

import os
from pathlib import Path


def usage_dir() -> Path:
    """`LEMONAID_STATE_DIR` (default `~/.local/state/lemonaid`) plus `usage/`."""
    override = os.environ.get("LEMONAID_STATE_DIR")
    base = (
        Path(override).expanduser() if override else Path.home() / ".local" / "state" / "lemonaid"
    )

    return base / "usage"
