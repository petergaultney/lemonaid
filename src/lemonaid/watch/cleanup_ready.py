"""Done children whose cleanup was held, reported once when nothing holds them any more.

Children are re-read only while one is held or newly done, so a parent with none pays
nothing beyond its usual brief poll.
"""

import dataclasses
import json
import pathlib
from collections import abc

from ..brief import children, children_cli, lemon
from ..inbox import db
from ..log import get_logger
from . import cursors

_log = get_logger("watch.cleanup_ready")

_EVERY = 30.0  # holds such as an attached client last minutes or hours


@dataclasses.dataclass
class Tracker:
    path: pathlib.Path
    held: dict[str, list[str]]  # done child to why its cleanup was held; [] once settled
    checked_at: float = 0.0  # wall clock, so the interval holds across one-shot rearms


def open_tracker(path: pathlib.Path) -> Tracker:
    try:
        saved = json.loads(path.read_text())
        return Tracker(path, dict(saved["held"]), float(saved["checked_at"]))
    except (OSError, ValueError, TypeError, KeyError) as error:
        if path.exists():
            _log.warning("Cannot load cleanup cursor %s: %s", path, error)
        return Tracker(path, {})


def _save(tracker: Tracker) -> None:
    cursors.write_json(tracker.path, {"held": tracker.held, "checked_at": tracker.checked_at})


def _in_tmux(child: children.Child) -> bool:
    return bool(child.tmux_session) or any(_in_tmux(c) for c in child.children)


def due(tracker: Tracker, parent: str, done: abc.Set[str], now: float) -> dict[str, list[str]]:
    """Children in *done* whose held cleanup is now ready, each with what last held it."""
    kept = {c: reasons for c, reasons in tracker.held.items() if c in done}
    if kept != tracker.held:  # a child that leaves done is judged afresh when it returns
        tracker.held = kept
        _save(tracker)
    if all(tracker.held.get(c) == [] for c in done) or 0 <= now - tracker.checked_at < _EVERY:
        return {}

    tracker.checked_at = now
    world = children_cli.holds_world()
    tmux_known = world.sessions is not None and world.clients is not None
    with db.connect() as conn:
        found = {c.lemon_id: c for c in children.of(conn, lemon.current(conn, parent), world)}
    ready: dict[str, list[str]] = {}
    for lemon_id in done:
        child, before = found.get(lemon_id), tracker.held.get(lemon_id)
        if child is None or before == [] or (_in_tmux(child) and not tmux_known):
            continue  # a session whose clients tmux can't report could read as ready

        if child.cleanup == "held":
            tracker.held[lemon_id] = list(child.held_by)
        elif before and child.cleanup == "ready":
            ready[lemon_id] = before
        else:
            tracker.held[lemon_id] = []  # ready when first seen done, or cleaned up already
    _save(tracker)
    return ready


def commit(tracker: Tracker, reported: abc.Iterable[str]) -> None:
    tracker.held |= {lemon_id: [] for lemon_id in reported}
    _save(tracker)
