"""The live state of pull requests a brief names, from `gh`.

A brief says what its worker last wrote; the PR says what has happened since.
Only explicit references count: a pull-request URL, or `PR #N`, which `gh`
resolves against the repository of the brief's directory.
"""

import json
import re
import subprocess
import threading
import time
from collections import abc
from pathlib import Path

_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/(?P<number>\d+)")
_NUMBER = re.compile(r"\bPR\s*#(?P<number>\d+)", re.IGNORECASE)
_MAX_REFS = 3
_GH_TIMEOUT_SECONDS = 5
_CACHE_SECONDS = 120

Lookup = abc.Callable[[str, Path | None], str]


def refs(text: str) -> list[str]:
    """PR references in *text*, in order: URLs, then numbers no URL already covers."""
    urls = {match["number"]: match[0] for match in _URL.finditer(text)}
    numbers = [n for match in _NUMBER.finditer(text) if (n := match["number"]) not in urls]
    return list(dict.fromkeys([*urls.values(), *numbers]))[:_MAX_REFS]


def label(ref: str) -> str:
    match = _URL.fullmatch(ref)
    return f"#{match['number']}" if match else f"#{ref}"


def lookup(ref: str, cwd: Path | None) -> str:
    """`open`, `draft`, `merged` or `closed`; "" when `gh` can't say."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", ref, "--json", "state,isDraft"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd if cwd and cwd.is_dir() else None,
            timeout=_GH_TIMEOUT_SECONDS,
        )
        data = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""

    state = str(data.get("state", "")).lower()
    return "draft" if state == "open" and data.get("isDraft") else state


class Cache:
    """Non-blocking lookups for a view that re-renders on a timer.

    A miss answers "" and fetches in the background; a later render sees it.
    """

    def __init__(self, fetch: Lookup = lookup, max_age: float = _CACHE_SECONDS) -> None:
        self._fetch = fetch
        self._max_age = max_age
        self._states: dict[tuple[str, Path | None], tuple[float, str]] = {}
        self._pending: set[tuple[str, Path | None]] = set()
        self._lock = threading.Lock()

    def _refresh(self, key: tuple[str, Path | None]) -> None:
        state = self._fetch(*key)
        with self._lock:
            self._states[key] = (time.monotonic(), state)
            self._pending.discard(key)

    def get(self, ref: str, cwd: Path | None) -> str:
        key = (ref, cwd)
        with self._lock:
            fetched_at, state = self._states.get(key, (float("-inf"), ""))
            if time.monotonic() - fetched_at < self._max_age or key in self._pending:
                return state

            self._pending.add(key)

        threading.Thread(target=self._refresh, args=(key,), daemon=True).start()
        return state
