"""The grove in a fast tmux popup, running in its hidden session between popups."""

import functools
import subprocess
from collections import abc

from ... import go
from ...config import load_config
from ...inbox import db
from ...lemon_watchers.common import detect_terminal_switch_source
from ..layout import view
from ..tui.app import GroveApp
from . import edits, live


def _switch_source() -> str | None:
    source = detect_terminal_switch_source()
    return None if source == "unknown" else source


def _choose(channel: str, client: str) -> str:
    with db.connect() as conn:
        found = db.get_by_channel(conn, channel, unread_only=False)
    if found is None:
        return f"No live lemon on {channel}"

    try:
        go.jump_tmux(found, client)
    except (LookupError, ValueError, OSError, subprocess.SubprocessError) as error:
        return f"Could not switch to {found.name or channel}: {error}"
    return ""


def run(
    opener: abc.Callable[[], str],
    rename_session: abc.Callable[[str, str], str],
    hide: abc.Callable[[], None],
) -> None:
    """Show the grove until its session ends, switching the client that last opened the popup
    to the lemon chosen and hiding the popup after each choice.
    """
    config = load_config()
    GroveApp(
        lambda: live.fresh(config, _switch_source()),
        refresh_every=3.0,
        edit=functools.partial(edits.ask, config=config, rename_session=rename_session),
        choose=lambda channel: _choose(channel, opener()),
        leave=hide,
        pan=view.load,
        keep_pan=view.save,
        nudge=(config.tui.grove_pan_columns, config.tui.grove_pan_rows),
    ).run()
