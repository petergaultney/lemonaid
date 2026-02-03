"""tmux integration for lemonaid."""

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
    return get_state_path() / "tmux-back.json"


def is_inside_tmux() -> bool:
    """Check if we're running inside tmux."""
    return bool(os.environ.get("TMUX"))


def get_current_location() -> tuple[str | None, str | None]:
    """Get the current tmux session and pane target.

    Returns (session_name, pane_id) where pane_id is like '%5'.
    The pane_id uniquely identifies a pane across all sessions.
    """
    if not is_inside_tmux():
        return None, None

    # TMUX_PANE gives us the pane ID directly (e.g., '%5')
    pane_id = os.environ.get("TMUX_PANE")
    if not pane_id:
        return None, None

    # Get the session name for this pane
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-t", pane_id, "-p", "#{session_name}"],
            capture_output=True,
            text=True,
            check=True,
        )
        session_name = result.stdout.strip()
        return session_name, pane_id
    except subprocess.CalledProcessError:
        return None, None


def get_pane_for_tty(tty: str) -> tuple[str | None, str | None]:
    """Find the tmux session and pane for a given TTY.

    Returns (session_name, pane_id) or (None, None) if not found.
    """
    try:
        # List all panes with their TTY and pane ID
        result = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{pane_tty}|#{session_name}|#{pane_id}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) == 3:
                pane_tty, session_name, pane_id = parts
                if pane_tty == tty:
                    return session_name, pane_id

    except subprocess.CalledProcessError:
        pass

    return None, None


def get_pane_for_cwd(cwd: str, process_name: str | None = None) -> tuple[str | None, str | None]:
    """Find a tmux pane by its current working directory.

    Optionally filter by a process running in the pane.
    Returns (session_name, pane_id) or (None, None) if not found.
    """
    try:
        # List all panes with their cwd, current command, session, and pane ID
        result = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{pane_current_path}|#{pane_current_command}|#{session_name}|#{pane_id}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) == 4:
                pane_cwd, pane_cmd, session_name, pane_id = parts
                if pane_cwd == cwd:
                    # If process_name specified, check it matches
                    if process_name and process_name not in pane_cmd:
                        continue
                    return session_name, pane_id

    except subprocess.CalledProcessError:
        pass

    return None, None


def save_back_location(session: str, pane_id: str) -> None:
    """Save a location for the 'back' command."""
    back_file = get_back_file()
    data = {"session": session, "pane_id": pane_id}
    back_file.write_text(json.dumps(data))


def load_back_location() -> tuple[str | None, str | None]:
    """Load the saved 'back' location."""
    back_file = get_back_file()
    if not back_file.exists():
        return None, None

    try:
        data = json.loads(back_file.read_text())
        return data.get("session"), data.get("pane_id")
    except (json.JSONDecodeError, KeyError):
        return None, None


def switch_to_pane(session: str, pane_id: str, save_current: bool = True) -> bool:
    """
    Switch to a tmux session and pane.

    If save_current=True, saves the current location for 'back' command.

    Args:
        session: The session name (for context, though pane_id is globally unique)
        pane_id: The pane ID (e.g., '%5') - globally unique in tmux
        save_current: Whether to save current location before switching
    """
    # Save current location before switching
    if save_current:
        current_session, current_pane = get_current_location()
        if current_session and current_pane:
            save_back_location(current_session, current_pane)

    try:
        # Switch client to the target pane
        # tmux will automatically switch to the right session/window
        subprocess.run(
            ["tmux", "switch-client", "-t", pane_id],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def go_back() -> bool:
    """Switch back to the previously saved location."""
    session, pane_id = load_back_location()
    if session is None or pane_id is None:
        return False

    # Don't save current as new back location (would cause ping-pong)
    return switch_to_pane(session, pane_id, save_current=False)


def swap_back_location(current_session: str, current_pane_id: str) -> tuple[str | None, str | None]:
    """Atomically swap: save current location, return previous target.

    Returns (session, pane_id) of the target to switch to, or (None, None).
    """
    # Load target before overwriting
    target_session, target_pane_id = load_back_location()

    # Save current as new back location (enables ping-pong)
    save_back_location(current_session, current_pane_id)

    return target_session, target_pane_id
