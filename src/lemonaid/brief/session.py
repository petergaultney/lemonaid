"""What tmux knows about a session that helps find its brief."""

import os
import subprocess
from pathlib import Path

LEMON_NAME_ENV = "LEMON_NAME"


def _tmux(*args: str) -> str:
    """A tmux command's stdout, or "" when it fails (no server, no such session)."""
    result = subprocess.run(["tmux", *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def current_session() -> str:
    """`session:window` of the calling pane, or "" outside tmux."""
    pane = os.environ.get("TMUX_PANE")
    if not pane:
        return ""

    return _tmux("display-message", "-p", "-t", pane, "#{session_name}:#{window_index}")


def client_window(session: str) -> str:
    """The index of the window the calling client shows in *session*, or "" if it
    shows another session or the caller is not in tmux.

    A key binding's `run-shell` has no `TMUX_PANE`, but its `TMUX` names the
    session the key was pressed in, and an untargeted query answers for that.
    """
    if not os.environ.get("TMUX"):
        return ""

    pane = os.environ.get("TMUX_PANE")
    here = _tmux(
        "display-message", "-p", *(("-t", pane) if pane else ()), "#{session_name}\t#{window_index}"
    )
    name, _, index = here.partition("\t")
    return index if name == session else ""


def session_dir(session: str) -> Path | None:
    """The directory a session was started in, which for a place is the place."""
    path = _tmux("display-message", "-p", "-t", f"={session}:", "#{session_path}")
    return Path(path) if path else None


def lemon_name(session: str) -> str:
    """The session's `LEMON_NAME`, or "" when it has none."""
    line = _tmux("show-environment", "-t", f"={session}", LEMON_NAME_ENV)
    prefix = f"{LEMON_NAME_ENV}="
    return line.removeprefix(prefix) if line.startswith(prefix) else ""


def names(session: str, backend: str = "", display: str = "") -> list[str]:
    """What a brief for this session could be named after, most specific first."""
    return [n for n in (lemon_name(session) if session else "", backend, session, display) if n]


def _windows(*args: str) -> list[list[str]]:
    """Rows of `list-windows`, since `display-message` answers for the current window
    when its target doesn't exist."""
    out = _tmux(
        "list-windows",
        *args,
        "-F",
        "#{session_name}\t#{window_index}\t#{window_id}\t#{window_name}",
    )
    return [line.split("\t", 3) for line in out.splitlines() if line.count("\t") == 3]


def window(session: str, window: str) -> tuple[str, str]:
    """(index, ID) of the one window *window* numbers or names in *session*, or ("", "")."""
    rows = _windows("-t", f"={session}")
    found = [r for r in rows if r[1] == window] or [r for r in rows if r[3] == window]
    return (found[0][1], found[0][2]) if len(found) == 1 else ("", "")


def window_location(window_id: str) -> tuple[str, str]:
    """(session, index) where tmux's window *window_id* is now, or ("", "") if it is gone."""
    found = [r for r in _windows("-a") if r[2] == window_id]
    return (found[0][0], found[0][1]) if found else ("", "")
