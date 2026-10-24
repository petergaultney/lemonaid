"""Point each lemon's inbox row at the pane its process runs in, as `restore tmux` finishes.

A row only names a tty, and ttys are reused when tmux restarts, so the evidence
here is the lemon itself: the pane whose Claude process lists that session, or
whose Codex process has that thread's rollout open. Nothing is ever pointed at
a pane on the strength of its tty alone.
"""

import sqlite3
import typing as ty
from collections import abc

from ..claude import live_sessions
from ..codex import channels as codex_channels
from ..codex import processes
from ..inbox import db
from ..log import get_logger
from . import navigation, recorded_pane

_log = get_logger("tmux.relink")

OK = "ok"
RELINKED = "relinked"
FORGOTTEN = "forgotten"  # not running, and its recorded pane now runs another lemon
NOT_RUNNING = "not running"
UNPLACEABLE = "unplaceable"  # running, but in no tmux pane or in several


class Relink(ty.NamedTuple):
    row: db.Notification
    state: str
    location: dict[str, ty.Any] | None  # the pane to record, for RELINKED


def _owner(row: db.Notification, owners: abc.Mapping[str, set[str]]) -> str:
    """The id `owners` would know *row*'s lemon by."""
    if row.channel.startswith("codex:"):
        return codex_channels.owner_id(row.channel, row.metadata, {k: [] for k in owners})

    if session_id := row.metadata.get("session_id"):
        return session_id

    prefix = row.channel.partition(":")[2]
    matches = [owner for owner in owners if owner.startswith(prefix)] if prefix else []
    return matches[0] if len(matches) == 1 else row.channel


def _current(row: db.Notification, location: abc.Mapping[str, ty.Any]) -> bool:
    return all(row.metadata.get(key) == value for key, value in location.items())


def plan(
    rows: abc.Iterable[db.Notification],
    owners: abc.Mapping[str, set[str]],
    panes: abc.Mapping[str, list[dict[str, ty.Any]]],
) -> list[Relink]:
    """What relinking *rows* would do, given which ttys each lemon runs on and the live panes."""
    tty_owners = {tty: owner for owner, ttys in owners.items() for tty in ttys}
    relinks = []
    for row in rows:
        owner = _owner(row, owners)
        ttys = owners.get(owner, set())
        if not ttys:
            recorded = row.metadata.get("tty")
            other = tty_owners.get(recorded) if recorded else None
            relinks.append(Relink(row, FORGOTTEN if other else NOT_RUNNING, None))
            continue

        locations = [location for tty in sorted(ttys) for location in panes.get(tty, [])]
        if len(locations) != 1:
            relinks.append(Relink(row, UNPLACEABLE, None))
        elif _current(row, locations[0]):
            relinks.append(Relink(row, OK, None))
        else:
            relinks.append(Relink(row, RELINKED, locations[0]))
    return relinks


def where(metadata: abc.Mapping[str, ty.Any]) -> str:
    """A row's recorded pane, as a person would name it."""
    session, window = metadata.get("tmux_session"), metadata.get("tmux_window")
    place = f"{session}:{window}" if session else "no tmux session"
    return f"{place} ({metadata.get('tty') or 'no tty'})"


def survey(conn: sqlite3.Connection) -> list[Relink] | None:
    """Relink every active tmux row from the lemons running now; None if tmux or `ps` can't say."""
    try:
        panes = recorded_pane.pane_metadata()
    except navigation.TmuxUnavailable as e:
        _log.warning("not relinking: cannot list tmux panes: %s", e)
        return None

    claude = live_sessions.by_tty()
    codex = processes.thread_ttys()
    if claude is None or codex is None:
        _log.warning("not relinking: cannot tell which lemons are running")
        return None

    owners = {**codex}
    for tty, sessions in claude.items():
        for session in sessions:
            owners.setdefault(session, set()).add(tty)
    return plan(db.get_active(conn, switch_source="tmux"), owners, panes)


_LABELS = {RELINKED: "relink", FORGOTTEN: "forget pane"}


def describe(relinks: abc.Iterable[Relink]) -> list[str]:
    """The rows a relink would change, as lines."""
    lines = []
    for r in relinks:
        if r.state not in _LABELS:
            continue
        before = where(r.row.metadata)
        after = where(r.location) if r.location is not None else "no pane"
        detail = f"{before} -> {after}" if before != after else f"{after}, recording its pane id"
        lines.append(f"{_LABELS[r.state]:<12} {r.row.name or r.row.channel}: {detail}")
    return lines


def as_json(relinks: abc.Iterable[Relink]) -> list[dict[str, str | None]]:
    return [
        {
            "channel": r.row.channel,
            "state": r.state,
            "recorded": where(r.row.metadata),
            "pane": where(r.location) if r.location is not None else None,
        }
        for r in relinks
    ]


def apply(conn: sqlite3.Connection, relinks: abc.Iterable[Relink]) -> list[Relink]:
    """Write *relinks*; returns those whose row changed, skipping any row that moved meanwhile."""
    applied = []
    for relink in relinks:
        if relink.state == RELINKED and relink.location is not None:
            changed = db.repair_location(conn, relink.row, relink.location)
        elif relink.state == FORGOTTEN:
            changed = db.forget_pane(conn, relink.row)
        else:
            continue

        if changed:
            _log.info("relink %s %s", relink.state, relink.row.channel)
            applied.append(relink)
    return applied
