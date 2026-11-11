"""Compare the user's unread GitHub notification threads with what a lemon was last told.

The cursor maps each unread thread's id to the `updated_at` the lemon was told about. A
thread is reported when it is new, or when it has activity since; a thread read in the
meantime leaves the cursor. The first poll takes every unread thread as seen, unless
`backlog` asks for them.
"""

import hashlib
import json
import pathlib
from collections import abc

from . import cursors, delivery, notifications

Seen = dict[str, str]


def state_stem(state_dir: pathlib.Path, scope: abc.Sequence[str], me: str) -> pathlib.Path:
    key = "\0".join(scope).lower() + (f"\0\0{me}" if me else "")
    return state_dir / ("notifications-" + hashlib.sha1(key.encode()).hexdigest()[:16])


def _describe(t: notifications.Thread) -> str:
    number = t.pr_number or t.issue_number
    return f'- {t.repo}{f"#{number}" if number else ""} ({t.reason}) "{t.title}" [thread {t.id}]'


def events(
    seen: Seen | None,
    threads: abc.Iterable[notifications.Thread],
    scope: abc.Sequence[str],
    backlog: bool = False,
) -> tuple[list[str], Seen]:
    """The lines to report and the cursor to save once they are delivered."""
    unread = [t for t in threads if t.unread and notifications.in_scope(t.repo, scope)]
    now = {t.id: t.updated_at for t in unread}
    if seen is None and not backlog:
        return [], now

    return [_describe(t) for t in unread if (seen or {}).get(t.id, "") < t.updated_at], now


def _load(path: pathlib.Path) -> Seen | None:
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return None

    return saved if isinstance(saved, dict) else None


def poll(
    stem: pathlib.Path, scope: abc.Sequence[str], deliver: delivery.Deliver, backlog: bool = False
) -> bool | None:
    """True if an event was delivered; None when GitHub couldn't be read. A delivery that
    raises leaves the cursor unchanged."""
    path = stem.with_suffix(".seen.json")
    if (threads := notifications.fetch(unread=True)) is None:
        return None

    lines, now = events(_load(path), threads, scope, backlog)
    if lines:
        deliver(
            "\n".join(
                [
                    f"{len(lines)} GitHub notification thread(s) new or active since last told;"
                    " triage with `lemonaid github notifications list --json`:",
                    *lines,
                ]
            )
        )
    cursors.write_json(path, now)
    return bool(lines)
