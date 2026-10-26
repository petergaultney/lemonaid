"""The grove screen as the inbox opens it, drawn from what the inbox last read."""

import functools
from collections import abc

from ...config import Config
from ...inbox.tui.live import inbox_frame
from ..layout import view
from ..tui import flip
from ..tui.screen import GroveScreen
from . import edits, live


def for_inbox(
    latest_frame: abc.Callable[[], inbox_frame.Frame | None],
    config: Config,
    rename_session: abc.Callable[[str, str], str] | None = None,
) -> GroveScreen:
    """*rename_session(old, new)* renames a tmux session, for renaming a tree from the grove."""
    return GroveScreen(
        live.from_inbox(latest_frame, config),
        edit=functools.partial(edits.ask, config=config, rename_session=rename_session),
        pan=view.load(),
        keep_pan=view.save,
        nudge=(config.tui.grove_pan_columns, config.tui.grove_pan_rows),
        big_trees=config.tui.grove_big_trees,
        flips=flip.configured(config),
    )
