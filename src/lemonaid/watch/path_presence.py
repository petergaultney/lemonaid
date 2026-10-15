"""Remember disappearance notifications across rearming, without retargeting a watch."""

import dataclasses
import json
import pathlib
import time
from collections import abc

from ..log import get_logger
from . import cursors, nearby_paths

_log = get_logger("watch.presence")


@dataclasses.dataclass
class Presence:
    path: pathlib.Path
    cursor: pathlib.Path
    identity: nearby_paths.Identity | None
    seen: bool
    reported: bool
    missing_since: float | None = None
    message: str = ""


def _save(watch: Presence) -> None:
    cursors.write_json(
        watch.cursor,
        {"identity": watch.identity, "seen": watch.seen, "reported": watch.reported},
    )


def observe(watch: Presence) -> bool:
    try:
        current = nearby_paths.identity(watch.path)
    except FileNotFoundError:
        return False

    changed = current != watch.identity or not watch.seen or watch.reported
    watch.identity, watch.seen, watch.reported = current, True, False
    watch.missing_since, watch.message = None, ""
    if changed:
        _save(watch)
    return True


def open_watch(stem: pathlib.Path, path: pathlib.Path, seen: bool = False) -> Presence:
    cursor = stem.with_suffix(".presence.json")
    saved: dict = {}
    try:
        value = json.loads(cursor.read_text())
        if isinstance(value, dict):
            saved = value
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as error:
        _log.warning("Cannot read watch presence cursor %s: %s", cursor, error)
    stored = saved.get("identity")
    previous = (
        (int(stored[0]), int(stored[1]), int(stored[2]), float(stored[3]))
        if isinstance(stored, list)
        and len(stored) == 4
        and all(isinstance(part, int | float) for part in stored)
        else None
    )
    watch = Presence(
        path.absolute(),
        cursor,
        previous,
        seen or saved.get("seen") is True,
        saved.get("reported") is True,
    )
    observe(watch)
    return watch


def missing_message(watch: Presence, prefix: str) -> str:
    if not watch.message:
        found = nearby_paths.candidates(watch.path, watch.identity) if watch.identity else []
        watch.message = prefix
        if found:
            watch.message += "; possible replacement: " + ", ".join(map(str, found))
            watch.message += (
                ". Confirm before updating your watch list; the watch target is unchanged"
            )
    return watch.message


def report_missing(
    watch: Presence, quiet: float, deliver: abc.Callable[[str], bool]
) -> bool | None:
    """None means no event; a delivered notice is remembered only after acknowledgement."""
    if not watch.seen or watch.reported:
        return None

    now = time.monotonic()
    if watch.missing_since is None:
        watch.missing_since = now
    if now - watch.missing_since < quiet:
        return None

    if observe(watch):
        return None

    message = missing_message(
        watch, f"{watch.path} is no longer present; it may have been deleted or moved"
    )
    if not deliver(message):
        return False

    watch.reported = True
    _save(watch)
    return True
