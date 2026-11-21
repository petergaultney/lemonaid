"""Follow one Slack thread or channel for one lemon: fetch its new messages from the lemon's
cursor and deliver them.

A fetch happens when the gateway signals the conversation (`slack.wakes`), on the first poll,
so a restart catches up, every `fetch_every` while no gateway socket is up, and every
`_BACKSTOP` while one is, for what the socket does not report (a channel the user has not
joined). The cursor, the last message read, advances only after delivery. A first poll takes
the conversation as seen, unless the subscription's `after` names where to start. With a
`match`, only messages whose text it matches are delivered; the cursor passes the rest.

The subscription ends when the lemon's brief is done or the conversation has had no message for
`QUIET_DAYS`: the lemon hears it once, and its line leaves the brief's `## Watching`.
"""

import json
import re
import shlex
import time
from collections import abc
from pathlib import Path

from ..brief import lemon, verbs_cli, waiters
from ..inbox import db
from ..log import get_logger
from ..slack import api, fetch, permalink, session, signed_out, wake_text, wakes
from ..slack_config import SlackConfig
from . import cursors, delivery

QUIET_DAYS = 7
_BACKSTOP = 600.0

_log = get_logger("watch.slack_events")


def _state_path(directory: Path, conversation: permalink.Conversation) -> Path:
    return directory / f"{'-'.join(conversation.target)}.json"


def _load(path: Path) -> dict[str, str] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _quiet(latest: str) -> bool:
    return time.time() - float(latest) >= QUIET_DAYS * 86400


def _names(word: str, conversation: permalink.Conversation) -> bool:
    try:
        return permalink.parse(word).target == conversation.target
    except ValueError:
        return False


def _follows(command: str, conversation: permalink.Conversation) -> bool:
    """Whether a `## Watching` command follows *conversation*, by any link to it."""
    try:
        words = shlex.split(command)
    except ValueError:
        return False

    return words[:3] == ["lemonaid", "watch", "slack"] and any(
        _names(word, conversation) for word in words[3:]
    )


def _forget(lemon_id: str, conversation: permalink.Conversation) -> None:
    """Remove every `watch slack` line for *conversation* from *lemon_id*'s brief, if any."""
    with db.connect() as conn:
        path = lemon.brief_of(conn, lemon_id) if lemon_id else None
    if path is None or not path.is_file():
        return

    if error := verbs_cli.edit(
        path,
        lambda text: waiters.remove_where(text, lambda command: _follows(command, conversation)),
        preserve_existing=True,
    ):
        _log.warning("could not stop following %s in %s: %s", conversation.link, path, error)


def poller(
    conversation: permalink.Conversation,
    after: str,
    match: str,
    brief_done: bool,
    directory: Path,
    lemon_id: str,
    deliver: abc.Callable[[str], object],
    warn: abc.Callable[[str], object],
    settings: SlackConfig,
) -> abc.Callable[[], None]:
    """*directory* holds the lemon's Slack cursors. *after* is where a first fetch starts, else
    the newest message. *match*, a regex, picks the messages delivered; "" delivers all.
    *brief_done* ends it. *warn* gets why Slack cannot be read, at each try until a sign-in."""
    path = _state_path(directory, conversation)
    follower = lemon_id or directory.parent.name
    wanted = re.compile(match) if match else None
    seen: int | None = None  # the wake stamp at the last fetch; None fetches at once
    fetched_at = 0.0
    retry_at = 0.0  # after Slack could not be reached
    ended = False

    def end(reason: str) -> None:
        nonlocal ended
        noun, link = conversation.noun, conversation.link
        message = f"Stopped following Slack {noun} {link}: {reason}; its line left ## Watching"
        deliver(delivery.Labeled(message, f"stopped following a Slack {noun}"))
        ended = True
        _forget(lemon_id, conversation)
        path.unlink(missing_ok=True)

    def signed_out_notice(current: session.Session | None) -> None:
        warn(delivery.Labeled(signed_out.lemon_problem(current), "Slack sign-in needed"))

    def report(current: session.Session, messages: list[dict]) -> None:
        name = wake_text.namer(current)
        chosen = [m for m in messages if wanted is None or wanted.search(wake_text.plain(m, name))]
        if chosen:
            text = wake_text.describe(conversation, chosen, name, match)
            label = wake_text.label(conversation, chosen, name)
            deliver(delivery.Labeled(text, label, len(chosen), True))

    def read(current: session.Session, saved: dict[str, str] | None) -> None:
        nonlocal seen, fetched_at
        stamp = wakes.stamp(conversation.channel, conversation.ts)
        if saved is None and not after:
            start = fetch.latest(current, conversation)
            saved, found = {"cursor": start, "latest": start}, fetch.Fetched(start, start, [])
        else:
            saved = saved or {"cursor": after, "latest": after}
            found = fetch.after(current, conversation, saved["cursor"])
        seen, fetched_at = stamp, time.monotonic()
        signed_out.heard_again(directory.parent)
        if found.messages:
            report(current, found.messages)
        latest = max(saved["latest"], found.latest, key=permalink.order)
        cursors.write_json(path, {"cursor": found.cursor, "latest": latest})
        if _quiet(latest):
            end(f"nothing new in {QUIET_DAYS} days")

    def poll() -> None:
        nonlocal retry_at
        if ended:
            return

        if brief_done:
            end("your brief is done")
            return

        wakes.follow(conversation.channel, conversation.ts, follower)
        now, saved = time.monotonic(), _load(path)
        since = now - fetched_at
        due = (
            seen is None
            or wakes.stamp(conversation.channel, conversation.ts) != seen
            or since >= _BACKSTOP
            or (since >= settings.fetch_every and not wakes.gateway_up())
            or (saved is not None and _quiet(saved["latest"]))
        )
        if not due or now < retry_at:
            return

        current = session.load()
        if signed_out.problem(current):
            if current is None:
                signed_out.mark(None)
            signed_out_notice(current)
            retry_at = now + settings.fetch_every
            return

        assert current is not None  # problem() names a missing session
        try:
            read(current, saved)
        except api.Expired:
            signed_out.mark(current)
            signed_out_notice(current)
        except api.Unavailable as error:
            _log.info(
                "cannot read Slack %s %s now: %s", conversation.noun, conversation.link, error
            )
            retry_at = now + settings.fetch_every

    return poll
