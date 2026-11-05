"""cmux as a front end: a lemon is a surface in a workspace.

A cmux session can outlive its tty, so whether one is still there is asked of
cmux for each session (`handlers.where_sessions_are`), never of its tty.
"""

import os
from collections import abc

from .. import cmux
from ..config import Config
from ..lemon_watchers import watcher
from ..log import get_logger
from . import interface

_log = get_logger("front_end.cmux")


def runs_harness(metadata: interface.Metadata, tty: str) -> bool | None:
    return watcher.process_on_tty(tty, watcher.harness_process(metadata.get("channel", "")))


def locate(metadata: interface.Metadata) -> cmux.navigation.Surface | str | None:
    """The surface the session in *metadata* runs in; see `cmux.navigation.locate`."""
    return cmux.navigation.locate(metadata, runs_harness)


def show(
    metadata: interface.Metadata | None,
    config: Config,
    on_resume: abc.Callable[[str], None] | None = None,
) -> bool:
    """Focus its surface, or resume a session that has none."""
    if metadata is None:
        return False

    try:
        target = locate(metadata)
    except cmux.navigation.CmuxUnavailable:
        return False

    channel = metadata.get("channel")
    if target == cmux.navigation.UNKNOWN:
        # Either answer could be wrong: a switch may land on a stranger, and a
        # recreate may start a second copy of a live session.
        _log.warning("not switching to %s: could not tell which surface runs it", channel)
        return False

    if target == cmux.navigation.AMBIGUOUS:
        # Recreating would add a third copy of a session that already has two.
        _log.warning("not switching to %s: several surfaces run it", channel)
        return False

    if target is None:
        return cmux.recreate.recreate(metadata, config)

    return cmux.navigation.switch_to_surface(target)


def terminal() -> interface.Terminal:
    return interface.Terminal(
        name="cmux",
        workspace_key="",
        here=lambda: bool(os.environ.get("CMUX_SURFACE_ID")),
        show=show,
        exists=lambda tty, socket=None, not_after=None: None,  # see the module docstring
    )
