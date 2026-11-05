"""Notification handlers for lemonaid."""

import sqlite3
import subprocess
from collections import abc
from typing import Any, Literal

from . import cmux, front_end, tmux
from .codex import channels as codex_channels
from .codex import processes
from .config import Config, load_config
from .inbox import db
from .log import get_logger

_log = get_logger("handlers")


# Switch sources whose sessions can outlive their tty, so the watcher asks them
# where each session is rather than whether its recorded tty is still there.
PER_SESSION_SOURCES = frozenset({"cmux"})


def check_pane_exists_by_tty(
    tty: str, switch_source: str, socket: str | None = None, not_after: float | None = None
) -> bool | None:
    """Whether a pane still exists, or None if that could not be determined.

    The watcher archives on False, so "tmux did not answer" has to be a third
    answer rather than folding into "no pane". Used by watcher for auto-archive.

    *socket* names the server the session was recorded on. Without it the
    question is put to the caller's own server, where a pane living on a
    different one is absent for a reason that has nothing to do with it.

    *not_after* rejects a pane younger than the record, since tty names are reused.
    """
    found = front_end.terminals.named(switch_source)
    return found.exists(tty, socket, not_after) if found else False


def handle_notification(
    metadata: dict[str, Any] | None,
    config: Config | None = None,
    switch_source: str | None = None,
    on_tmux_resume: abc.Callable[[str], None] | None = None,
) -> bool:
    """
    Handle a notification by switching to its source.

    An `open_uri` in the metadata wins: the row names a document rather than a
    session, so it is handed to `open` instead of a switch-handler.

    Otherwise the front end the switch_source names shows it.

    Returns True if handled successfully, False otherwise.
    """
    if config is None:
        config = load_config()

    # A row naming a document opens it in whichever app owns its URI scheme.
    # Nothing is running behind such a row, so there is no pane to switch to,
    # and the switch_source still decides where the row is *listed*.
    uri = (metadata or {}).get("open_uri")
    if uri:
        _log.info("opening %s", uri)
        return subprocess.run(["open", uri], check=False).returncode == 0

    found = front_end.terminals.named(switch_source)
    return found.show(metadata, config, on_tmux_resume) if found else False


def show_tmux_keeping_focus(
    metadata: dict[str, Any], config: Config, switch_source: str | None
) -> bool:
    """`handle_notification` for an existing tmux pane, leaving focus where it is."""
    return tmux.keep_focus.show(
        metadata, lambda: handle_notification(metadata, config, switch_source=switch_source)
    )


def where_sessions_are(
    sessions: list[tuple[str | None, dict[str, Any]]], fresh: bool = False
) -> dict[str, str | Literal[False] | None]:
    """For each (switch_source, metadata) of a PER_SESSION_SOURCES session, keyed by channel:
    the tty it runs on now, False if it is gone, or None if that could not be told.

    *metadata* carries the row's `channel`. Sessions of other sources are left out.
    *fresh* asks the backend not to answer from anything it remembers, for a
    decision a person is waiting on rather than a watcher tick.
    """
    in_cmux = [metadata for source, metadata in sessions if source == "cmux"]
    if not in_cmux:
        return {}

    return cmux.navigation.where(in_cmux, front_end.cmux.runs_harness, reuse_sweep=not fresh)


def codex_tmux_locations() -> dict[str, list[dict[str, Any]]] | None:
    threads = processes.thread_ttys()
    if threads is None:
        return None
    try:
        panes = tmux.recorded_pane.pane_metadata()
    except tmux.navigation.TmuxUnavailable:
        return None
    return {
        thread: [location for tty in ttys for location in panes.get(tty, [])]
        for thread, ttys in threads.items()
    }


def repair_tmux_locations(
    conn: sqlite3.Connection, locations: dict[str, list[dict[str, Any]]] | None = None
) -> int:
    if locations is None:
        locations = codex_tmux_locations()
    if locations is None:
        return 0
    repaired = codex_channels.repair_duplicates(conn, locations)
    for notification in db.get_active(conn, switch_source="tmux"):
        if not notification.channel.startswith("codex:"):
            continue
        matches = locations.get(
            codex_channels.owner_id(notification.channel, notification.metadata, locations), []
        )
        if len(matches) == 1 and db.repair_location(conn, notification, matches[0]):
            repaired += 1
            _log.info(
                "repaired tmux location channel=%s pane=%s",
                notification.channel,
                matches[0]["tmux_pane_identity"][0],
            )
    return repaired
