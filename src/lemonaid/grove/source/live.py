"""Load the grove from the inbox's latest refresh, or fresh from the database.

Loading also lays out anything new and saves the layout, so a block or tree keeps the place it
was first given.
"""

from collections import abc
from typing import Any

from ...config import Config
from ...inbox import db
from ...inbox.tui.live import inbox_frame
from ..layout import arrange, state
from ..tui.frame import Grove
from . import blocks, inputs


def _arranged(read: inputs.Inputs, config: Config) -> Grove:
    found = blocks.blocks(read, config.tui.context_threshold)
    arranged: list[tuple[arrange.Arrangement, dict[str, Any]]] = []

    def lay_out(saved: dict[str, Any]) -> dict[str, Any]:
        arranged.append(arrange.arrange(found, saved))
        return arranged[0][1]

    state.update(lay_out)
    return Grove(found, *arranged[0])


def from_inbox(
    latest_frame: abc.Callable[[], inbox_frame.Frame | None], config: Config
) -> abc.Callable[[], Grove]:
    """A loader that reuses the inbox's last frame of live sessions instead of reading them again."""

    def load() -> Grove:
        frame = latest_frame()
        with db.connect() as conn:
            read = inputs.from_frame(conn, frame) if frame else inputs.read(conn, config, None)
        return _arranged(read, config)

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
