"""Load the grove from the inbox's latest refresh, or fresh from the database.

Loading also lays out anything new and saves the layout, so a block or tree keeps the place it
was first given.
"""

import dataclasses
import time
from collections import abc
from pathlib import Path
from typing import Any

from ... import go
from ...config import Config
from ...inbox import db
from ...inbox.tui.live import inbox_frame
from ..draw import card
from ..layout import arrange, landmarks, state
from ..model import Block
from ..tui.frame import Grove
from . import blocks, inputs, lemon_cards


def home(saved: dict[str, Any]) -> str:
    """The group drawn as block 0 with the lemons in no group, as `lemonaid grove home` saved it."""
    return saved.get("home", "")


def _arranged(
    read: inputs.Inputs, config: Config, cards: bool = True, where: Path | None = None
) -> Grove:
    """*cards* makes each lemon's card, which reads the filesystem: only off the event loop."""
    read = dataclasses.replace(read, jump_problems=go.jump_problems(read.rows)) if cards else read
    found = blocks.blocks(
        read,
        config.tui.context_threshold,
        home=home(state.load(where)),
        first=config.tui.grove_first_block,
    )
    arranged: list[tuple[arrange.Arrangement, dict[str, Any]]] = []

    def lay_out(saved: dict[str, Any]) -> dict[str, Any]:
        arranged.append(
            arrange.arrange(found, landmarks.with_packhouse(saved, config.tui.grove_packhouse))
        )
        return arranged[0][1]

    state.update(lay_out, where)
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


def fresh(config: Config, switch_source: str | None, where: Path | None = None) -> Grove:
    with db.connect() as conn:
        read = inputs.read(conn, config, switch_source)
    return _arranged(read, config, where=where)


def current_blocks(config: Config, switch_source: str | None) -> tuple[Block, ...]:
    with db.connect() as conn:
        read = inputs.read(conn, config, switch_source)
    read = dataclasses.replace(read, jump_problems=go.jump_problems(read.rows))
    return blocks.blocks(
        read,
        config.tui.context_threshold,
        home=home(state.load()),
        first=config.tui.grove_first_block,
    )


def preview(config: Config, switch_source: str | None, where: Path | None = None) -> Grove:
    """The grove as `fresh` would lay it out, without saving anything new."""
    found = current_blocks(config, switch_source)
    saved = landmarks.with_packhouse(state.load(where), config.tui.grove_packhouse)
    return Grove(found, *arrange.arrange(found, saved))
