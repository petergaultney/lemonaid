"""Which lemon a command means: the caller itself, or one named by ID, channel, or brief."""

import functools
import os
import sqlite3
from collections import abc
from pathlib import Path

from .. import groups
from ..inbox import self_session
from ..inbox.channel import channel_id
from ..log import get_logger
from . import attached, identity, store

_log = get_logger("brief.lemon")


def self_channel(conn: sqlite3.Connection, explicit: str = "", fallback: str = "") -> str:
    """The caller's channel, from *explicit*, the harness's environment, or its tmux pane.

    Raises LookupError when none of those names one and there is no *fallback*.
    """
    channel = explicit or os.environ.get("LEMONAID_CHANNEL", "")
    if channel:
        if channel.startswith("codex:"):
            from ..codex import channels

            return channels.for_session(conn, channel.removeprefix("codex:"))
        return channel

    if session_id := os.environ.get("CLAUDE_CODE_SESSION_ID"):
        return channel_id("claude", session_id)

    if session_id := os.environ.get("CODEX_THREAD_ID"):
        from ..codex import channels

        return channels.for_session(conn, session_id)

    if pane_id := os.environ.get("TMUX_PANE"):
        where = self_session.pane_location(pane_id)
        if where is None:
            if fallback:
                return fallback

            raise LookupError(f"Could not ask tmux where pane {pane_id} is")

        channel, error = self_session.resolve(conn, where)
        if error:
            if fallback:
                return fallback

            raise LookupError(error)

        return channel

    if fallback:
        return fallback

    raise LookupError("Cannot identify this lemon; set LEMONAID_CHANNEL or use a tmux pane")


def current(conn: sqlite3.Connection, lemon_id: str) -> str:
    """*lemon_id*, or the Lemon-ID it was rerolled to."""
    row = conn.execute(
        "SELECT lemon_id FROM lemon_aliases WHERE old_id = ?", (lemon_id,)
    ).fetchone()
    return row["lemon_id"] if row else lemon_id


def _brief_ids(entries: abc.Iterable[attached.Attachment]) -> dict[Path, str]:
    found = {}
    for entry in entries:
        if not entry.channel or not entry.path.is_file():
            continue
        try:
            found[entry.path] = identity.from_path(entry.path)
        except ValueError as error:
            _log.warning("Skipping invalid brief %s: %s", entry.path, error)
    return found


def _find(
    conn: sqlite3.Connection,
    all_briefs: list[attached.Attachment],
    brief_ids: abc.Callable[[], dict[Path, str]],
    target: str,
) -> attached.Attachment:
    if target.startswith("codex:"):
        from ..codex import channels

        target = channels.for_session(conn, target.removeprefix("codex:"))
    found = [entry for entry in all_briefs if entry.channel == target and entry.channel]
    if not found and identity.valid(target):
        lemon_id = current(conn, target)
        found = [
            entry
            for entry in all_briefs
            if entry.channel and brief_ids().get(entry.path) == lemon_id
        ]

    if not found:
        found = [
            entry
            for entry in all_briefs
            if entry.channel and (entry.path.stem == target or entry.path.name == target)
        ]
    if len(found) != 1:
        raise LookupError(f"Expected one attached lemon for {target!r}; found {len(found)}")

    return found[0]


def finder(conn: sqlite3.Connection) -> abc.Callable[[str], attached.Attachment]:
    """`attachment` for many targets, reading the attachments and each brief once."""
    attached.claim_pending(conn)
    all_briefs = attached.everything(conn)
    return functools.partial(
        _find, conn, all_briefs, functools.cache(lambda: _brief_ids(all_briefs))
    )


def attachment(
    conn: sqlite3.Connection, target: str, *, claim_pending: bool = True
) -> attached.Attachment:
    """The one attached lemon *target* names: a channel, a Lemon-ID (or an old one), or a brief's name."""
    if claim_pending:
        attached.claim_pending(conn)
    all_briefs = attached.everything(conn)
    return _find(conn, all_briefs, functools.cache(lambda: _brief_ids(all_briefs)), target)


def brief_of(conn: sqlite3.Connection, lemon_id: str) -> Path | None:
    """The brief registered for *lemon_id* (or the ID it was rerolled to), attached or not."""
    row = conn.execute(
        "SELECT path FROM lemon_identities WHERE lemon_id = ?", (current(conn, lemon_id),)
    ).fetchone()
    return Path(row["path"]) if row else None


def own_id(conn: sqlite3.Connection, explicit_channel: str = "") -> str:
    """The caller's Lemon-ID, from the brief attached to its channel."""
    channel = self_channel(conn, explicit_channel)
    attached.claim_pending(conn)
    path = attached.by_channel(conn, [channel]).get(channel)
    if path is None:
        raise LookupError(f"No brief attached to {channel!r}, so it has no Lemon-ID")

    return identity.ensure(conn, path)


def lemon_id(conn: sqlite3.Connection, target: str) -> str:
    """The Lemon-ID *target* names: an ID lemonaid knows, a channel, or a brief's name or path.

    Unlike `attachment`, a brief need not be attached yet, so a child waiting
    for its lemon to start can be named.
    """
    if identity.valid(target) and brief_of(conn, target) is not None:
        return current(conn, target)

    try:
        found = attachment(conn, target)
        lemon = identity.ensure(conn, found.path)
        if found.channel == target:
            groups.store.rekey(conn, target, lemon)  # it was grouped by channel before its brief

        return lemon
    except LookupError:
        path = store.resolve(target)
        if not store.outside_error(path) and path.is_file():
            return identity.ensure(conn, path)

        raise
