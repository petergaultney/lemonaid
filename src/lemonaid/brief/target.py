"""Which directories and brief names belong to a session, from the inbox and tmux.

The TUI and the CLI both resolve through here, so a session's brief is the same
whichever way it is asked for.
"""

import dataclasses
from collections import abc
from pathlib import Path

from ..inbox import db
from . import session


@dataclasses.dataclass(frozen=True)
class Target:
    dirs: list[Path]  # searched in order; the first holding a brief wins
    place: Path | None  # the session's directory; no brief is looked for above it
    names: list[str]  # candidate <name>s for .z/brief-<name>.md, most specific first
    title: str


def _unique(paths: abc.Iterable[Path | None]) -> list[Path]:
    return list(dict.fromkeys(p for p in paths if p is not None))


def _backend(notification: db.Notification) -> str:
    return notification.channel.partition(":")[0]


def for_notification(notification: db.Notification) -> Target:
    """The target for one inbox row: its lemon's cwd, then its tmux session's directory."""
    tmux_session = notification.metadata.get("tmux_session") or ""
    cwd = notification.metadata.get("cwd")
    place = session.session_dir(tmux_session) if tmux_session else None
    return Target(
        _unique([Path(cwd) if cwd else None, place]),
        place,
        session.names(tmux_session, _backend(notification), notification.name or ""),
        notification.name or tmux_session or (Path(cwd).name if cwd else ""),
    )


def for_session(tmux_session: str, notifications: abc.Iterable[db.Notification]) -> Target:
    """The target for a tmux session, from every active inbox row recorded in it.

    A session can hold several lemons (a worker and its reviewer). Only when it
    holds exactly one does that lemon's backend count as a brief name; otherwise
    no one of them is more likely than the rest.
    """
    rows = sorted(
        (n for n in notifications if n.metadata.get("tmux_session") == tmux_session),
        key=lambda n: n.created_at,
        reverse=True,
    )
    if len(rows) == 1:
        return for_notification(rows[0])

    place = session.session_dir(tmux_session)
    return Target(
        _unique([*(Path(n.metadata["cwd"]) for n in rows if n.metadata.get("cwd")), place]),
        place,
        session.names(tmux_session),
        tmux_session,
    )
