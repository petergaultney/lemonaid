"""The tmux side of restoring lost lemons: which windows exist, and opening one at an index.

When tmux dies, the sessions are gone but the inbox is not: it still holds every
lost lemon, its cwd, and the session and window it was sitting in. This places each
lost lemon in a window, opens it and types the line that resumes it, for restore
(`lemonaid.restore`), which knows nothing of tmux.
"""

import subprocess
from collections import abc

from ..inbox import db
from ..launch import window as launch_window
from ..log import get_logger
from ..restore import run
from . import home, inspect, own_pane, placement, readiness, restore_relink, server

_log = get_logger("tmux.restore")

_SPAWN_TIMEOUT_SECONDS = 10


def _output(*argv: str) -> tuple[str, str]:
    """(what `argv` printed, why it failed or "")."""
    try:
        done = subprocess.run(
            argv, check=True, capture_output=True, text=True, timeout=_SPAWN_TIMEOUT_SECONDS
        )
        return done.stdout.strip(), ""
    except subprocess.CalledProcessError as e:
        _log.warning("%s failed: %s", " ".join(argv), e.stderr)
        return "", (e.stderr or "").strip() or f"exit {e.returncode}"
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("%s failed: %s", " ".join(argv), e)
        return "", str(e)


def _run(*argv: str) -> str:
    """Why `argv` failed, or "" when it ran."""
    return _output(*argv)[1]


def layout() -> dict[str, set[int]]:
    """Each running session's window indices; empty when no server runs."""
    try:
        result = subprocess.run(
            ["tmux", "list-windows", "-a", "-F", "#{session_name}|#{window_index}"],
            capture_output=True,
            text=True,
            timeout=_SPAWN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("could not list windows: %s", e)
        return {}

    # A missing server exits non-zero with "no server running": nothing to collide with.
    found: dict[str, set[int]] = {}
    for line in result.stdout.splitlines() if result.returncode == 0 else []:
        session, _, index = line.rpartition("|")
        if index.isdigit():
            found.setdefault(session, set()).add(int(index))
    return found


def _client_size() -> tuple[str, str]:
    """The size to build a detached session at.

    A detached session with no size is 80x24, and stays that way until a client
    shows it. The scratch pane splits its saved width off whatever the window
    reports, so in an 80-column window a 48-column sidebar leaves 32 for your
    work - and the swap that would fix it is capped against the client, which
    is wide enough that nothing looks wrong. The pane you see is the
    placeholder: a bare `sleep`, which renders as an empty pane.
    """
    result = subprocess.run(
        ["tmux", "display-message", "-p", "#{client_width} #{client_height}"],
        capture_output=True,
        text=True,
        timeout=_SPAWN_TIMEOUT_SECONDS,
    )
    parts = result.stdout.split()

    return (parts[0], parts[1]) if len(parts) == 2 and parts[0].isdigit() else ("200", "50")


def _first_index(session: str) -> int | None:
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", f"={session}:^", "#{window_index}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_SPAWN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("could not read the first window of %s: %s", session, e)
        return None

    return int(result.stdout.strip()) if result.stdout.strip().isdigit() else None


def _spot(at: placement.Spot) -> run.Spot:
    return run.Spot(
        f"{at.session}:{at.index}",
        f"{at.session}:{at.recorded}" if at.index != at.recorded else "",
        at,
    )


def place(
    rows: abc.Iterable[db.Notification],
) -> tuple[list[tuple[db.Notification, run.Spot]], list[tuple[db.Notification, str]]]:
    """Lemons go back only onto the server restore opens windows on; one whose own pane
    still runs there idle at a shell goes back into it."""
    rows = list(rows)
    away = [(row, socket) for row in rows if (socket := home.elsewhere(row.metadata))]
    here = [row for row in rows if not home.elsewhere(row.metadata)]
    own = own_pane.idle(here)
    placed, unplaced = placement.place((row for row in here if row.channel not in own), layout())
    return [
        *(
            (row, run.Spot(own[row.channel].where, "", own[row.channel]))
            for row in here
            if row.channel in own
        ),
        *((row, _spot(at)) for row, at in placed),
    ], [
        *((row, f"it ran on another tmux server ({socket})") for row, socket in away),
        *((row, "no place in its terminal is recorded for it") for row in unplaced),
    ]


def close_window(window: str) -> None:
    """Close the window restore made, by its id, so no other window is ever closed. A
    lemon's own pane (a pane id, not a window's) is left as it is."""
    if window.startswith("%"):
        return

    _run("tmux", "kill-window", "-t", window)


def _exists(session: str) -> bool:
    return not _run("tmux", "has-session", "-t", f"={session}")


def open_window(
    to: run.Spot, cwd: str, environment: abc.Mapping[str, str], start: bool = True
) -> tuple[str, str]:
    """Open *spot*'s window in *cwd*: (the window id it made, why not or "").

    Without *start*, a missing session is made only on a server that runs: tmux's `-N`
    refuses to start one, however the server went away since anyone checked.

    Whether to create the session is decided now, not when the plan was made, since an
    earlier window of it may have been closed or made since. tmux refuses an index that
    is taken, so a window someone opened there meanwhile is never touched. A new
    session's first window is moved to its recorded index before anything else is
    added, so a window lemonaid knows nothing about leaves a gap rather than shifting
    the others down.
    """
    if isinstance(to.at, own_pane.Pane):
        return own_pane.respawn(to.at, cwd, environment)

    spot: placement.Spot = to.at
    environment_args = launch_window.environment_args(dict(environment))
    new = ("-P", "-F", "#{window_id}")
    if _exists(spot.session):
        made, why = _output(
            "tmux",
            "new-window",
            "-d",
            "-t",
            f"={spot.session}:{spot.index}",
            "-c",
            cwd,
            *new,
            *environment_args,
        )
        return made, why

    width, height = _client_size()
    made, why = _output(
        "tmux",
        *(() if start else ("-N",)),
        "new-session",
        "-d",
        "-s",
        spot.session,
        "-c",
        cwd,
        "-x",
        width,
        "-y",
        height,
        *new,
        *environment_args,
    )
    if why:
        return "", f"could not create its session: {why}"

    # tmux refuses to move a window onto its own index, which is where base-index puts
    # it when the two agree.
    if _first_index(spot.session) != spot.index and (
        why := _run("tmux", "move-window", "-s", made, "-t", f"={spot.session}:{spot.index}")
    ):
        close_window(made)
        return "", why

    return made, ""


def type_line(window: str, line: str) -> str:
    return _run("tmux", "send-keys", "-t", window, line, "Enter")


def up() -> bool:
    """Whether a tmux server runs on the default socket, where restore opens windows."""
    return isinstance(server.started(None), int)


def terminal(start: bool) -> run.Terminal:
    return run.Terminal(
        place,
        lambda to, cwd, environment: open_window(to, cwd, environment, start),
        type_line,
        close_window,
        restore_relink.running,
        inspect.seen,
        restore_relink.found,
        restore_relink.relinked,
        readiness.unready,
        readiness.strays,
        readiness.ADVICE,
        up,
    )
