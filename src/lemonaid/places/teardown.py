"""Tearing down a tmux session and the places it occupies.

Ordering matters here, because the caller is usually standing inside the thing
being destroyed. You have to be moved out before anything is removed, and the
removal itself is slow enough (dependency trees, large working copies) that
waiting on it defeats the purpose. So teardown switches every client away first,
then does the work in a detached process.
"""

import shlex
import subprocess
from collections import abc
from pathlib import Path

from .. import tmux
from ..log import get_logger
from . import escape, hooks, inbox_cleanup, ownership, windows

_log = get_logger("places.teardown")

_REAP_TIMEOUT_SECONDS = 1800  # a large working copy can take a while to remove


def reap_log_path() -> Path:
    return tmux.navigation.get_state_path() / "reap.log"


def _reaper_session_name(what: str) -> str:
    """A recognizable name, so a stuck teardown is findable in `tmux ls`.

    *what* is the session being killed, or the places being released when there is
    no session - two sessionless tosses running at once would otherwise ask tmux
    for the same name.
    """
    return "_lma_reap_" + "".join(c if c.isalnum() else "-" for c in what)[:40]


def _release_commands(places: abc.Sequence[ownership.Place], log: str) -> list[str]:
    """One destroy invocation per place, skipping what there's nothing to do for.

    A place whose directory is already gone needs no release - that is the normal
    state for a session outliving its worktree, not a failure. A root with no
    destroy hook has nothing to run either.
    """
    return [
        f"( cd {shlex.quote(str(place.root.path))} && "
        f"{{ {hooks.substitute(place.root.destroy, key=place.key)} ; }} ) >> {log} 2>&1"
        for place in places
        if place.root.destroy and place.exists
    ]


def _spawn_reaper(
    session: str,
    places: abc.Sequence[ownership.Place],
    cwd: Path,
    window: str = "",
) -> str | None:
    """Kill *session* if there is one and release *places*, outliving this process.

    A throwaway tmux session hosts the work: it survives the caller's shell
    exiting, and tmux is already a dependency. The session is killed before any
    directory is released because the caller's shell has its working directory
    inside one of them, and a process still holding a file there can make the
    removal fail. *window* is the caller's own window when that closes on its
    own rather than with a session: killing it ends the caller, so it too is
    left to the reaper.

    The reaper has no terminal anyone will look at, so it appends to a log.
    """
    log = shlex.quote(str(reap_log_path()))
    what = session or ", ".join(place.key for place in places)
    reaper = _reaper_session_name(what)
    script = "; ".join(
        [
            f"echo {shlex.quote(f'--- tossing {what} ---')} >> {log}",
            *(
                [f"tmux kill-session -t {shlex.quote('=' + session)} >> {log} 2>&1"]
                if session
                else []
            ),
            *([f"tmux kill-window -t {shlex.quote(window)} >> {log} 2>&1"] if window else []),
            *_release_commands(places, log),
            f"echo {shlex.quote(f'--- done {what} ---')} >> {log}",
            f"tmux kill-session -t {shlex.quote('=' + reaper)}",
        ]
    )

    try:
        subprocess.run(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                reaper,
                "-c",
                str(cwd),
                # Separate argv elements: tmux execs these itself rather than
                # handing them to a shell, so a single "sh -c ..." string would be
                # looked up as a program by that literal name and fail silently.
                "sh",
                "-c",
                script,
            ],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as e:
        _log.warning("could not spawn a reaper for %r: %s", what, e)
        return f"Could not start teardown of {what!r}: {e}"

    return None


def concerns(place: ownership.Place) -> list[str]:
    """Reasons not to destroy *place* without being asked twice.

    The root's inspect hook decides what counts - lemonaid has no opinion about
    what makes a directory worth keeping. A directory that is already gone can
    hold nothing worth keeping.
    """
    if not place.exists:
        return []

    return [line for line in [hooks.inspect(place.root, place.directory)] if line]


def _reaper_cwd(places: abc.Sequence[ownership.Place]) -> Path:
    """Somewhere for the reaper to sit that isn't a directory it's removing."""
    return next((place.root.path for place in places), Path.home())


def toss(
    session: str,
    places: abc.Sequence[ownership.Place],
    partial: windows.Planned = {},  # noqa: B006 - read only
) -> str | None:
    """Kill *session*, close the *partial* windows, and release *places*.

    Clients are moved out of harm's way first: out of *session*, and off each
    closing window onto another in its own session. The caller has checked the
    plan against tmux just before this (`target.changed_since`); nothing here
    looks again. An empty *session* with no windows releases the places without
    killing anything - a directory that never had a session is still worth
    releasing.

    Returns an error message on failure, or None once teardown is under way.
    Teardown itself finishes after this returns; see `reap_log_path`.
    """
    if session and (error := escape.evacuate(session)):
        return error

    if partial and (error := windows.move_clients_off(partial)):
        return error

    snapshot = inbox_cleanup.capture(session, places, partial)

    # The caller's own window is left to the reaper: closing it here would end
    # this process before the directory is released.
    own = windows.own_window() if partial else ""
    if partial and (failed := windows.close(w for w in partial if w != own)):
        return f"Could not close {', '.join(failed)}; the directory was not released."

    error = _spawn_reaper(session, places, _reaper_cwd(places), own if own in partial else "")
    if error:
        return error

    inbox_cleanup.finish(snapshot)
    return None
