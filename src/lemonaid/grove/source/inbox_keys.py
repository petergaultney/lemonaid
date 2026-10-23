"""The grove's keys in the inbox: each lemon's key for its row, and the bar that takes one."""

from ...config import Config
from ...inbox.tui.live import inbox_frame
from ..tui import keys
from ..tui.frame import Grove
from ..tui.jump_bar import JumpBar
from . import live


def grove(frame: inbox_frame.Frame, config: Config) -> Grove:
    """The grove for *frame*, laying out and saving anything new, as opening the grove would."""
    return live.from_inbox(lambda: frame, config)()


def names(found: Grove) -> dict[str, str]:
    return keys.names(found.blocks, found.arrangement)


def digits(found: Grove) -> dict[str, str]:
    """Each group's block digit, by group name."""
    return {block.name: block.digit for block in found.blocks if block.name}


def jump_bar(found: Grove, first: str) -> JumpBar:
    return JumpBar(found, first)
