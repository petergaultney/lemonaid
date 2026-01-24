"""Codex session utilities."""

from __future__ import annotations

import json
import re
from pathlib import Path


def get_sessions_root() -> Path:
    """Return the Codex sessions root directory."""
    return Path.home() / ".codex" / "sessions"


def extract_session_id_from_filename(name: str) -> str | None:
    """Extract a session UUID from a Codex session filename."""
    match = re.search(
        r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        name,
    )
    if match:
        return match.group(1)
    return None


def read_session_meta(path: Path) -> dict | None:
    """Read the first session_meta payload from a session file."""
    try:
        with path.open() as f:
            for _ in range(20):
                line = f.readline()
                if not line:
                    break
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") == "session_meta":
                    return entry.get("payload", {})
    except OSError:
        return None
    return None


def find_session_path(session_id: str) -> Path | None:
    """Find a Codex session file by session ID."""
    if not session_id:
        return None

    root = get_sessions_root()
    if not root.exists():
        return None

    pattern = f"*{session_id}.jsonl"
    for path in root.rglob(pattern):
        if path.is_file():
            return path

    return None


def find_latest_session_for_cwd(cwd: str) -> Path | None:
    """Find the most recently modified session file for a cwd."""
    if not cwd:
        return None

    root = get_sessions_root()
    if not root.exists():
        return None

    latest_path: Path | None = None
    latest_mtime: float = 0.0

    for path in root.rglob("*.jsonl"):
        meta = read_session_meta(path)
        if not meta:
            continue
        if meta.get("cwd") != cwd:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > latest_mtime:
            latest_mtime = mtime
            latest_path = path

    return latest_path
