"""Child brief changes, remembered per parent and watcher across one-shot rearms."""

import dataclasses
import hashlib
import json
import os
import pathlib
import re
import tempfile
import time
from collections import abc

from ..brief import lemon, status
from ..inbox import db
from ..lineage import links
from ..log import get_logger
from . import delivery

_log = get_logger("watch.briefs")

_ASK_HEADING = re.compile(r"^#{3,6}\s+\**Needs(?:\s+\w+)?\**\s*:?\s*#*\s*$", re.I)
_ASK_BULLET = re.compile(r"^([ \t]*)[-*+]\s+\**Needs(?:\s+\w+)?\**\s*:\**(.*)$", re.I)
_HEADING = re.compile(r"^#{1,6}\s")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+")


def _needs(text: str) -> str:
    """The first Needs section, with whitespace and bullet formatting normalized."""
    lines: list[str] = []
    active = False
    indent: int | None = None
    fence = ""
    for line in text.splitlines():
        delimiter = _FENCE.match(line)
        if not fence:
            if active:
                if _HEADING.match(line) or (
                    indent is not None
                    and line.strip()
                    and len(line.expandtabs()) - len(line.expandtabs().lstrip()) <= indent
                ):
                    break
            elif _ASK_HEADING.fullmatch(line):
                active = True
                continue
            elif bullet := _ASK_BULLET.fullmatch(line):
                active = True
                indent = len(bullet[1].expandtabs())
                lines.append(bullet[2])
                continue
        if active:
            lines.append(_BULLET.sub("", line))
        if delimiter:
            if not fence:
                fence = delimiter[1]
            elif (
                delimiter[1][0] == fence[0]
                and len(delimiter[1]) >= len(fence)
                and not delimiter[2].strip()
            ):
                fence = ""

    collapsed = " ".join(" ".join(lines).split())
    return (
        ""
        if collapsed.rstrip(".").lower() in {"", "nothing", "none", "no", "n/a", "-"}
        else collapsed
    )


@dataclasses.dataclass(frozen=True)
class _Mark:
    status: str
    needs: str
    path: str = dataclasses.field(default="", compare=False)


def _snapshot(parent: str) -> dict[str, _Mark]:
    with db.connect() as conn:
        found: dict[str, _Mark] = {}
        for child in links.children_of(conn, lemon.current(conn, parent)):
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
            if state := status.split(text).status:
                found[child] = _Mark(state, _needs(text), str(path))
        return found


def default_state_dir() -> pathlib.Path:
    return pathlib.Path(tempfile.gettempdir()) / "lemonaid-watch-briefs"


def state_stem(
    state_dir: pathlib.Path, parent: str, me: str, to: frozenset[str] = frozenset({"merge", "done"})
) -> pathlib.Path:
    key = f"{db.get_db_path().resolve()}\0{parent}\0{me}"
    key += "\0to:" + ",".join(sorted(to))
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


def open_watch(
    state_dir: pathlib.Path,
    parent: str,
    me: str,
    quiet: float,
    to: frozenset[str] = frozenset({"merge", "done"}),
) -> BriefsWatch:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_stem(state_dir, parent, me, to).with_suffix(".reported.json")
    current = _snapshot(parent)
    reported = _load(path)
    if reported is None:
        reported = current
        _save(path, reported)
    return BriefsWatch(parent, quiet, path, reported, current, time.monotonic(), to)


def _describe(child: str, previous: _Mark | None, current: _Mark) -> str:
    state = (
        f"Status: {previous.status} -> {current.status}"
        if previous and previous.status != current.status
        else f"Status: {current.status}"
    )
    ask = (
        f"; Needs: {current.needs or '(none)'}"
        if current.needs or (previous and current.needs != previous.needs)
        else ""
    )
    return f"{child}: {state}{ask} ({current.path})"


def poll(w: BriefsWatch, deliver: delivery.Deliver) -> bool:
    current = _snapshot(w.parent)
    absorbed = {
        child: mark
        for child, mark in current.items()
        if mark != (previous := w.reported.get(child))
        and (mark.status not in w.to or (previous and mark.status == previous.status))
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
    changed = {child: mark for child, mark in current.items() if mark != w.reported.get(child)}
    if not changed or time.monotonic() - w.pending_since < w.quiet:
        return False

    deliver(
        "\n".join(_describe(child, w.reported.get(child), mark) for child, mark in changed.items())
    )
    # Retain missing or unlinked briefs so their return alone does not repeat a report.
    w.reported = w.reported | current
    _save(w.reported_path, w.reported)
    return True
