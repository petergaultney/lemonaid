"""Notification handlers for lemonaid."""

import json
import sqlite3
import subprocess
from collections import abc
from typing import Any, Literal

from . import cmux, tmux, wezterm
from .codex import channels as codex_channels
from .codex import processes
from .config import Config, load_config
from .inbox import db
from .lemon_watchers import watcher
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

    *not_after* rejects a pane in a tmux session younger than the record: tty
    names are reused, so after a reboot a recorded tty usually names some other
    pane entirely.
    """
    if switch_source == "tmux":
        try:
            session, pane_id = tmux.navigation.get_pane_for_tty(tty, socket, not_after)
        except tmux.navigation.TmuxUnavailable:
            return None

        return session is not None and pane_id is not None

    elif switch_source == "wezterm":
        workspace, pane_id = _resolve_pane_from_tty(tty)
        return workspace is not None and pane_id is not None

    elif switch_source in PER_SESSION_SOURCES:
        # Its tty alone cannot say; ask `where_sessions_are` instead.
        return None

    return False


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

    Otherwise the switch_source determines which built-in handler to use:
    - "tmux" -> use tmux switch-handler
    - "wezterm" -> use wezterm switch-handler
    - "cmux" -> use cmux switch-handler

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

    if switch_source == "tmux":
        return _handle_tmux(metadata, config, on_tmux_resume)
    elif switch_source == "wezterm":
        return _handle_wezterm(metadata, config)
    elif switch_source == "cmux":
        return _handle_cmux(metadata, config)

    return False


def _handle_cmux(metadata: dict[str, Any] | None, config: Config) -> bool:
    """Handle notification by focusing its cmux surface, or resuming a session that has none."""
    if metadata is None:
        return False

    try:
        target = locate_cmux(metadata)
    except cmux.navigation.CmuxUnavailable:
        return False

    channel = metadata.get("channel")
    if target == cmux.navigation.UNKNOWN:
        # Either answer could be wrong: a switch may land on a stranger, and a
        # recreate may start a second copy of a live session.
        _log.warning("not switching to %s: could not tell which surface runs it", channel)
        return False

    if target == cmux.navigation.AMBIGUOUS:
        # Recreating would add a third copy of a session that already has two.
        _log.warning("not switching to %s: several surfaces run it", channel)
        return False

    if target is None:
        return cmux.recreate.recreate(metadata, config)

    return cmux.navigation.switch_to_surface(target)


def locate_cmux(metadata: dict[str, Any]) -> cmux.navigation.Surface | str | None:
    """The cmux surface the session in *metadata* runs in; see `cmux.navigation.locate`."""
    return cmux.navigation.locate(metadata, _cmux_runs_harness)


def _cmux_runs_harness(metadata: dict[str, Any], tty: str) -> bool | None:
    return watcher.process_on_tty(tty, watcher.harness_process(metadata.get("channel", "")))


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

    return cmux.navigation.where(in_cmux, _cmux_runs_harness, reuse_sweep=not fresh)


def _handle_wezterm(metadata: dict[str, Any] | None, config: Config) -> bool:
    """Handle notification by switching to WezTerm workspace/pane."""
    if metadata is None:
        return False

    workspace = None
    pane_id = None

    if config.wezterm.resolve_pane == "metadata":
        # Use workspace/pane_id directly from metadata
        workspace = metadata.get("workspace")
        pane_id = metadata.get("pane_id")
    elif config.wezterm.resolve_pane == "tty":
        # Resolve from TTY by querying wezterm cli list
        tty = metadata.get("tty")
        if tty:
            workspace, pane_id = _resolve_pane_from_tty(tty)

    if workspace is None or pane_id is None:
        # Fallback to metadata if TTY resolution failed
        workspace = metadata.get("workspace")
        pane_id = metadata.get("pane_id")

    if workspace is None or pane_id is None:
        return False

    return wezterm.navigation.switch_to_pane(workspace, pane_id)


def _resolve_pane_from_tty(tty: str) -> tuple[str | None, int | None]:
    """Resolve workspace and pane_id from TTY name."""
    try:
        result = subprocess.run(
            ["wezterm", "cli", "list", "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
        panes = json.loads(result.stdout)

        for pane in panes:
            if pane.get("tty_name") == tty:
                return pane.get("workspace"), pane.get("pane_id")

    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        pass

    return None, None


class _Unknown(Exception):
    """`ps` could not say what runs on a pane's tty."""


def _runs(tty: str, harness: str) -> bool:
    found = watcher.process_on_tty(tty, harness)
    if found is None:
        raise _Unknown(tty)

    return found


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


def refresh_notification_location(notification: db.Notification) -> db.Notification:
    if notification.switch_source != "tmux" or not notification.channel.startswith("codex:"):
        return notification
    locations = codex_tmux_locations()
    if locations is None:
        return notification
    matches = locations.get(
        codex_channels.owner_id(notification.channel, notification.metadata, locations), []
    )
    if len(matches) != 1:
        return notification
    with db.connect() as conn:
        db.repair_location(conn, notification, matches[0])
        return db.get(conn, notification.id) or notification


def _handle_tmux(
    metadata: dict[str, Any] | None,
    config: Config,
    on_resume: abc.Callable[[str], None] | None = None,
) -> bool:
    """Handle notification by switching to its pane, or recreating a dead session."""
    if metadata is None:
        return False

    channel = metadata.get("channel", "")
    if channel.startswith("codex:"):
        locations = codex_tmux_locations()
        owner = codex_channels.owner_id(channel, metadata, locations or {})
        if locations is not None and owner in locations:
            matches = locations[owner]
            if len(matches) != 1:
                _log.warning("not switching to %s: no unique terminal owns its thread", channel)
                return False
            with db.connect() as conn:
                repair_tmux_locations(conn, {owner: matches})
            metadata.update(matches[0])

    try:
        session, pane_id = tmux.recorded_pane.locate(metadata)
    except tmux.navigation.TmuxUnavailable as error:
        _log.warning("not switching to %s: %s", metadata.get("channel"), error)
        return False

    # Directory lookup is only for rows without a recorded identity; it cannot
    # override evidence that a known pane is gone.
    if (session is None or pane_id is None) and not tmux.recorded_pane.has_identity(metadata):
        cwd = metadata.get("cwd")
        if cwd:
            harness = watcher.harness_process(metadata.get("channel", ""))
            try:
                session, pane_id = tmux.navigation.get_pane_for_cwd(
                    cwd, lambda pane_tty: _runs(pane_tty, harness)
                )
            except _Unknown:
                # Either answer could be wrong: a switch may land on a stranger,
                # and a recreate may start a second copy of a live session.
                _log.warning("not switching to %s: could not tell which pane runs %s", cwd, harness)
                return False

    if session == tmux.navigation.AMBIGUOUS:
        # One of the matches is the right session, so recreating would add a
        # duplicate to a directory that already has too many.
        _log.warning(
            "not switching to %s: its directory belongs to several sessions",
            metadata.get("cwd"),
        )
        return False

    if session is None or pane_id is None:
        if on_resume is None:
            return tmux.recreate.recreate(metadata, config)

        tty = tmux.recreate.resume(metadata, config)
        if tty is None:
            return False

        on_resume(tty)
        return True

    switched = tmux.navigation.switch_to_pane(session, pane_id)
    _log.info(
        "tmux jump channel=%s session=%s pane=%s switched=%s",
        metadata.get("channel"),
        session,
        pane_id,
        switched,
    )
    return switched
