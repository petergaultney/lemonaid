"""WezTerm integration for lemonaid."""

import base64
import json
import os
import subprocess
from pathlib import Path


def get_state_path() -> Path:
    """Get the path to the lemonaid state directory."""
    state_dir = Path.home() / ".local" / "state" / "lemonaid"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_back_file() -> Path:
    """Get the path to the back state file."""
    return get_state_path() / "back.json"


def get_current_pane() -> tuple[str | None, int | None]:
    """Get the currently active WezTerm workspace and pane_id.

    Uses WEZTERM_PANE env var to identify the current pane, then looks up
    its workspace from the pane list.
    """
    # Get pane ID from environment - this is authoritative
    pane_id_str = os.environ.get("WEZTERM_PANE")
    if not pane_id_str:
        return None, None

    try:
        pane_id = int(pane_id_str)
    except ValueError:
        return None, None

    # Look up the workspace for this pane
    try:
        result = subprocess.run(
            ["wezterm", "cli", "list", "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
        panes = json.loads(result.stdout)

        for pane in panes:
            if pane.get("pane_id") == pane_id:
                return pane.get("workspace"), pane_id

    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        pass

    return None, None


def save_back_location(workspace: str, pane_id: int) -> None:
    """Save a location for the 'back' command."""
    back_file = get_back_file()
    data = {"workspace": workspace, "pane_id": pane_id}
    back_file.write_text(json.dumps(data))


def load_back_location() -> tuple[str | None, int | None]:
    """Load the saved 'back' location."""
    back_file = get_back_file()
    if not back_file.exists():
        return None, None

    try:
        data = json.loads(back_file.read_text())
        return data.get("workspace"), data.get("pane_id")
    except (json.JSONDecodeError, KeyError):
        return None, None


def switch_to_pane(workspace: str, pane_id: int, save_current: bool = True) -> bool:
    """
    Switch to a WezTerm workspace and pane via escape sequence.

    If save_current=True, saves the current location for 'back' command.
    """
    # Save current location before switching
    if save_current:
        current_ws, current_pane = get_current_pane()
        if current_ws and current_pane:
            save_back_location(current_ws, current_pane)

    # Send the escape sequence to switch
    value = f"{workspace}|{pane_id}"
    encoded = base64.b64encode(value.encode()).decode()
    seq = f"\033]1337;SetUserVar=switch_workspace_and_pane={encoded}\007"

    try:
        fd = os.open("/dev/tty", os.O_WRONLY)
        try:
            os.write(fd, seq.encode())
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


def go_back() -> bool:
    """Switch back to the previously saved location."""
    workspace, pane_id = load_back_location()
    if workspace is None or pane_id is None:
        return False

    # Don't save current as new back location (would cause ping-pong)
    return switch_to_pane(workspace, pane_id, save_current=False)


def swap_back_location(
    current_workspace: str, current_pane_id: int
) -> tuple[str | None, int | None]:
    """Atomically swap: save current location, return previous target.

    This is designed to be called from WezTerm Lua to minimize Lua code.
    Returns (workspace, pane_id) of the target to switch to, or (None, None).
    """
    # Load target before overwriting
    target_workspace, target_pane_id = load_back_location()

    # Save current as new back location (enables ping-pong)
    save_back_location(current_workspace, current_pane_id)

    return target_workspace, target_pane_id
