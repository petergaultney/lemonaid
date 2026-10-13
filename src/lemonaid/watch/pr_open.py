"""Whether a PR is open, from one `gh` call a minute at most while it is open.

A merged or closed PR is never asked again. The answer is kept in a file under the state directory, since each Stop hook is a new process.
"""

import json
import os
import subprocess
import time
from pathlib import Path

from ..log import get_logger

_log = get_logger("watch.pr_open")

_TTL = 60.0
_TIMEOUT = 5.0


def _cache() -> Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return Path(state).expanduser() / "pr-state.json"


def _saved() -> dict[str, list]:
    try:
        saved = json.loads(_cache().read_text())
    except (OSError, ValueError):
        return {}

    return saved if isinstance(saved, dict) else {}


def _ask(repo: str, number: int) -> str:
    """The PR's state (`OPEN`, `MERGED`, `CLOSED`), or "" when `gh` can't say."""
    try:
        r = subprocess.run(
            ["gh", "pr", "view", str(number), "--repo", repo, "--json", "state", "-q", ".state"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        _log.warning("gh could not say whether %s#%s is open: %s", repo, number, error)
        return ""

    if r.returncode != 0:
        _log.warning("gh pr view %s#%s failed: %s", repo, number, r.stderr.strip())
        return ""

    return r.stdout.strip()


def is_open(repo: str, number: int) -> bool:
    """Whether the PR is open; False when that can't be told, so a hook never blocks on it."""
    key = f"{repo}#{number}"
    saved = _saved()
    at, state = saved.get(key, (0.0, ""))
    if state in ("", "OPEN") and time.time() - at > _TTL:
        state = _ask(repo, number)
        if state:
            try:
                _cache().parent.mkdir(parents=True, exist_ok=True)
                _cache().write_text(json.dumps({**saved, key: [time.time(), state]}))
            except OSError as error:
                _log.warning("could not save the PR state cache: %s", error)

    return state == "OPEN"
