"""What `lemon end` and its merge-time hint read about a lemon: its work, harness and session."""

import sqlite3
from collections import abc
from pathlib import Path

from ... import pr_states
from ...brief import children, pr, status
from ...inbox import db
from ...messages import recipient
from ..restart import native, process

Finished = abc.Callable[[str], bool]  # whether the PR at a URL has merged or closed

NO_STATUS = "none"  # the Status a caller expects of a brief that has none


def finished_lookup(command: str, cwd: Path | None) -> Finished:
    """Merged or closed as a scout last read it from GitHub, or else as `[brief] pr_state` says."""

    def finished(url: str) -> bool:
        found = pr.repo_and_number(url)
        if found and pr_states.is_finished(*found):
            return True

        return bool(command.strip()) and pr.lookup(command, url, cwd) in ("merged", "closed")

    return finished


def same_pr(url: str, other: str) -> bool:
    found, wanted = pr.repo_and_number(url), pr.repo_and_number(other)
    return bool(found and wanted) and (found[0].lower(), found[1]) == (
        wanted[0].lower(),
        wanted[1],
    )


def running(row: db.Notification) -> bool:
    """Whether its harness may still run. A person may archive a live lemon's card, so the
    card says nothing; the process a hook recorded does, and without one, its terminal."""
    recorded = native.binding(row.channel)
    if recorded is not None:
        return process.same(process.Identity(**recorded["identity"]))

    return recipient.harness_alive(row) is not False


_MATES = """
SELECT 1 FROM notifications
WHERE status != 'archived' AND channel != :channel
  AND json_extract(metadata, '$.tmux_session') = :session
  AND COALESCE(json_extract(metadata, '$.tmux_socket'), '') = :socket
LIMIT 1
"""


def sole_session(conn: sqlite3.Connection, row: db.Notification | None) -> str:
    """The tmux session the lemon has to itself, which makes it its place's lemon, cleaned up
    with `place toss`; "" when another live lemon shares it, or it has none."""
    session = str(row.metadata.get("tmux_session") or "") if row else ""
    if not row or not session:
        return ""

    found = conn.execute(
        _MATES,
        {
            "channel": row.channel,
            "session": session,
            "socket": str(row.metadata.get("tmux_socket") or ""),
        },
    ).fetchone()
    return "" if found else session


def work_done(text: str, finished: Finished) -> bool:
    """Its Status is `done`, or every PR in its brief's PRs table has merged or closed."""
    if status.split(text).status == "done":
        return True

    urls = children.prs(text)
    return bool(urls) and all(finished(url) for url in urls)
