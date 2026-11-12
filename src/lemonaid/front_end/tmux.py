"""tmux as a front end: a lemon is a pane in a window of a session on a server."""

import subprocess
from collections import abc
from pathlib import Path

from .. import tmux
from ..claude import launch_args
from ..config import Config
from ..launch import window
from ..launch.restart import pane, process
from ..lemon_watchers import watcher
from ..log import get_logger
from ..restore import run
from ..tmux import command_popup, restore
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


def lost(rows: abc.Sequence[interface.Metadata]) -> list[bool | None]:
    """A row is lost when no server runs on its recorded socket, or the one there started
    after the server its session was made on. Without a recorded socket, or a recorded
    session order to compare a running server with, it can't be judged.
    """
    servers: dict[str, int | str | None] = {}

    def judge(metadata: interface.Metadata) -> bool | None:
        socket = metadata.get("tmux_socket")
        if not socket:
            return None

        if socket not in servers:
            servers[socket] = tmux.server.started(socket)
        match servers[socket], metadata.get("tmux_session_order"):
            case tmux.server.GONE, _:
                return True
            case int(now), [int(), int(recorded), int()]:
                return now != recorded
            case _:
                return None

    return [judge(metadata) for metadata in rows]


def _workspace(socket: str, directory: Path, key: str, config: Config) -> str:
    return tmux.relocation.destination_session(
        socket, directory, key, config.places.protected_sessions
    )


def _prepare(socket: str, tty: str, workspace: str, directory: str, config: Config) -> None:
    """Make the destination session, and keep a protected session's pane open after
    its harness exits, even when the harness was the pane's only process."""
    tmux.relocation.ensure_session(socket, workspace, directory)
    found = pane.locate(socket, tty)
    if tmux.relocation.session_of(socket, found.pane) in config.places.protected_sessions:
        tmux.relocation.keep_on_exit(socket, found.pane)


def _only_shell(left: pane.Pane) -> bool:
    if left.dead:
        return True

    root = process.inspect(left.pid)
    return (
        root is not None
        and process.on_tty(left.tty) == [root]
        and process.shell(root, launch_args.argv(root.pid))
    )


def _leave(socket: str, tty: str, workspace: str, config: Config) -> str:
    """Close the old pane when only its shell is left. tmux then closes its window, and
    its session when that was its last pane; the session's clients follow the lemon."""
    try:
        left = pane.locate(socket, tty)
    except ValueError:
        return "its old pane is gone"

    try:
        if (session := tmux.relocation.session_of(socket, left.pane)) in (
            config.places.protected_sessions
        ):
            return f"its old pane {left.pane} stays open: session {session!r} is protected"

        if not _only_shell(left):
            return f"its old pane {left.pane} still runs other jobs, so it stays open"

        tmux.relocation.close_pane(socket, left.pane, workspace)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        return f"its old pane {left.pane} stays open: {error}"

    return f"closed its old pane {left.pane}"


def relocation() -> interface.Relocation:
    return interface.Relocation(_workspace, _prepare, tmux.relocation.pane_location, _leave)


def terminal() -> interface.Terminal:
    return interface.Terminal(
        name="tmux",
        workspace_key="tmux_session",
        here=lambda: bool(window.own_session()),
        show=show,
        exists=exists,
        lost=lost,
    )


def restorer(start: bool) -> run.Terminal:
    return restore.terminal(start)


def popup(command: abc.Sequence[str], title: str) -> int | None:
    return command_popup.run(command, title)
