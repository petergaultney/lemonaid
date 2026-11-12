"""Compare direct mentions of the user on PRs with what a lemon was last told.

The cursor holds `since`, the time of the last complete poll, `seen`, the mentions
already reported with their creation times, and `floor`, the time of the first poll:
nothing older is ever reported, however far the overlap reaches back. A poll reads notification threads updated
from `_MARGIN` before `since`, since GitHub can list a thread a little after its comment
appears; `seen` keeps the overlap from reporting a mention twice. The first poll takes
every current mention as seen, unless `backlog` asks for the last `_BACKLOG`.

Every PR thread the user participates in is read when it was updated in the window, not
only those whose reason is `mention`: a thread's reason is its latest, and a merge or a
later comment replaces it. A PR some live lemon already hears comments on is skipped
(`watched`).
"""

import datetime
import hashlib
import json
import pathlib
import typing as ty
from collections import abc

from . import clip, cursors, delivery, mention_comments, notifications

_MARGIN = datetime.timedelta(minutes=10)
_BACKLOG = datetime.timedelta(hours=24)
_EXCERPT = 200


class Cursor(ty.TypedDict):
    since: str
    floor: str
    seen: dict[str, str]  # mention id -> created_at


def iso(t: datetime.datetime) -> str:
    return t.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s: str) -> datetime.datetime:
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)


def state_stem(state_dir: pathlib.Path, scope: abc.Sequence[str], me: str) -> pathlib.Path:
    key = "\0".join(scope).lower() + (f"\0\0{me}" if me else "")
    return state_dir / ("mentions-" + hashlib.sha1(key.encode()).hexdigest()[:16])


def window(cursor: Cursor | None, now: datetime.datetime, backlog: bool) -> str | None:
    """Where to start reading notifications; None when the first poll takes all as seen."""
    if cursor is None:
        return iso(now - _BACKLOG) if backlog else None

    return iso(_parse(cursor["since"]) - _MARGIN)


def _describe(repo: str, number: int, title: str, m: mention_comments.Mention) -> str:
    quoted = "\n".join(f"> {line}" for line in clip.shorten(m.body.strip(), _EXCERPT).splitlines())
    return f'{repo} PR #{number} "{title}": {m.author} mentioned you ({m.where}): {m.url}\n{quoted}'


def events(
    cursor: Cursor | None,
    threads: abc.Iterable[notifications.Thread],
    read: abc.Callable[[str, int, str], mention_comments.Pull | None],
    watched: abc.Callable[[str, int], bool],
    scope: abc.Sequence[str],
    now: datetime.datetime,
    backlog: bool = False,
) -> tuple[list[str], Cursor]:
    """The lines to report and the cursor to save once they are delivered.

    A PR that can't be read leaves `since` where it was, so the next poll tries it again.
    """
    start = window(cursor, now, backlog)
    if start is None:
        return [], {"since": iso(now), "floor": iso(now), "seen": {}}

    floor = cursor["floor"] if cursor else start
    seen = dict(cursor["seen"]) if cursor else {}
    lines, complete = [], True
    for t in threads:
        number = t.pr_number
        if (
            number is None
            or t.updated_at < start
            or not notifications.in_scope(t.repo, scope)
            or watched(t.repo, number)
        ):
            continue

        if (pull := read(t.repo, number, start)) is None:
            complete = False
            continue

        for m in mention_comments.direct(pull, max(start, floor)):
            if m.id not in seen:
                seen[m.id] = m.created_at
                lines.append(_describe(t.repo, number, pull.title, m))
    since = iso(now) if complete else (cursor["since"] if cursor else iso(now - _BACKLOG))
    keep = iso(_parse(since) - 2 * _MARGIN)
    return lines, {
        "since": since,
        "floor": floor,
        "seen": {i: c for i, c in seen.items() if c >= keep},
    }


def _load(path: pathlib.Path) -> Cursor | None:
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return None

    return saved if isinstance(saved, dict) and "since" in saved else None


def poll(
    stem: pathlib.Path,
    scope: abc.Sequence[str],
    deliver: delivery.Deliver,
    watched: abc.Callable[[str, int], bool],
    backlog: bool = False,
) -> bool | None:
    """True if an event was delivered; None when GitHub couldn't be read. A delivery that
    raises leaves the cursor unchanged."""
    path = stem.with_suffix(".seen.json")
    cursor = _load(path)
    now = datetime.datetime.now(datetime.UTC)
    start = window(cursor, now, backlog)
    threads = notifications.fetch(start, participating=True) if start is not None else []
    if threads is None:
        return None

    lines, saved = events(cursor, threads, mention_comments.read, watched, scope, now, backlog)
    if lines:
        deliver(delivery.Labeled("\n\n".join(lines), "mentioned", len(lines), True))
    cursors.write_json(path, saved)
    return bool(lines)
