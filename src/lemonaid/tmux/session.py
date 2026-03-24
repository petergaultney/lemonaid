"""tmux session creation and management."""

import shlex
import subprocess
import sys
import time
from pathlib import Path

from ..claude.projects import find_session_project
from ..config import TmuxSessionConfig
from ..log import get_logger
from .navigation import is_inside_tmux

_log = get_logger("tmux.session")


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

    # Create session with first window
    try:
        first_cmd = windows[0] if windows else ""
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", name, "-c", directory],
            check=True,
            capture_output=True,
        )

        # Query base-index after new-session so the server is guaranteed to exist.
        # On a fresh boot with no tmux server, querying before would fall back to 0
        # even if ~/.tmux.conf sets base-index to 1.
        base_index = get_base_index()

        # Send command to first window if specified.
        # send-keys failures are non-fatal — the session/windows are already created.
        if first_cmd:
            subprocess.run(
                ["tmux", "send-keys", "-t", f"{name}:{base_index}", first_cmd, "Enter"],
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


def spawn_session_for_resume(
    resume_argv: list[str],
    cwd: str,
    config: TmuxSessionConfig,
    channel: str = "",
    session_metadata: dict | None = None,
) -> str | None:
    """Create a tmux session from the default template with a resume command.

    Replaces the window at `config.resume_window` with the resume command.
    For Claude sessions, resolves the project directory from history.jsonl
    to use as the session root.

    Returns an error message string on failure, or None on success.
    """
    from .cli import _auto_session_name

    windows = config.get_template("default")
    if not windows:
        return "No tmux-session template 'default' in config"

    resume_cmd = " ".join(shlex.quote(a) for a in resume_argv)

    # For Claude sessions, prefer the history-derived project dir
    if channel.startswith("claude:") and session_metadata:
        session_id = session_metadata.get("session_id", "")
        if session_id:
            project_dir = find_session_project(session_id)
            if project_dir:
                cwd = project_dir

    idx = min(config.resume_window, len(windows) - 1)
    session_windows = [*windows[:idx], resume_cmd, *windows[idx + 1 :]]
    session_name = _auto_session_name(Path(cwd))

    _log.info("spawn_session_for_resume: %s -> session '%s' in %s", channel, session_name, cwd)

    if not create_session(name=session_name, windows=session_windows, directory=cwd, attach=True):
        return "Failed to create tmux session"

    return None
