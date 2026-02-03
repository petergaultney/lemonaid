"""Notification handlers for lemonaid."""

import json
import subprocess
from typing import Any

from . import tmux, wezterm
from .config import Config, load_config


def check_pane_exists_by_tty(tty: str, switch_source: str) -> bool:
    """Check if a pane still exists given its TTY and switch source.

    Lower-level helper that just needs TTY. Used by watcher for auto-archive.
    """
    if switch_source == "tmux":
        session, pane_id = tmux.get_pane_for_tty(tty)
        return session is not None and pane_id is not None

    elif switch_source == "wezterm":
        workspace, pane_id = _resolve_pane_from_tty(tty)
        return workspace is not None and pane_id is not None

    return False


def handle_notification(
    metadata: dict[str, Any] | None,
    config: Config | None = None,
    switch_source: str | None = None,
) -> str | None:
    """
    Handle a notification by switching to its source.

    The switch_source determines which built-in handler to use:
    - "tmux" -> use tmux switch-handler
    - "wezterm" -> use wezterm switch-handler
    - "slack" -> use slack switch-handler

    Returns:
        "handled" - success, TUI decides what to do based on switch_source
        "archive" - success, TUI should archive the notification
        "skip" - success but TUI should not mark read or archive
        None - failed to handle
    """
    if config is None:
        config = load_config()

    if switch_source == "tmux":
        return "handled" if _handle_tmux(metadata) else None
    elif switch_source == "wezterm":
        return "handled" if _handle_wezterm(metadata, config) else None
    elif switch_source == "slack":
        return _handle_slack(metadata, config)

    return None


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

    return wezterm.switch_to_pane(workspace, pane_id)


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


def _handle_slack(metadata: dict[str, Any] | None, config: Config) -> str | None:
    """Handle notification by opening Slack, with deep link if possible.

    Tries to construct a slack:// deep link URL to open directly to the
    conversation. Falls back to just activating Slack if lookup fails.

    Returns:
        "archive" - opened with deep link, notification should be archived
        "skip" - opened Slack app only, don't mark read or archive
        None - failed to open
    """
    # Try to construct a deep link
    url = None
    if metadata:
        workspace = metadata.get("workspace", "")
        channel_name = metadata.get("title", "")  # title is channel/DM name
        if workspace and channel_name:
            result = config.slack.lookup_channel(workspace, channel_name)
            if result:
                team_id, channel_id = result
                url = f"slack://channel?team={team_id}&id={channel_id}"

    try:
        if url:
            subprocess.run(["open", url], check=True)
            return "archive"
        else:
            subprocess.run(["open", "-a", "Slack"], check=True)
            return "skip"
    except subprocess.CalledProcessError:
        return None


def _handle_tmux(metadata: dict[str, Any] | None) -> bool:
    """Handle notification by switching to tmux session/pane."""
    if metadata is None:
        return False

    # Resolve pane from TTY
    tty = metadata.get("tty")
    if not tty:
        return False

    session, pane_id = tmux.get_pane_for_tty(tty)
    if session is None or pane_id is None:
        return False

    return tmux.switch_to_pane(session, pane_id)
