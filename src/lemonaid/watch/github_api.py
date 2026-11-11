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
from urllib import parse

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


def state_dir() -> Path:
    return cursors.root().parent / "github"


def pause_path() -> Path:
    return state_dir() / "paused-until.json"


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


def _gh(args: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["gh", "api", *args], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        _log.warning("gh api %s timed out", args[0])
        return None


def graphql(fields: list[str], query: str, *, partial: bool = False) -> dict | None:
    """The response's `data`; None when paused, refused, timed out or unreadable.

    `fields` are `gh api` field flags such as `["-F", "number=3"]`. With `partial`, a
    response with errors still returns whatever `data` it has, so one unreadable PR in a
    batch doesn't hide the rest.
    """
    if paused() or (r := _gh(["graphql", "--include", *fields, "-f", f"query={query}"])) is None:
        return None

    headers, body = _split(r.stdout)
    if pause := _pause_for(headers, r.stderr, r.returncode == 0):
        _pause(pause)
    if r.returncode != 0:
        _log.warning("gh api graphql failed: %s", r.stderr.strip()[:300])
        if not partial or pause:
            return None

    try:
        return json.loads(body)["data"]
    except (ValueError, KeyError, TypeError):
        return None


def rest(path: str) -> ty.Any:
    """The decoded JSON of a REST GET; None when paused, refused, timed out or unreadable.

    REST calls spend a quota separate from GraphQL's, so a REST response never starts the
    shared pause; it only honors one.
    """
    if paused() or (r := _gh(["-X", "GET", path])) is None:
        return None

    if r.returncode != 0:
        _log.warning("gh api %s failed: %s", path.split("?")[0], r.stderr.strip()[:300])
        return None

    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def rest_pages(
    path: str, params: abc.Mapping[str, str], *, per_page: int = 100, max_pages: int = 100
) -> list | None:
    """Every item of a paginated REST list, read until a short page; None if any page
    can't be read or *max_pages* full pages leave more unread."""
    items: list = []
    for page in range(1, max_pages + 1):
        query = parse.urlencode({**params, "per_page": per_page, "page": page})
        nodes = rest(f"{path}?{query}")
        if not isinstance(nodes, list):
            return None

        items.extend(nodes)
        if len(nodes) < per_page:
            return items
    _log.warning("gh api %s has more than %d pages; read none of it", path, max_pages)
    return None


def rest_send(path: str, method: str) -> bool:
    """Whether a REST call that changes something (`PATCH`, `DELETE`) succeeded."""
    if paused() or (r := _gh(["-X", method, path, "--silent"])) is None:
        return False

    if r.returncode != 0:
        _log.warning("gh api %s %s failed: %s", method, path, r.stderr.strip()[:300])
    return r.returncode == 0


def login() -> str | None:
    """The `gh` user's login; None when it can't be read."""
    user = rest("user")
    return (user.get("login") or None) if isinstance(user, dict) else None
