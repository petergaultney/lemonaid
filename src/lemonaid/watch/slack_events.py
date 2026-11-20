"""Follow one Slack thread for one lemon: fetch its new replies from the lemon's cursor and
deliver them.

A fetch happens when the gateway signals the thread (`slack.wakes`), on the first poll, so a
restart catches up, and every `fetch_every` while no gateway socket is up. The cursor, the last
reply delivered, advances only after delivery. A first poll takes the thread as seen, unless
the subscription's `after` names where to start.

The subscription ends when the lemon's brief is done or the thread has had no reply for
`QUIET_DAYS`: the lemon hears it once, and its line leaves the brief's `## Watching`.
"""

import json
import shlex
import time
from collections import abc
from pathlib import Path

from ..brief import lemon, verbs_cli, waiters
from ..inbox import db
from ..log import get_logger
from ..slack import api, permalink, replies, session, signed_out, wakes
from ..slack_config import SlackConfig
from . import cursors, delivery

QUIET_DAYS = 7

_log = get_logger("watch.slack_events")


def _state_path(directory: Path, thread: permalink.Thread) -> Path:
    return directory / f"{thread.channel}-{thread.ts}.json"


def _load(path: Path) -> dict[str, str] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _quiet(latest: str) -> bool:
    return time.time() - float(latest) >= QUIET_DAYS * 86400


def _names(word: str, thread: permalink.Thread) -> bool:
    try:
        found = permalink.parse(word)
    except ValueError:
        return False

    return (found.channel, found.ts) == (thread.channel, thread.ts)


def _follows(command: str, thread: permalink.Thread) -> bool:
    """Whether a `## Watching` command follows *thread*, by any link to it."""
    try:
        words = shlex.split(command)
    except ValueError:
        return False

    return words[:3] == ["lemonaid", "watch", "slack"] and any(
        _names(word, thread) for word in words[3:]
    )


def _forget(lemon_id: str, thread: permalink.Thread) -> None:
    """Remove every `watch slack` line for *thread* from *lemon_id*'s brief, if it has one."""
    with db.connect() as conn:
        path = lemon.brief_of(conn, lemon_id) if lemon_id else None
    if path is None or not path.is_file():
        return

    if error := verbs_cli.edit(
        path,
        lambda text: waiters.remove_where(text, lambda command: _follows(command, thread)),
        preserve_existing=True,
    ):
        _log.warning("could not stop following %s in %s: %s", thread.link, path, error)


def _deliver_replies(
    thread: permalink.Thread,
    found: abc.Sequence[dict],
    name: abc.Callable[[str], str],
    deliver: abc.Callable[[str], object],
) -> None:
    label = (
        f"Slack reply from {replies.author(found[0], name)}"
        if len(found) == 1
        else f"{len(found)} Slack replies"
    )
    deliver(delivery.Labeled(replies.describe(thread, found, name), label, len(found), True))


def poller(
    thread: permalink.Thread,
    after: str,
    brief_done: bool,
    directory: Path,
    lemon_id: str,
    deliver: abc.Callable[[str], object],
    settings: SlackConfig,
) -> abc.Callable[[], None]:
    """*directory* holds the lemon's Slack cursors; its parent, the lemon's notices. *after* is
    where a first fetch starts, else the thread's latest reply. *brief_done* ends it."""
    path = _state_path(directory, thread)
    follower = lemon_id or directory.parent.name
    seen: int | None = None  # the wake stamp at the last fetch; None fetches at once
    next_fetch = 0.0  # when to fetch again while no gateway socket is up
    retry_at = 0.0  # after Slack could not be reached
    ended = False

    def end(reason: str) -> None:
        nonlocal ended
        message = (
            f"Stopped following Slack thread {thread.link}: {reason}; its line left ## Watching"
        )
        deliver(delivery.Labeled(message, "stopped following a Slack thread"))
        ended = True
        _forget(lemon_id, thread)
        path.unlink(missing_ok=True)

    def signed_out_notice(problem: str) -> None:
        signed_out.tell_once(
            directory.parent, delivery.Labeled(problem, "Slack sign-in needed"), deliver
        )

    def fetch(current: session.Session, saved: dict[str, str] | None) -> None:
        nonlocal seen, next_fetch
        stamp = wakes.stamp(thread.channel, thread.ts)
        if saved is None and not after:
            start = replies.latest(current, thread)
            saved, found = {"cursor": start, "latest": start}, replies.Fetched(start, [])
        else:
            saved = saved or {"cursor": after, "latest": after}
            found = replies.after(current, thread, saved["cursor"])
        seen, next_fetch = stamp, time.monotonic() + settings.fetch_every
        signed_out.heard_again(directory.parent)
        if found.replies:
            _deliver_replies(thread, found.replies, replies.namer(current), deliver)
        latest = max(saved["latest"], found.latest, key=permalink.order)
        cursor = found.replies[-1]["ts"] if found.replies else saved["cursor"]
        cursors.write_json(path, {"cursor": cursor, "latest": latest})
        if _quiet(latest):
            end(f"no reply in {QUIET_DAYS} days")

    def poll() -> None:
        nonlocal retry_at
        if ended:
            return

        if brief_done:
            end("your brief is done")
            return

        wakes.follow(thread.channel, thread.ts, follower)
        now, saved = time.monotonic(), _load(path)
        due = (
            seen is None
            or wakes.stamp(thread.channel, thread.ts) != seen
            or (now >= next_fetch and not wakes.gateway_up())
            or (saved is not None and _quiet(saved["latest"]))
        )
        if not due or now < retry_at:
            return

        current = session.load()
        if problem := signed_out.problem(current):
            if current is None:
                signed_out.mark(None)
            signed_out_notice(problem)
            retry_at = now + settings.fetch_every
            return

        assert current is not None  # problem() names a missing session
        try:
            fetch(current, saved)
        except api.Expired:
            signed_out.mark(current)
            signed_out_notice(signed_out.problem(current))
        except api.Unavailable as error:
            _log.info("cannot read Slack thread %s now: %s", thread.link, error)
            retry_at = now + settings.fetch_every

    return poll
