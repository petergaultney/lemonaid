"""Shared utilities for LLM integrations."""

import os
import subprocess
import sys
from pathlib import Path

from ..log import get_logger

_log = get_logger("lemon_watchers.common")

_ANCESTOR_DEPTH = 10
_PROBE_TIMEOUT_SECONDS = 5


def get_tty() -> str | None:
    """Get the TTY name for this process or an ancestor process.

    Tries stdin/stdout/stderr first, then walks up the process tree
    looking for an ancestor with a controlling TTY. This is useful when
    spawned as a hook (e.g., OpenClaw TypeScript hooks run in Node.js
    which doesn't have a TTY, but an ancestor shell does).

    Note: Process tree walking uses `ps` which behaves slightly differently
    on macOS vs Linux, but the TTY detection should work on both.

    Returning None is consequential and hard to notice later: the tty is what
    the watcher keys auto-archiving on and what switching resolves a pane by, so
    a notification without one is never garbage-collected and falls back to
    matching on cwd, which several sessions can share. It is logged for that
    reason - roughly 5% of recorded notifications have historically lacked one,
    with no trace of why.
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
    from_ancestor = _get_ancestor_tty()
    if not from_ancestor:
        _log.warning(
            "no tty for pid %d via stdin/stdout/stderr or %d ancestors; "
            "this notification will not be auto-archived and can only be switched to by cwd",
            os.getpid(),
            _ANCESTOR_DEPTH,
        )

    return from_ancestor


def _get_ancestor_tty(max_depth: int = _ANCESTOR_DEPTH) -> str | None:
    """Walk up the process tree looking for an ancestor with a TTY.

    Stops at init (PID 1) or after max_depth iterations to prevent infinite loops.

    Each way of giving up is logged distinctly. A `ps` that fails and a tree with
    genuinely no terminal in it produce the same None, and telling them apart
    afterward is the whole difficulty in diagnosing a notification that arrived
    without a tty.
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
                timeout=_PROBE_TIMEOUT_SECONDS,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            _log.warning("ps failed walking up from pid %d: %s", pid, e)
            return None

        parts = result.stdout.strip().split()
        if len(parts) < 2:
            _log.warning("ps gave no ppid/tty for pid %d: %r", pid, result.stdout)
            return None

        try:
            ppid = int(parts[0])
        except ValueError:
            _log.warning("ps gave an unparseable ppid for pid %d: %r", pid, parts[0])
            return None

        tty = parts[1]
        if tty and tty not in ("??", "-", ""):
            return f"/dev/{tty}"

        if ppid <= 1:
            _log.info("reached pid %d with no tty in the tree above pid %d", ppid, os.getpid())
            return None

        pid = ppid

    _log.warning("gave up after %d ancestors looking for a tty", max_depth)

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


def _pane_format(spec: str) -> str | None:
    """Ask tmux about this pane, or None when there is no pane to ask about."""
    pane_id = os.environ.get("TMUX_PANE")
    if not pane_id:
        return None

    try:
        result = subprocess.run(
            ["tmux", "display-message", "-t", pane_id, "-p", spec],
            capture_output=True,
            text=True,
            check=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except (subprocess.SubprocessError, OSError) as e:
        _log.warning("could not read %s for pane %s: %s", spec, pane_id, e)
        return None

    return result.stdout.strip() or None


def get_tmux_session_name() -> str | None:
    """Get the tmux session name if running in tmux."""
    return _pane_format("#{session_name}")


def get_tmux_window_index() -> str | None:
    """The pane's window index, as tmux would address it.

    Kept as the string tmux printed rather than an int: it is only ever used to
    build a `session:index` target, and a base-index of 1 makes 0 a real value
    that must not be confused with absent.
    """
    return _pane_format("#{window_index}")


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
