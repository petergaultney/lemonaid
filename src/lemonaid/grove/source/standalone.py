"""The grove run on its own, as `lemonaid grove open` does in a popup, then a switch to the chosen lemon."""

import functools
import sys

from ... import handlers
from ...config import Config
from ...inbox import db
from ..layout import view
from ..tui.app import GroveApp
from . import live, renames


def run(config: Config, switch_source: str | None) -> None:
    # A fresh read takes a quarter second or so; the inbox's grove reuses its frame instead.
    channel = GroveApp(
        functools.partial(live.fresh, config, switch_source),
        refresh_every=5.0,
        rename=renames.apply,
        pan=view.load,
        keep_pan=view.save,
        nudge=(config.tui.grove_pan_columns, config.tui.grove_pan_rows),
    ).run()
    if not channel:
        return

    with db.connect() as conn:
        found = db.get_by_channel(conn, channel, unread_only=False)
    if found is None:
        print(f"No live lemon on {channel}", file=sys.stderr)
        return

    if not handlers.handle_notification(
        {**found.metadata, "channel": found.channel, "name": found.name or ""},
        config,
        switch_source=found.switch_source,
    ):
        print(
            f"Could not switch to {found.name or channel}; try it from the inbox", file=sys.stderr
        )
