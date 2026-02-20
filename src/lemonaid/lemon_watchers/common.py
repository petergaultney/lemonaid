"""Shared utilities for LLM integrations."""

import os
import subprocess
import sys
from pathlib import Path


def get_tty() -> str | None:
    """Get the TTY name for this process or an ancestor process.

    Tries stdin/stdout/stderr first, then walks up the process tree
    looking for an ancestor with a controlling TTY. This is useful when
    spawned as a hook (e.g., OpenClaw TypeScript hooks run in Node.js
    which doesn't have a TTY, but an ancestor shell does).

    Note: Process tree walking uses `ps` which behaves slightly differently
    on macOS vs Linux, but the TTY detection should work on both.
    """
    # Try stdin first
    try:
        tty = os.ttyname(sys.stdin.fileno())
        if tty and tty != "/dev/tty":
            return tty
    except OSError:
        pass

    # Try stdout
    try:
        tty = os.ttyname(sys.stdout.fileno())
        if tty and tty != "/dev/tty":
            return tty
    except OSError:
        pass

    # Try stderr
    try:
        tty = os.ttyname(sys.stderr.fileno())
        if tty and tty != "/dev/tty":
            return tty
    except OSError:
        pass

    # Walk up the process tree looking for an ancestor with a TTY
    return _get_ancestor_tty()


def _get_ancestor_tty(max_depth: int = 10) -> str | None:
    """Walk up the process tree looking for an ancestor with a TTY.

    Stops at init (PID 1) or after max_depth iterations to prevent infinite loops.
    """
    pid = os.getpid()

    for _ in range(max_depth):
        try:
            # Get parent PID and TTY in one call
            result = subprocess.run(
                ["ps", "-o", "ppid=,tty=", "-p", str(pid)],
                capture_output=True,
                text=True,
                check=True,
            )
            parts = result.stdout.strip().split()
            if len(parts) < 2:
                break

            ppid_str, tty = parts[0], parts[1]
            ppid = int(ppid_str)

            # Check if this process has a real TTY
            if tty and tty not in ("??", "-", ""):
                return f"/dev/{tty}"

            # Move to parent
            if ppid <= 1:
                break
            pid = ppid

        except (subprocess.CalledProcessError, OSError, ValueError):
            break

    return None


def detect_terminal_switch_source() -> str:
    """Detect the switch-source for this terminal environment.

    The switch-source determines which switch-handler can navigate
    back to this terminal. Returns one of: 'tmux', 'wezterm', or 'unknown'.
    """
    if os.environ.get("TMUX"):
        return "tmux"
    if os.environ.get("WEZTERM_PANE"):
        return "wezterm"
    return "unknown"


def get_tmux_session_name() -> str | None:
    """Get the tmux session name if running in tmux."""
    pane_id = os.environ.get("TMUX_PANE")
    if not pane_id:
        return None
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-t", pane_id, "-p", "#{session_name}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def shorten_path(path: str) -> str:
    """Shorten a path for display, using last 2 components.

    Examples:
        /Users/peter/play/lemonaid -> play/lemonaid
        ~/work/project/subdir -> project/subdir
    """
    if not path:
        return "session"
    cwd_path = Path(path)
    home = Path.home()

    if cwd_path.is_relative_to(home):
        display_path = "~/" + str(cwd_path.relative_to(home))
    else:
        display_path = str(cwd_path)

    parts = display_path.split("/")
    if len(parts) > 2:
        return "/".join(parts[-2:])
    return display_path


def fish_path(path: str) -> str:
    """Shorten a path fish-shell style: abbreviate intermediate dirs to first char.

    ~/work/ds-monorepo/libs/gent -> ~/w/d/l/gent
    /Users/peter/play/lemonaid   -> ~/p/lemonaid
    /etc/nginx/conf.d            -> /e/n/conf.d
    """
    if not path:
        return ""
    cwd_path = Path(path)
    home = Path.home()

    if cwd_path.is_relative_to(home):
        parts = ["~", *cwd_path.relative_to(home).parts]
    else:
        # Absolute path: parts[0] is "/" — drop it and rejoin with leading /
        parts = list(cwd_path.parts[1:])
        if len(parts) <= 1:
            return str(cwd_path)

        return "/" + "/".join(
            [
                *(p[0] for p in parts[:-1]),
                parts[-1],
            ]
        )

    if len(parts) <= 2:
        return str(cwd_path).replace(str(home), "~")

    return "/".join(
        [
            parts[0],
            *(p[0] for p in parts[1:-1]),
            parts[-1],
        ]
    )


def get_name_from_cwd(cwd: str) -> str:
    """Extract a display name from the cwd path (last component)."""
    if not cwd:
        return ""
    parts = cwd.rstrip("/").split("/")
    return parts[-1] if parts else ""


def get_git_branch(cwd: str) -> str | None:
    """Get the current git branch for a directory. Returns None if not a git repo."""
    if not cwd:
        return None

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
        branch = result.stdout.strip()
        return branch if branch else None
    except (subprocess.CalledProcessError, OSError):
        return None


def short_filename(path: str) -> str:
    """Shorten a file path for display - just the filename."""
    if not path:
        return "file"
    return Path(path).name or path[-30:]
