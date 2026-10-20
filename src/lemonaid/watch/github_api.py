"""GitHub GraphQL reads through `gh`, and the machine-wide pause every reader honors.

Every lemon on a machine shares its user's GraphQL quota, 5,000 points an hour. When GitHub
refuses a read for quota, or says fewer than `_RESERVE` points are left, the reader writes
the time GitHub names for the reset to one file, and every reader skips its calls until
then, so a refused read is not retried each interval by every watcher at once. Each
process resumes at its own random offset after the reset, so they don't all fire together.

`gh api rate_limit` is no guide here: it can report a different quota window from the one
queries are spending, so the pause reads the rate-limit headers of the query's own response.
"""

import contextlib
import fcntl
import json
import random
import subprocess
import time
import typing as ty
from collections import abc
from pathlib import Path

from ..log import get_logger
from . import cursors

_RESERVE = 100  # points left for hand-run `gh` calls once watchers pause
_SECONDARY_PAUSE = 60.0  # GitHub's advice for a secondary limit without Retry-After
_UNKNOWN_RESET = 300.0  # a quota refusal whose response names no reset
_JITTER = random.uniform(0, 60)

_log = get_logger("watch.github")


class Pause(ty.NamedTuple):
    until: float  # epoch seconds, before this process's jitter
    reason: ty.Literal["quota", "secondary"]


def pause_path() -> Path:
    return cursors.root().parent / "github" / "paused-until.json"


def _saved() -> Pause | None:
    try:
        saved = json.loads(pause_path().read_text())
        return Pause(float(saved["until"]), saved["reason"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def paused(now: float | None = None) -> Pause | None:
    pause = _saved()
    return (
        pause if pause and pause.until + _JITTER > (time.time() if now is None else now) else None
    )


@contextlib.contextmanager
def locked(path: Path) -> abc.Iterator[None]:
    """Hold an exclusive lock on `path` (created if missing) across threads and processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def _pause(pause: Pause) -> None:
    """Extend the shared pause to `pause.until`; a shorter pause never cuts a longer one short."""
    with locked(pause_path().with_suffix(".lock")):
        current = _saved()
        if current and current.until >= pause.until:
            return

        _log.warning("Pausing GitHub reads until %s (%s)", time.ctime(pause.until), pause.reason)
        cursors.write_json(pause_path(), pause._asdict())


def _split(stdout: str) -> tuple[dict[str, str], str]:
    """Headers (lowercased) and body of `gh api --include` output; a bare body has no headers."""
    if not stdout.startswith("HTTP/"):
        return {}, stdout

    head, _, body = stdout.replace("\r\n", "\n").partition("\n\n")
    pairs = (line.split(":", 1) for line in head.splitlines()[1:] if ":" in line)
    return {k.strip().lower(): v.strip() for k, v in pairs}, body


def _pause_for(headers: dict[str, str], stderr: str, ok: bool) -> Pause | None:
    now = time.time()
    reset = float(headers.get("x-ratelimit-reset") or 0)
    if "secondary rate limit" in stderr.lower():
        return Pause(now + float(headers.get("retry-after") or _SECONDARY_PAUSE), "secondary")

    if not ok and "rate limit" in stderr.lower():
        return Pause(reset if reset > now else now + _UNKNOWN_RESET, "quota")

    remaining = headers.get("x-ratelimit-remaining")
    if remaining is not None and int(remaining) < _RESERVE and reset > now:
        return Pause(reset, "quota")

    return None


def graphql(fields: list[str], query: str) -> dict | None:
    """The response's `data`; None when paused, refused, timed out or unreadable.

    `fields` are `gh api` field flags such as `["-F", "number=3"]`.
    """
    if paused():
        return None

    try:
        r = subprocess.run(
            ["gh", "api", "graphql", "--include", *fields, "-f", f"query={query}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        _log.warning("gh api graphql timed out")
        return None

    headers, body = _split(r.stdout)
    if pause := _pause_for(headers, r.stderr, r.returncode == 0):
        _pause(pause)
    if r.returncode != 0:
        _log.warning("gh api graphql failed: %s", r.stderr.strip()[:300])
        return None

    try:
        return json.loads(body)["data"]
    except (ValueError, KeyError, TypeError):
        return None
