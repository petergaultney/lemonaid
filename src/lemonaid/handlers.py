"""Notification handlers for lemonaid."""

import base64
import json
import os
import subprocess
from typing import Any

from .config import Config, load_config


def handle_notification(
    channel: str,
    metadata: dict[str, Any] | None,
    config: Config | None = None,
) -> bool:
    """
    Handle a notification based on config.

    Returns True if handled successfully, False otherwise.
    """
    if config is None:
        config = load_config()

    handler_name = config.get_handler(channel)
    if handler_name is None:
        return False

    if handler_name == "wezterm":
        return _handle_wezterm(metadata, config)
    elif handler_name.startswith("exec:"):
        cmd = handler_name[5:]  # Strip "exec:" prefix
        return _handle_exec(cmd, channel, metadata)
    else:
        # Unknown handler - silently fail
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

    return _switch_wezterm_pane(workspace, pane_id)


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


def _switch_wezterm_pane(workspace: str, pane_id: int) -> bool:
    """Switch to a WezTerm workspace and pane via escape sequence."""
    value = f"{workspace}|{pane_id}"
    encoded = base64.b64encode(value.encode()).decode()
    seq = f"\033]1337;SetUserVar=switch_workspace_and_pane={encoded}\007"

    try:
        # Write directly to /dev/tty to bypass any stdout redirection (e.g., from TUIs)
        fd = os.open("/dev/tty", os.O_WRONLY)
        try:
            os.write(fd, seq.encode())
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


def _handle_exec(cmd: str, channel: str, metadata: dict[str, Any] | None) -> bool:
    """Handle notification by executing a command."""
    env = os.environ.copy()
    env["LEMONAID_CHANNEL"] = channel
    if metadata:
        env["LEMONAID_METADATA"] = json.dumps(metadata)

    try:
        subprocess.run(cmd, shell=True, env=env, check=False)
        return True
    except Exception:
        return False
