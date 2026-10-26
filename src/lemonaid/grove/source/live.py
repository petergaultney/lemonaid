"""Load the grove from the inbox's latest refresh, or fresh from the database.

Loading also lays out anything new and saves the layout, so a block or tree keeps the place it
was first given.
"""

import time
from collections import abc
from typing import Any

from ...config import Config
from ...inbox import db
from ...inbox.tui.live import inbox_frame
from ..draw import card
from ..layout import arrange, state
from ..tui.frame import Grove
from . import blocks, inputs, lemon_cards


def _arranged(read: inputs.Inputs, config: Config, cards: bool = True) -> Grove:
    """*cards* makes each lemon's card, which reads the filesystem: only off the event loop."""
    found = blocks.blocks(read, config.tui.context_threshold)
    arranged: list[tuple[arrange.Arrangement, dict[str, Any]]] = []

    def lay_out(saved: dict[str, Any]) -> dict[str, Any]:
        arranged.append(arrange.arrange(found, saved))
        return arranged[0][1]

    state.update(lay_out)
    return Grove(
        found,
        *arranged[0],
        lemon_cards.by_channel(read, config, card.INNER + 1, time.time()) if cards else {},
    )


def from_inbox(
    latest_frame: abc.Callable[[], inbox_frame.Frame | None], config: Config, cards: bool = True
) -> abc.Callable[[], Grove]:
    """A loader that reuses the inbox's last frame of live sessions instead of reading them again.
    Without *cards* it makes no lemon cards, for a caller on the event loop.
    """

    def load() -> Grove:
        frame = latest_frame()
        with db.connect() as conn:
            read = inputs.from_frame(conn, frame) if frame else inputs.read(conn, config, None)
        return _arranged(read, config, cards)

    return load


def fresh(config: Config, switch_source: str | None) -> Grove:
    with db.connect() as conn:
        read = inputs.read(conn, config, switch_source)
    return _arranged(read, config)


def preview(config: Config, switch_source: str | None) -> Grove:
    """The grove as `fresh` would lay it out, without saving anything new."""
    with db.connect() as conn:
        read = inputs.read(conn, config, switch_source)
    found = blocks.blocks(read, config.tui.context_threshold)
    return Grove(found, *arrange.arrange(found, state.load()))
