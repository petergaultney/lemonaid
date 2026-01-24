"""Shared utilities for LLM integrations."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def get_tty() -> str | None:
    """Get the TTY name for this process or its parent.

    Tries stdin/stdout/stderr first, then falls back to querying ps
    for the parent process's TTY (useful when spawned as a hook).
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

    # Fall back to asking ps for parent's TTY (works when spawned as hook)
    try:
        result = subprocess.run(
            ["ps", "-o", "tty=", "-p", str(os.getppid())],
            capture_output=True,
            text=True,
            check=True,
        )
        tty = result.stdout.strip()
        if tty and tty != "??" and tty != "":
            return f"/dev/{tty}"
    except (subprocess.CalledProcessError, OSError):
        pass

    return None


def detect_terminal_env() -> str:
    """Detect which terminal environment we're running in.

    Returns one of: 'tmux', 'wezterm', or 'unknown'.
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


def get_name_from_cwd(cwd: str) -> str:
    """Extract a display name from the cwd path (last component)."""
    if not cwd:
        return ""
    parts = cwd.rstrip("/").split("/")
    return parts[-1] if parts else ""


def short_filename(path: str) -> str:
    """Shorten a file path for display - just the filename."""
    if not path:
        return "file"
    return Path(path).name or path[-30:]
