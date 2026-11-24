"""The lemons a watcher may end once its PR merges or closes, named in the batch that says so.

These are the lemons whose brief names the watcher as `parent:` and that share their tmux
session with another live lemon (for an author, its reviewers), once their work is done. A
lemon alone in its session is its place's lemon, which `place toss` cleans up, so it is
left out. Their work is done when their Status says so, or this PR is in their PRs table
and every PR there has merged or closed.
"""

import shlex
import sqlite3

from ...brief import children, identity, lemon, named_children, status
from ...config import load_config
from ...inbox import db
from ...log import get_logger
from . import done

_log = get_logger("launch.end.hint")


def endable(watcher: str, url: str) -> dict[str, str]:
    """Each lemon *watcher* may end now that *url* merged or closed, with its Status."""
    finished = done.finished_lookup(load_config().brief.pr_state, None)
    found: dict[str, str] = {}
    with db.connect() as conn:
        started = {
            lemon_id: entry
            for lemon_id, entry in named_children.of(conn, lemon.current(conn, watcher)).items()
            if not done.sole_session(conn, entry.notification)
        }
    for lemon_id, entry in started.items():
        try:
            text = entry.path.read_text()
        except OSError as error:
            _log.warning("Cannot read brief %s: %s", entry.path, error)
            continue

        state = status.split(text).status or done.NO_STATUS
        on_it = any(done.same_pr(url, listed) for listed in children.prs(text))
        if (on_it or state == "done") and done.work_done(text, finished):
            found[lemon_id] = state
    return found


def _command(lemon_id: str, state: str) -> str:
    """Expecting its Status as it is now, or `done`, which it may set while handling the merge."""
    expected = "" if state == "done" else f" --expect done --expect {shlex.quote(state)}"
    return f"lemonaid lemon end {lemon_id}{expected}"


def lines(watcher: str, url: str) -> list[str]:
    """One line for each lemon *watcher* may now end, with the command that ends it.

    A failure leaves the lines out, never the merge or close they ride along with.
    """
    try:
        found = endable(watcher, url)
    except (OSError, ValueError, sqlite3.Error) as error:
        _log.warning("Cannot tell which lemons %s may end after %s: %s", watcher, url, error)
        return []

    return [
        f"{identity.brief_name(lemon_id) or lemon_id}, which you started, is done:"
        f" end it with `{_command(lemon_id, state)}`"
        for lemon_id, state in found.items()
    ]
