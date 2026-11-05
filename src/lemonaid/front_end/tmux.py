"""tmux as a front end: a lemon is a pane in a window of a session on a server."""

from collections import abc

from .. import tmux
from ..config import Config
from ..launch import window
from ..lemon_watchers import watcher
from ..log import get_logger
from . import interface

_log = get_logger("front_end.tmux")


class _Unknown(Exception):
    """`ps` could not say what runs on a pane's tty."""


def _runs(tty: str, harness: str) -> bool:
    found = watcher.process_on_tty(tty, harness)
    if found is None:
        raise _Unknown(tty)
    return found


def show(
    metadata: interface.Metadata | None,
    config: Config,
    on_resume: abc.Callable[[str], None] | None = None,
) -> bool:
    """Switch to its pane, or recreate a dead session."""
    if metadata is None:
        return False

    try:
        session, pane_id = tmux.recorded_pane.locate(metadata)
    except tmux.navigation.TmuxUnavailable as error:
        _log.warning("not switching to %s: %s", metadata.get("channel"), error)
        return False

    # Directory lookup is only for rows without a recorded identity; it cannot
    # override evidence that a known pane is gone.
    if (session is None or pane_id is None) and not tmux.recorded_pane.has_identity(metadata):
        channel = metadata.get("channel", "")
        if channel.startswith("codex:"):
            _log.warning("not switching to %s: no recorded pane identifies its terminal", channel)
            return False
        cwd = metadata.get("cwd")
        if cwd:
            harness = watcher.harness_process(channel)
            try:
                session, pane_id = tmux.navigation.get_pane_for_cwd(
                    cwd, lambda pane_tty: _runs(pane_tty, harness)
                )
            except _Unknown:
                _log.warning("not switching to %s: could not identify its harness", cwd)
                return False

    if session == tmux.navigation.AMBIGUOUS:
        # One of the matches is the right session, so recreating would add a
        # duplicate to a directory that already has too many.
        _log.warning(
            "not switching to %s: its directory belongs to several sessions",
            metadata.get("cwd"),
        )
        return False

    if session is None or pane_id is None:
        if on_resume is None:
            return tmux.recreate.recreate(metadata, config)

        tty = tmux.recreate.resume(metadata, config)
        if tty is None:
            return False

        on_resume(tty)
        return True

    switched = tmux.navigation.switch_to_pane(session, pane_id)
    _log.info(
        "tmux jump channel=%s session=%s pane=%s switched=%s",
        metadata.get("channel"),
        session,
        pane_id,
        switched,
    )
    return switched


def exists(tty: str, socket: str | None = None, not_after: float | None = None) -> bool | None:
    """*not_after* rejects a pane in a session younger than the record: tty names are
    reused, so after a reboot a recorded tty usually names some other pane entirely.
    """
    try:
        session, pane_id = tmux.navigation.get_pane_for_tty(tty, socket, not_after)
    except tmux.navigation.TmuxUnavailable:
        return None

    return session is not None and pane_id is not None


def terminal() -> interface.Terminal:
    return interface.Terminal(
        name="tmux", here=lambda: bool(window.own_session()), show=show, exists=exists
    )
