"""Whether watched lemons are still running, reported once per exit.

A lemon whose brief is `done` is never a problem: its session going away is normal.
A started lemon is expected to write its brief's Now or Status in its first turn, so one
that goes idle with both empty and the file unchanged since it was attached has not taken
it up. A brief carried over by a handoff, `/clear` or `brief attach` has them already.
Nor is one lost with its terminal while a restore runs: the restore is bringing it
back, and a parent told it is gone would resume it alongside.
"""

import dataclasses
import functools
import json
import pathlib
import sqlite3
import time
from collections import abc

from ..brief import attached, lemon, now_edit
from ..inbox import ended
from ..launch.restart import state
from ..log import get_logger
from ..messages import recipient, store, waiter
from ..restore import auto
from . import briefs_orphans, cursors

_log = get_logger("watch.liveness")

_DEAF_SETTLE = 60.0  # a lemon is briefly deaf between finishing a turn and rearming its waiter
_ROW_GRACE = 600.0  # a Codex lemon has no inbox row until its first turn ends
_START_GRACE = 300.0  # how long a brief may wait for its lemon to start
_START_WINDOW = 3600.0  # an older start is old news, such as one from before an upgrade
_SETTLED = frozenset({"deaf", "untouched"})


@dataclasses.dataclass(frozen=True)
class Problem:
    kind: str  # "exited", "gone", "deaf", "unstarted" or "untouched"
    stamp: str  # tells one exit from the next
    detail: str

    @property
    def token(self) -> str:
        return f"{self.kind}:{self.stamp}"


def _untouched(entry: attached.Attachment, status: str) -> bool:
    if status:
        return False

    try:
        if entry.path.stat().st_mtime > entry.attached_at:
            return False

        now = now_edit.now_of(entry.path.read_text())
    except (OSError, UnicodeError):
        return False

    return not now.lead and not any(section.body for section in now.sections)


def _unstarted(entry: attached.Attachment, now: float) -> Problem | None:
    if not _START_GRACE <= now - entry.requested_at < _START_WINDOW:
        return None

    asked = time.strftime("%H:%M", time.localtime(entry.requested_at))
    return Problem(
        "unstarted", str(entry.requested_at), f"no lemon has taken up its brief since {asked}"
    )


def _problem(
    entry: attached.Attachment,
    lemon_id: str,
    status: str,
    sessions: abc.Callable[[str], abc.Set[str] | None],
    parked: abc.Callable[[], abc.Mapping[str, str]],
    unrun: abc.Callable[[], abc.Mapping[str, str]],
    restoring: abc.Callable[[], bool],
) -> Problem | None:
    """A parked lemon is reported as deaf, with the reason in its detail."""
    row = entry.notification
    if state.blocked(entry.channel):
        return None

    if row is not None and ended.revivable(row.metadata) and restoring():
        return None

    if row is None:
        if time.time() - entry.attached_at < _ROW_GRACE:
            return None

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

    found_state = recipient.classify(
        entry.channel,
        row,
        alive,
        waiter.is_armed(store.mailbox_for_id(lemon_id)),
        time.time(),
        parked().get(entry.channel, ""),
        unrun().get(entry.channel, ""),
    )
    if found_state.state in (recipient.DEAF, recipient.PARKED):
        return Problem("deaf", "", found_state.detail)

    if found_state.state == recipient.LISTENING and _untouched(entry, status):
        return Problem(
            "untouched",
            str(entry.attached_at),
            "it went idle without touching its brief since it started",
        )

    return None


def probe(
    conn: sqlite3.Connection,
    statuses: abc.Mapping[str, str],
    sessions: abc.Callable[[str], abc.Set[str] | None] | None = None,
) -> dict[str, Problem | None]:
    """What is wrong with each lemon in *statuses* (Lemon-ID to its brief's Status), if anything."""
    if not statuses:
        return {}

    sessions = functools.cache(sessions or briefs_orphans.live_sessions)
    parked = functools.cache(recipient.parked_jobs)
    unrun = functools.cache(recipient.unrun_codex)
    restoring = functools.cache(auto.running)
    attached.claim_pending(conn)
    paths = {lemon_id: lemon.brief_of(conn, lemon_id) for lemon_id in statuses}
    by_path = {
        entry.path: entry for entry in attached.for_paths(conn, filter(None, paths.values()))
    }
    found: dict[str, Problem | None] = {}
    for lemon_id, status in statuses.items():
        path = paths[lemon_id]
        entry = by_path.get(path) if path else None
        if status == "done":
            found[lemon_id] = None
        elif entry is not None and not entry.channel:
            found[lemon_id] = _unstarted(entry, time.time())
        elif entry is None:
            found[lemon_id] = Problem("gone", "", "no session is attached to its brief")
        else:
            found[lemon_id] = _problem(entry, lemon_id, status, sessions, parked, unrun, restoring)
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

    A lemon first seen is recorded without a report. A reported problem ends only once the
    lemon has stayed healthy for the settle time, so a probe that fails for a moment (as
    tmux does while lemonaid is being reinstalled) does not make the same problem new.
    """
    ready: dict[str, Problem] = {}
    changed = False
    for lemon_id, problem in current.items():
        token = problem.token if problem else ""
        last = tracker.reported.get(lemon_id)
        if last is None:
            tracker.reported[lemon_id], changed = token, True
            continue

        if token == last:
            tracker.held.pop(lemon_id, None)
            continue

        held = tracker.held.get(lemon_id)
        if held is None or held[0] != token:
            held = tracker.held[lemon_id] = (token, now)
        if now - held[1] < (_DEAF_SETTLE if problem and problem.kind in _SETTLED else settle):
            continue

        if problem:
            ready[lemon_id] = problem
        else:
            tracker.reported[lemon_id], changed = "", True
            tracker.held.pop(lemon_id, None)
    if changed:
        cursors.write_json(tracker.path, tracker.reported)
    return ready


def commit(tracker: Tracker, reported: abc.Mapping[str, Problem]) -> None:
    tracker.reported |= {lemon_id: problem.token for lemon_id, problem in reported.items()}
    for lemon_id in reported:
        tracker.held.pop(lemon_id, None)
    cursors.write_json(tracker.path, tracker.reported)
