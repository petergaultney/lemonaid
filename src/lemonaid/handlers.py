"""Notification handlers for lemonaid."""

import json
import subprocess
from typing import Any

from . import tmux, wezterm
from .config import Config, load_config
from .lemon_watchers import watcher
from .log import get_logger

_log = get_logger("handlers")


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

    return False


def handle_notification(
    metadata: dict[str, Any] | None,
    config: Config | None = None,
    switch_source: str | None = None,
) -> bool:
    """
    Handle a notification by switching to its source.

    The switch_source determines which built-in handler to use:
    - "tmux" -> use tmux switch-handler
    - "wezterm" -> use wezterm switch-handler

    Returns True if handled successfully, False otherwise.
    """
    if config is None:
        config = load_config()

    if switch_source == "tmux":
        return _handle_tmux(metadata, config)
    elif switch_source == "wezterm":
        return _handle_wezterm(metadata, config)

    return False


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


def _handle_tmux(metadata: dict[str, Any] | None, config: Config) -> bool:
    """Handle notification by switching to its pane, or recreating a dead session."""
    if metadata is None:
        return False

    session, pane_id = None, None

    # Try to resolve pane from TTY first (most reliable)
    tty = metadata.get("tty")
    if tty:
        session, pane_id = tmux.navigation.get_pane_for_tty(tty)

    # Fallback: resolve from cwd, for rows with no tty (a Codex session hosted on
    # the app-server daemon records none) or whose tty is no longer a pane.
    if session is None or pane_id is None:
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
        return tmux.recreate.recreate(metadata, config)

    return tmux.navigation.switch_to_pane(session, pane_id)
