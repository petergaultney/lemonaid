"""Where lemonaid keeps what it knows about docs: the index, the delivery log, and each
session's mode and context window."""

import os
from pathlib import Path


def state_dir() -> Path:
    return Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid").expanduser()


def deliveries() -> Path:
    return state_dir() / "doc-deliveries.jsonl"


def index() -> Path:
    return state_dir() / "docs" / "index.json"


def sessions() -> Path:
    """Where each session's docs mode is recorded."""
    return state_dir() / "docs" / "sessions"


def session_mode(harness: str, session: str) -> Path:
    return sessions() / f"{harness}-{session}"


def window(harness: str, session: str) -> Path:
    return state_dir() / "docs" / "windows" / f"{harness}-{session}.json"
