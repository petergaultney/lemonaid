"""Thread titles Codex records in its session index."""

import json
from pathlib import Path

from ..log import get_logger
from . import daemon_setup

_log = get_logger("codex")

# Titles Codex gives its own approval-review threads, which say nothing about the lemon.
_GENERIC = frozenset({"guardian review"})


def index_path() -> Path:
    return daemon_setup.codex_home() / "session_index.jsonl"


def read_index(path: Path) -> dict[str, str]:
    """Map each thread id to its latest title; the last line for an id wins."""
    titles: dict[str, str] = {}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return titles

    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            _log.warning("skipping unparseable line in %s", path)
            continue

        thread_id, title = entry.get("id"), entry.get("thread_name")
        if isinstance(thread_id, str) and isinstance(title, str) and title.strip():
            titles[thread_id] = title.strip()

    return {i: t for i, t in titles.items() if t.lower() not in _GENERIC}


class IndexCache:
    """The parsed session index, re-read only when its modification time changes."""

    def __init__(self) -> None:
        self._mtime = 0.0
        self._titles: dict[str, str] = {}

    def titles(self) -> dict[str, str]:
        path = index_path()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return {}

        if mtime != self._mtime:
            self._titles = read_index(path)
            self._mtime = mtime

        return self._titles
