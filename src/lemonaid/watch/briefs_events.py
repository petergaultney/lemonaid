"""Child brief changes, remembered per parent and watcher across one-shot rearms."""

import dataclasses
import hashlib
import json
import os
import pathlib
import sqlite3
import time
from collections import abc

from ..brief import lemon, lemon_table, status, store
from ..inbox import db
from ..lineage import links
from ..log import get_logger
from . import briefs_orphans, delivery, lemon_liveness, needs_text

_log = get_logger("watch.briefs")


@dataclasses.dataclass(frozen=True)
class _Mark:
    status: str
    needs: str
    path: str = dataclasses.field(default="", compare=False)


@dataclasses.dataclass(frozen=True)
class _Seen:
    marks: dict[str, _Mark]
    explicit: dict[str, lemon_table.Row]  # watched lemons whose row sets their wake statuses
    problems: dict[str, lemon_liveness.Problem | None]


def _resolve(
    conn: sqlite3.Connection, rows: abc.Iterable[lemon_table.Row]
) -> dict[str, lemon_table.Row]:
    found: dict[str, lemon_table.Row] = {}
    for row in rows:
        try:
            found[lemon.lemon_id(conn, row.lemon)] = row
        except (LookupError, ValueError, store.ChangedUnderneath) as error:
            _log.warning("Cannot resolve ### Lemons row %s: %s", row.lemon, error)
    return found


def _snapshot(parent: str, rows: abc.Iterable[lemon_table.Row], orphans: bool) -> _Seen:
    with db.connect() as conn:
        found: dict[str, _Mark] = {}
        explicit = _resolve(conn, rows)
        watched = links.children_of(conn, lemon.current(conn, parent))
        watched += [lemon_id for lemon_id in explicit if lemon_id not in watched]
        if orphans:
            watched += briefs_orphans.find(
                conn, {lemon.current(conn, parent), *watched}, briefs_orphans.live_sessions
            )
        for child in watched:
            path = lemon.brief_of(conn, child)
            if path is None:
                continue
            try:
                text = path.read_text()
            except FileNotFoundError:
                continue
            except OSError as error:
                _log.warning("Cannot read child brief %s: %s", path, error)
                continue
            found[child] = _Mark(status.split(text).status, needs_text.needs(text), str(path))
        problems = lemon_liveness.probe(conn, {child: mark.status for child, mark in found.items()})
        return _Seen(found, explicit, problems)


def state_stem(
    state_dir: pathlib.Path,
    parent: str,
    me: str,
    to: frozenset[str] = frozenset({"merge", "done"}),
    orphans: bool = False,
) -> pathlib.Path:
    key = f"{db.get_db_path().resolve()}\0{parent}\0{me}"
    key += "\0to:" + ",".join(sorted(to))
    key += "\0orphans" if orphans else ""
    return state_dir / hashlib.sha256(key.encode()).hexdigest()[:24]


def _load(path: pathlib.Path) -> dict[str, _Mark] | None:
    try:
        saved = json.loads(path.read_text())
        return {child: _Mark(**mark) for child, mark in saved.items()}
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, AttributeError) as error:
        _log.warning("Cannot load child watch state %s: %s", path, error)
        return None


def _save(path: pathlib.Path, marks: abc.Mapping[str, _Mark]) -> None:
    tmp = path.with_suffix(f".tmp{os.getpid()}")
    tmp.write_text(json.dumps({child: dataclasses.asdict(mark) for child, mark in marks.items()}))
    tmp.replace(path)


@dataclasses.dataclass
class BriefsWatch:
    parent: str
    quiet: float
    reported_path: pathlib.Path
    reported: dict[str, _Mark]
    pending: dict[str, _Mark]
    pending_since: float
    to: frozenset[str]
    tracker: lemon_liveness.Tracker
    orphans: bool = False
    rows: tuple[lemon_table.Row, ...] = ()
    needs: bool = False  # a changed Needs wakes, as it does with `orphans`


def open_watch(
    state_dir: pathlib.Path,
    parent: str,
    me: str,
    quiet: float,
    to: frozenset[str] = frozenset({"merge", "done"}),
    orphans: bool = False,
    rows: tuple[lemon_table.Row, ...] = (),
    needs: bool = False,
) -> BriefsWatch:
    state_dir.mkdir(parents=True, exist_ok=True)
    stem = state_stem(state_dir, parent, me, to, orphans)
    path = stem.with_suffix(".reported.json")
    seen = _snapshot(parent, rows, orphans)
    reported = _load(path)
    if reported is None:
        reported = seen.marks
        _save(path, reported)
    tracker = lemon_liveness.open_tracker(stem.with_suffix(".live.json"), seen.problems)
    return BriefsWatch(
        parent,
        quiet,
        path,
        reported,
        seen.marks,
        time.monotonic(),
        to,
        tracker,
        orphans,
        rows,
        needs,
    )


def _describe(child: str, previous: _Mark | None, current: _Mark) -> str:
    state = (
        f"Status: {previous.status or 'none'} -> {current.status or 'none'}"
        if previous and previous.status != current.status
        else f"Status: {current.status or 'none'}"
    )
    ask = (
        f"; Needs: {current.needs or '(none)'}"
        if current.needs or (previous and current.needs != previous.needs)
        else ""
    )
    return f"{child}: {state}{ask} ({current.path})"


def _absorbed(
    w: BriefsWatch, row: lemon_table.Row | None, mark: _Mark, previous: _Mark | None
) -> bool:
    """Whether a changed mark advances the baseline without waking, under the lemon's row if
    it has one: a Needs ask that appeared or changed wakes when Needs is watched."""
    if row and previous is None:  # a newly listed lemon's current state is taken as seen
        return True

    to = frozenset(row.wake) if row else w.to
    if (
        (lemon_table.NEEDS in to if row else w.orphans or w.needs)
        and mark.needs
        and (previous is None or previous.needs != mark.needs)
    ):
        return False

    return mark.status not in to or bool(previous and mark.status == previous.status)


def poll(w: BriefsWatch, deliver: delivery.Deliver) -> bool:
    seen = _snapshot(w.parent, w.rows, w.orphans)
    current = seen.marks
    absorbed = {
        child: mark
        for child, mark in current.items()
        if mark != (previous := w.reported.get(child))
        and _absorbed(w, seen.explicit.get(child), mark, previous)
    }
    if absorbed:
        w.reported = w.reported | absorbed
        w.pending = w.pending | absorbed
        _save(w.reported_path, w.reported)
    if {child: mark.status for child, mark in current.items()} != {
        child: mark.status for child, mark in w.pending.items()
    }:
        w.pending_since = time.monotonic()
    w.pending = current
    changed = (
        {child: mark for child, mark in current.items() if mark != w.reported.get(child)}
        if time.monotonic() - w.pending_since >= w.quiet
        else {}
    )
    stopped = lemon_liveness.due(w.tracker, seen.problems, w.quiet, time.monotonic())
    if not changed and not stopped:
        return False

    deliver(
        "\n".join(
            [
                *(_describe(child, w.reported.get(child), mark) for child, mark in changed.items()),
                *(
                    f"{child}: {problem.detail}; Status: {current[child].status or 'none'}"
                    f" ({current[child].path})"
                    for child, problem in stopped.items()
                ),
            ]
        )
    )
    if changed:
        # Retain missing or unlinked briefs so their return alone does not repeat a report.
        w.reported = w.reported | current
        _save(w.reported_path, w.reported)
    lemon_liveness.commit(w.tracker, stopped)
    return True
