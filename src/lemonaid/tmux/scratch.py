"""Scratch pane functionality for lemonaid.

Provides a toggleable "always-on" lma pane that can be shown/hidden
without restarting the TUI (avoiding startup latency).

State is tracked per tmux server in ~/.local/state/lemonaid/scratch-pane-<server>.json
to avoid conflicts when running multiple tmux servers.
"""

import json
import os
import subprocess

from . import get_state_path

_SCRATCH_SESSION = "_lma_scratch"


def _get_server_name() -> str:
    """Get the tmux server name from TMUX env var.

    TMUX format: /path/to/socket,pid,pane_index
    Returns the socket basename (e.g., 'default' for the default server).
    """
    tmux_env = os.environ.get("TMUX", "")
    if tmux_env:
        socket_path = tmux_env.split(",")[0]
        return os.path.basename(socket_path)
    return "default"


def _get_state() -> dict | None:
    """Load scratch pane state (pane_id of the lma pane)."""
    path = get_state_path() / f"scratch-pane-{_get_server_name()}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, KeyError):
        return None


def _save_state(pane_id: str) -> None:
    """Save scratch pane state."""
    path = get_state_path() / f"scratch-pane-{_get_server_name()}.json"
    path.write_text(json.dumps({"pane_id": pane_id}))


def _clear_state() -> None:
    """Clear scratch pane state."""
    path = get_state_path() / f"scratch-pane-{_get_server_name()}.json"
    if path.exists():
        path.unlink()


def _pane_exists(pane_id: str) -> bool:
    """Check if a pane still exists."""
    result = subprocess.run(
        ["tmux", "display-message", "-t", pane_id, "-p", "#{pane_id}"],
        capture_output=True,
    )
    return result.returncode == 0


def _get_pane_window(pane_id: str) -> str | None:
    """Get the window ID that contains a pane."""
    result = subprocess.run(
        ["tmux", "display-message", "-t", pane_id, "-p", "#{window_id}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _get_current_window() -> str | None:
    """Get the current window ID."""
    result = subprocess.run(
        ["tmux", "display-message", "-p", "#{window_id}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _session_exists() -> bool:
    """Check if the scratch tmux session exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", _SCRATCH_SESSION],
        capture_output=True,
    )
    return result.returncode == 0


def _get_session_pane() -> str | None:
    """Get the pane ID of the first pane in the scratch session."""
    result = subprocess.run(
        ["tmux", "list-panes", "-t", _SCRATCH_SESSION, "-F", "#{pane_id}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip().split("\n")[0]
    return None


def _create_pane() -> str:
    """Create the scratch pane with lma running. Returns pane_id."""
    # Check if session already exists (recovery: state file lost but session exists)
    if _session_exists():
        pane_id = _get_session_pane()
        if pane_id:
            _save_state(pane_id)
            return pane_id

    # Create a new session with lma in scratch mode
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", _SCRATCH_SESSION, "lma", "--scratch"],
        check=True,
    )

    result = subprocess.run(
        ["tmux", "list-panes", "-t", _SCRATCH_SESSION, "-F", "#{pane_id}"],
        capture_output=True,
        text=True,
        check=True,
    )
    pane_id = result.stdout.strip()
    _save_state(pane_id)
    return pane_id


def _show(pane_id: str, height: str) -> bool:
    """Join the scratch pane into current window as a top split."""
    result = subprocess.run(
        ["tmux", "join-pane", "-v", "-b", "-l", height, "-s", pane_id],
        capture_output=True,
    )
    return result.returncode == 0


def _hide(pane_id: str) -> bool:
    """Break the scratch pane to its own window."""
    result = subprocess.run(
        ["tmux", "break-pane", "-d", "-s", pane_id],
        capture_output=True,
    )
    return result.returncode == 0


def _create_and_show(height: str) -> str:
    """Create a fresh scratch pane and show it."""
    _clear_state()
    if _session_exists():
        subprocess.run(
            ["tmux", "kill-session", "-t", _SCRATCH_SESSION],
            capture_output=True,
        )
    pane_id = _create_pane()
    _show(pane_id, height)
    return "created"


def toggle_scratch(height: str = "30%") -> str:
    """Toggle the scratch lma pane. Returns 'shown', 'hidden', or 'created'."""
    state = _get_state()

    if state is None:
        return _create_and_show(height)

    pane_id = state["pane_id"]

    if not _pane_exists(pane_id):
        return _create_and_show(height)

    current_window = _get_current_window()
    pane_window = _get_pane_window(pane_id)

    if pane_window == current_window:
        if not _hide(pane_id):
            return _create_and_show(height)
        return "hidden"
    else:
        if not _show(pane_id, height):
            return _create_and_show(height)
        return "shown"
