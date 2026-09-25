"""The live state of pull requests a brief names, from a command in lemonaid's config.

A brief says what its worker last wrote; the PR says what has happened since.
Only explicit references count: a pull-request URL, or `PR #N`. lemonaid knows
nothing about the forge: `[brief] pr_state` is a shell command that prints one
word for `{ref}`, run in the lemon's place so a bare number resolves against
that directory's repository.
"""

import re
import shlex
import subprocess
import threading
import time
from collections import abc
from pathlib import Path

from ..log import get_logger

_log = get_logger("brief.pr")

_URL = re.compile(r"https://[\w.-]+/(?P<repo>[\w.-]+/[\w.-]+)/pulls?/(?P<number>\d+)")
_REF = re.compile(rf"(?P<url>{_URL.pattern})|\bPR\s*#(?P<bare>\d+)", re.IGNORECASE)
_STATES = ("open", "draft", "merged", "closed")
_MAX_REFS = 3
_TIMEOUT_SECONDS = 5
_CACHE_SECONDS = 120

Lookup = abc.Callable[[str, Path | None], str]


def _number(ref: str) -> str:
    match = _URL.fullmatch(ref)
    return match["number"] if match else ref


def refs(text: str) -> list[str]:
    """PR references in *text*, in the order written, each once.

    A bare `PR #N` is the same PR as a URL for #N only when every URL in the
    brief is in one repository; otherwise nothing says which repository it
    means, and both are kept.
    """
    matches = list(_REF.finditer(text))
    one_repo = len({_URL.fullmatch(m["url"])["repo"] for m in matches if m["url"]}) == 1
    found: list[str] = []
    for match in matches:
        number = match["number"] or match["bare"]
        slot = next((i for i, ref in enumerate(found) if one_repo and _number(ref) == number), None)
        if slot is None:
            found.append(match["url"] or match["bare"])
        elif match["url"] and found[slot] == number:
            found[slot] = match["url"]  # the bare mention's place, now with its URL

    return list(dict.fromkeys(found))[:_MAX_REFS]


def label(ref: str, refs_shown: abc.Collection[str] = ()) -> str:
    """`#N`, or `repo#N` for a URL when the refs shown with it span repositories."""
    match = _URL.fullmatch(ref)
    if not match:
        return f"#{ref}"

    repos = {m["repo"] for r in refs_shown if (m := _URL.fullmatch(r))}
    return (
        f"#{match['number']}"
        if len(repos) <= 1
        else f"{match['repo'].split('/')[-1]}#{match['number']}"
    )


def no_state(ref: str, cwd: Path | None) -> str:
    return ""


def lookup(command: str, ref: str, cwd: Path | None) -> str:
    """The first word *command* prints for *ref*, if it is a state; "" otherwise.

    A failing command is a configuration or environment problem the reader of a
    brief can't act on, so it logs and shows no state.
    """
    filled = command.replace("{ref}", shlex.quote(ref))
    try:
        result = subprocess.run(
            filled,
            shell=True,
            cwd=cwd if cwd and cwd.is_dir() else None,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _log.warning("pr_state %r failed to run: %s", filled, e)
        return ""

    if result.returncode != 0:
        _log.warning("pr_state %r exited %d: %s", filled, result.returncode, result.stderr.strip())
        return ""

    word = next(iter(result.stdout.split()), "").lower()
    return word if word in _STATES else ""


def configured(command: str) -> Lookup:
    """A lookup running *command*, or one that shows no state when it is unset."""
    if not command.strip():
        return no_state

    return lambda ref, cwd: lookup(command, ref, cwd)


class Cache:
    """Non-blocking lookups for a view that re-renders on a timer.

    A miss answers "" and fetches in the background; a later render sees it.
    """

    def __init__(self, fetch: Lookup, max_age: float = _CACHE_SECONDS) -> None:
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
