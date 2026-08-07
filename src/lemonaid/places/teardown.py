"""Tearing down a tmux session and the places it occupies.

Ordering matters here, because the caller is usually standing inside the thing
being destroyed. You have to be moved out before anything is removed, and the
removal itself is slow enough (dependency trees, large working copies) that
waiting on it defeats the purpose. So teardown switches you away first, then does
the work in a detached process.
"""

import shlex
import sqlite3
import subprocess
from collections import abc
from pathlib import Path

from .. import tmux
from ..inbox import db
from ..log import get_logger
from . import hooks, ownership

_log = get_logger("places.teardown")

_REAP_TIMEOUT_SECONDS = 1800  # a large working copy can take a while to remove


def reap_log_path() -> Path:
    return tmux.navigation.get_state_path() / "reap.log"


def _live_sessions_by_recency(doomed_session: str) -> list[str]:
    """Other sessions, most recently active first, excluding lemonaid's own."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_activity} #{session_name}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as e:
        _log.warning("could not list sessions to find an escape target: %s", e)
        return []

    return [
        name
        for _, name in sorted(
            (
                (int(activity), name)
                for activity, _, name in (
                    line.partition(" ") for line in result.stdout.splitlines()
                )
                if activity.isdigit() and name != doomed_session and not name.startswith("_lma")
            ),
            reverse=True,
        )
    ]


def _wants_attention(available: abc.Container[str]) -> str:
    """The live session with something unread in the inbox, if any.

    Preferred over bare recency: the most recently *active* session is often the
    one you just left, while the inbox knows which one is actually waiting on you.
    """
    try:
        with db.connect() as conn:
            unread = db.get_unread(conn)
    except sqlite3.Error as e:
        _log.warning("could not read the inbox for an escape target: %s", e)
        return ""

    return next((n.name for n in unread if n.name and n.name in available), "")


def _escape_target(doomed_session: str) -> str:
    """Where to send the client before killing *doomed_session*.

    Wherever you came from first - finishing a piece of work usually means going
    back to what you left. Otherwise a session that wants attention, and failing
    that the most recently active one.
    """
    back_session, _ = tmux.navigation.load_back_location()
    if back_session and back_session != doomed_session:
        return back_session

    by_recency = _live_sessions_by_recency(doomed_session)

    return _wants_attention(set(by_recency)) or next(iter(by_recency), "")


def _switch_client(session: str) -> bool:
    """Move this client to *session* by name.

    Not `navigation.switch_to_pane`, which targets a pane id; here the
    destination is a whole session and tmux picks its active pane.
    """
    try:
        subprocess.run(
            ["tmux", "switch-client", "-t", session],
            check=True,
            capture_output=True,
        )
        return True
    except (OSError, subprocess.CalledProcessError) as e:
        _log.warning("could not switch to %s: %s", session, e)
        return False


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
        f"{{ {hooks.substitute(place.root.destroy, key=place.key)} ; }} >> {log} 2>&1"
        for place in places
        if place.root.destroy and place.exists
    ]


def _spawn_reaper(session: str, places: abc.Sequence[ownership.Place], cwd: Path) -> str | None:
    """Kill *session* if there is one and release *places*, outliving this process.

    A throwaway tmux session hosts the work: it survives the caller's shell
    exiting, and tmux is already a dependency. The session is killed before any
    directory is released because the caller's shell has its working directory
    inside one of them, and a process still holding a file there can make the
    removal fail.

    The reaper has no terminal anyone will look at, so it appends to a log.
    """
    log = shlex.quote(str(reap_log_path()))
    what = session or ", ".join(place.key for place in places)
    script = "; ".join(
        [
            f"echo {shlex.quote(f'--- tossing {what} ---')} >> {log}",
            *([f"tmux kill-session -t {shlex.quote(session)} >> {log} 2>&1"] if session else []),
            *_release_commands(places, log),
            f"echo {shlex.quote(f'--- done {what} ---')} >> {log}",
        ]
    )

    try:
        subprocess.run(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                _reaper_session_name(what),
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
    from_inside: bool,
) -> str | None:
    """Kill *session* and release *places*, moving the client out first if needed.

    An empty *session* releases the places without killing anything - a directory
    that never had a session is still worth releasing.

    Returns an error message on failure, or None once teardown is under way.
    Teardown itself finishes after this returns; see `reap_log_path`.
    """
    if from_inside:
        target = _escape_target(session)
        if not target:
            return "Nowhere to switch to - refusing to kill the session you're in"

        if not _switch_client(target):
            return f"Could not switch away to '{target}'; nothing was torn down"

    return _spawn_reaper(session, places, _reaper_cwd(places))
