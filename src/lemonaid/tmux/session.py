"""tmux session creation and management."""

import subprocess
import sys
import time
from pathlib import Path

from . import is_inside_tmux


def get_base_index() -> int:
    """Get tmux's base-index setting (usually 0 or 1)."""
    try:
        result = subprocess.run(
            ["tmux", "show-option", "-gv", "base-index"],
            capture_output=True,
            text=True,
            check=True,
        )
        return int(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0  # default


def create_session(
    name: str,
    windows: list[str],
    directory: str | Path | None = None,
    claude_rename: bool = False,
    attach: bool = True,
) -> bool:
    """Create a new tmux session with the specified windows.

    Args:
        name: Session name
        windows: List of commands for each window (empty string = just shell)
        directory: Working directory for all windows (default: cwd)
        claude_rename: If True, send /rename to any window running 'claude'
        attach: If True, attach to the session after creation

    Returns True on success.
    """
    if directory is None:
        directory = Path.cwd()
    directory = str(directory)

    base_index = get_base_index()

    # Create session with first window
    try:
        first_cmd = windows[0] if windows else ""
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", name, "-c", directory],
            check=True,
            capture_output=True,
        )

        # Send command to first window if specified
        if first_cmd:
            subprocess.run(
                ["tmux", "send-keys", "-t", f"{name}:{base_index}", first_cmd, "Enter"],
                check=True,
                capture_output=True,
            )

        # Create remaining windows
        for i, cmd in enumerate(windows[1:], start=1):
            subprocess.run(
                ["tmux", "new-window", "-t", name, "-c", directory],
                check=True,
                capture_output=True,
            )
            win_idx = base_index + i
            if cmd:
                subprocess.run(
                    ["tmux", "send-keys", "-t", f"{name}:{win_idx}", cmd, "Enter"],
                    check=True,
                    capture_output=True,
                )

        # Select first window
        subprocess.run(
            ["tmux", "select-window", "-t", f"{name}:{base_index}"],
            check=True,
            capture_output=True,
        )

        # Send /rename to claude windows after a delay.
        # Disabled by default since lemonaid now derives notification names from
        # the tmux session name automatically (see claude/notify.py get_tmux_session_name).
        if claude_rename:
            claude_win_indices = [
                base_index + i for i, cmd in enumerate(windows) if cmd.strip().startswith("claude")
            ]
            if claude_win_indices:
                time.sleep(1.5)  # wait for claude to start
                for win_idx in claude_win_indices:
                    subprocess.run(
                        ["tmux", "send-keys", "-t", f"{name}:{win_idx}", f"/rename {name}", "C-m"],
                        check=True,
                        capture_output=True,
                    )

        # Attach if requested
        if attach:
            # Use switch-client if inside tmux, else attach-session
            if is_inside_tmux():
                subprocess.run(
                    ["tmux", "switch-client", "-t", name],
                    check=True,
                )
            else:
                subprocess.run(
                    ["tmux", "attach-session", "-t", name],
                    check=True,
                )

        return True

    except subprocess.CalledProcessError as e:
        print(f"Failed to create session: {e}", file=sys.stderr)
        if e.stderr:
            print(f"tmux error: {e.stderr.decode().strip()}", file=sys.stderr)
        return False
