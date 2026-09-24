"""tmux session creation and management."""

import shlex
import subprocess
import time
from collections.abc import Mapping
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
    environment: Mapping[str, str] | None = None,
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

        if environment and not set_session_environment(name, environment):
            return False

        # Query base-index after new-session so the server is guaranteed to exist.
        # On a fresh boot with no tmux server, querying before would fall back to 0
        # even if ~/.tmux.conf sets base-index to 1.
        base_index = get_base_index()

        # Send command to first window if specified.
        # send-keys failures are non-fatal — the session/windows are already created.
        if first_cmd:
            if environment:
                exports = "; ".join(
                    f"export {key}={shlex.quote(value)}" for key, value in environment.items()
                )
                first_cmd = f"{exports}; {first_cmd}"
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
        stderr_msg = e.stderr.decode().strip() if e.stderr else ""
        _log.warning("create_session failed: %s — %s", e, stderr_msg)
        return False


def sanitize_name(name: str) -> str:
    """Make a string safe for use as a tmux session name.

    tmux forbids dots and colons in session names.
    """
    return name.replace(".", "-").replace(":", "-").strip()


def set_session_environment(session: str, environment: Mapping[str, str]) -> bool:
    """Set values inherited by windows subsequently created in *session*."""
    try:
        for key, value in environment.items():
            subprocess.run(
                ["tmux", "set-environment", "-t", session, key, value],
                check=True,
                capture_output=True,
            )
    except (OSError, subprocess.CalledProcessError) as e:
        _log.warning("could not set environment in session %s: %s", session, e)
        return False
    return True


def auto_session_name(directory: Path, max_len: int = 15) -> str:
    """Derive a tmux session name from the directory path.

    Uses the last one or two path components, joined by '-', trimmed to
    roughly *max_len* characters.  A single final component is never
    truncated; two components are used only when they fit.
    """
    parts = directory.resolve().parts  # absolute, no trailing slash quirks
    if len(parts) <= 1:
        return parts[-1] if parts else "tmux"

    last = parts[-1]
    candidate = f"{parts[-2]}-{last}"
    if len(candidate) <= max_len:
        return candidate

    # two components don't fit - just use the last one
    return last


def spawn_session(
    cwd: str,
    config: TmuxSessionConfig,
    resume_argv: list[str] | None = None,
    channel: str = "",
    session_metadata: dict | None = None,
    session_name: str = "",
    attach: bool = True,
    template_name: str = "default",
    initial_prompt: str = "",
    environment: Mapping[str, str] | None = None,
) -> str | None:
    """Create a tmux session from a configured template, rooted at *cwd*.

    With *resume_argv*, the window at `config.resume_window` is replaced by that
    command; without it the template is used as-is, which is what recreating a
    session for a directory that no longer has one needs.

    For Claude sessions, resolves the project directory from history.jsonl to
    use as the session root.

    Returns an error message string on failure, or None on success.
    """
    windows = config.get_template(template_name)
    if not windows:
        return f"No tmux-session template {template_name!r} in config"

    # Never mutate the list held by Config: the next session may choose a
    # different prompt or no prompt at all.
    windows = list(windows)

    if initial_prompt:
        configured_idx = (
            config.resume_window if config.harness_window is None else config.harness_window
        )
        idx = max(0, min(configured_idx, len(windows) - 1))
        if not windows[idx].strip():
            return (
                f"Tmux-session template {template_name!r} has no harness command "
                f"in window {idx}"
            )
        windows[idx] = f"{windows[idx]} {shlex.quote(initial_prompt)}"

    # For Claude sessions, prefer the history-derived project dir
    if channel.startswith("claude:") and session_metadata:
        session_id = session_metadata.get("session_id", "")
        if session_id:
            project_dir = find_session_project(session_id)
            if project_dir:
                cwd = project_dir

    if resume_argv:
        idx = min(config.resume_window, len(windows) - 1)
        resume_cmd = " ".join(shlex.quote(a) for a in resume_argv)
        windows = [*windows[:idx], resume_cmd, *windows[idx + 1 :]]

    session_name = sanitize_name(session_name or auto_session_name(Path(cwd)))

    _log.info("spawn_session: %s -> session '%s' in %s", channel or "no channel", session_name, cwd)

    if environment is None:
        # A session recreated from the inbox/history should keep the place's
        # identity even though it did not travel through `place open`.
        from ..places import names

        if lemon_name := names.current_name(cwd):
            environment = {names.LEMON_NAME_ENV: lemon_name}

    if not create_session(
        name=session_name,
        windows=windows,
        directory=cwd,
        attach=attach,
        environment=environment,
    ):
        return f"Failed to create tmux session '{session_name}' (name may already exist)"

    return None
