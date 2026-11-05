"""When a `--deadline` falls: an absolute ISO 8601 time, or a duration from when it was set.

A duration is anchored once and kept in the watch's cursor, so a rearm doesn't push it back.
"""

import datetime
import json
import pathlib
import re
import time

from . import cursors

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_DURATION = re.compile(r"(\d+(?:\.\d+)?)([smhd])")


def at(spec: str, anchor: float) -> float:
    """The deadline *spec* names, as a timestamp; a naive time is local. Raises ValueError."""
    if found := _DURATION.fullmatch(spec.strip()):
        return anchor + float(found[1]) * _UNITS[found[2]]

    when = datetime.datetime.fromisoformat(spec.strip())
    return (when if when.tzinfo else when.astimezone()).timestamp()


def checked(spec: str) -> str:
    """*spec*, for argparse, once it parses; argparse also passes the default, ""."""
    if not spec:
        return spec

    try:
        at(spec, 0.0)
    except ValueError:
        raise ValueError(f"{spec!r} is neither a duration (45m, 2h) nor an ISO time") from None
    return spec


def shown(when: float) -> str:
    return datetime.datetime.fromtimestamp(when).astimezone().strftime("%Y-%m-%d %H:%M %Z")


def load(path: pathlib.Path, spec: str) -> dict:
    """The saved deadline for *spec* (its `spec`, `at` and `done`), or one anchored now."""
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = {}
    if isinstance(saved, dict) and saved.get("spec") == spec and "at" in saved:
        return saved

    fresh = {"spec": spec, "at": at(spec, time.time()), "done": False}
    cursors.write_json(path, fresh)
    return fresh
