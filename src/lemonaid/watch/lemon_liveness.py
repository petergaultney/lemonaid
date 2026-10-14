"""Whether watched lemons are still running, reported once per exit.

A lemon whose brief is `done` is never a problem: its session going away is normal.
"""

import dataclasses
import functools
import json
import pathlib
import sqlite3
import time
from collections import abc

from ..brief import attached, lemon
from ..log import get_logger
from ..messages import recipient, store, waiter
from . import briefs_orphans, cursors

_log = get_logger("watch.liveness")

_DEAF_SETTLE = 60.0  # a lemon is briefly deaf between finishing a turn and rearming its waiter


@dataclasses.dataclass(frozen=True)
class Problem:
    kind: str  # "exited", "gone" or "deaf"
    stamp: str  # tells one exit from the next
    detail: str

    @property
    def token(self) -> str:
        return f"{self.kind}:{self.stamp}"


def _problem(
    entry: attached.Attachment,
    lemon_id: str,
    sessions: abc.Callable[[str], abc.Set[str] | None],
) -> Problem | None:
    row = entry.notification
    if row is None:
        return Problem("gone", "", "its inbox session is gone")

    running = sessions(row.metadata.get("tmux_socket") or "") if entry.tmux_session else None
    if running is not None and entry.tmux_session not in running:
        return Problem("gone", "", f"its tmux session {entry.tmux_session} is gone")

    cwd = str(row.metadata.get("cwd") or "")
    if cwd and not pathlib.Path(cwd).is_dir():
        return Problem("gone", "", f"its directory {cwd} is gone")

    alive = recipient.harness_alive(row)
    exited_at = row.metadata.get("exited_at")
    if alive is False or exited_at is not None:
        reason = str(row.metadata.get("exit_reason") or "no reason recorded")
        return Problem("exited", str(exited_at or ""), f"its harness exited ({reason})")

    if row.is_archived or row.is_snoozed:
        return None

    state = recipient.classify(
        entry.channel, row, alive, waiter.is_armed(store.inbox_for_id(lemon_id)), time.time()
    )
    return Problem("deaf", "", state.detail) if state.state == recipient.DEAF else None


def probe(
    conn: sqlite3.Connection,
    statuses: abc.Mapping[str, str],
    sessions: abc.Callable[[str], abc.Set[str] | None] | None = None,
) -> dict[str, Problem | None]:
    """What is wrong with each lemon in *statuses* (Lemon-ID to its brief's Status), if anything."""
    sessions = functools.cache(sessions or briefs_orphans.live_sessions)
    attached.claim_pending(conn)
    by_path = {entry.path: entry for entry in attached.everything(conn)}
    found: dict[str, Problem | None] = {}
    for lemon_id, status in statuses.items():
        path = lemon.brief_of(conn, lemon_id)
        entry = by_path.get(path) if path else None
        if status == "done" or (entry is not None and not entry.channel):
            found[lemon_id] = None  # finished, or still waiting for its lemon to start
        elif entry is None:
            found[lemon_id] = Problem("gone", "", "no session is attached to its brief")
        else:
            found[lemon_id] = _problem(entry, lemon_id, sessions)
    return found


@dataclasses.dataclass
class Tracker:
    path: pathlib.Path
    reported: dict[str, str]  # Lemon-ID to the token last reported or taken as seen; "" is healthy
    held: dict[str, tuple[str, float]] = dataclasses.field(default_factory=dict)


def open_tracker(path: pathlib.Path, current: abc.Mapping[str, Problem | None]) -> Tracker:
    """A tracker that takes the *current* state as seen when it has no saved cursor."""
    try:
        return Tracker(path, json.loads(path.read_text()))
    except (OSError, ValueError) as error:
        if path.exists():
            _log.warning("Cannot load liveness cursor %s: %s", path, error)

    tracker = Tracker(path, {lemon_id: p.token if p else "" for lemon_id, p in current.items()})
    cursors.write_json(path, tracker.reported)
    return tracker


def due(
    tracker: Tracker,
    current: abc.Mapping[str, Problem | None],
    settle: float,
    now: float,
) -> dict[str, Problem]:
    """The problems to report now: new, and unchanged for long enough to be real.

    A lemon first seen, or healthy again, is recorded without a report.
    """
    ready: dict[str, Problem] = {}
    changed = False
    for lemon_id, problem in current.items():
        token = problem.token if problem else ""
        last = tracker.reported.get(lemon_id)
        if last is None:
            tracker.reported[lemon_id], changed = token, True
        elif token == last:
            tracker.held.pop(lemon_id, None)
        else:
            if last:  # whatever was reported has ended, so its return is a new event
                tracker.reported[lemon_id], changed = "", True
            if not problem:
                tracker.held.pop(lemon_id, None)
                continue

            held = tracker.held.get(lemon_id)
            if held is None or held[0] != token:
                held = tracker.held[lemon_id] = (token, now)
            if now - held[1] >= (_DEAF_SETTLE if problem.kind == "deaf" else settle):
                ready[lemon_id] = problem
    if changed:
        cursors.write_json(tracker.path, tracker.reported)
    return ready


def commit(tracker: Tracker, reported: abc.Mapping[str, Problem]) -> None:
    tracker.reported |= {lemon_id: problem.token for lemon_id, problem in reported.items()}
    for lemon_id in reported:
        tracker.held.pop(lemon_id, None)
    cursors.write_json(tracker.path, tracker.reported)
