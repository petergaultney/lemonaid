"""The grove's keys in the inbox: each lemon's key for its row, and the bar that takes one."""

import dataclasses
from collections import abc

from ...config import Config
from ...inbox import sections
from ...inbox.tui.live import inbox_frame
from ...inbox.tui.live.inbox_entries import Entry
from ..tui import keys
from ..tui.frame import Grove
from ..tui.jump_bar import JumpBar
from . import live


def grove(frame: inbox_frame.Frame, config: Config) -> Grove:
    """The grove for *frame*, laying out and saving anything new, as opening the grove would; it
    has no lemon cards, since the inbox makes it on its event loop.
    """
    return live.from_inbox(lambda: frame, config, cards=False)()


def names(found: Grove) -> dict[str, str]:
    return keys.names(found.blocks, found.arrangement)


def digits(found: Grove) -> dict[str, str]:
    """Each group's block digit, by group name."""
    return {block.name: block.digit for block in found.blocks if block.name}


def zoomed(found: Grove, block: str, letter: str) -> tuple[frozenset[str], frozenset[str]]:
    """The channels of the block with digit *block*, and of its tree lettered *letter* (none for
    "" or a letter with no tree).
    """
    zoom = next((b for b in found.blocks if b.digit == block), None)
    if zoom is None:
        return frozenset(), frozenset()

    tree = keys.tree_at(zoom, found.arrangement, letter) if letter else None
    return (
        frozenset(lemon.channel for t in zoom.trees for lemon in t.lemons),
        frozenset(lemon.channel for lemon in tree.lemons) if tree else frozenset(),
    )


def only_block(frame: inbox_frame.Frame, found: Grove, digit: str) -> inbox_frame.Frame:
    """*frame* cut down to the block with digit *digit*: its lemons, drawn under its group alone,
    even a lemon that belongs to other groups too.
    """
    block = next((b for b in found.blocks if b.digit == digit), None)
    if block is None:
        return frame

    channels = {lemon.channel for tree in block.trees for lemon in tree.lemons}
    memberships = {
        channel: tuple(name for name in names if name == block.name)
        for channel, names in frame.active.memberships.items()
    }
    return dataclasses.replace(
        frame,
        matching_ids={n.id for n in frame.active.rows if n.channel in channels},
        groups=[g for g in frame.groups if g.name == block.name],
        active=dataclasses.replace(frame.active, memberships=memberships),
    )


def in_grove_order(entries: abc.Sequence[Entry], found: Grove, digit: str) -> list[Entry]:
    """*entries* with a zoomed block's rows grouped by tree, as the grove lists them: the lead
    tree first, then by letter, each tree's lemons in their key order (`5h`, `5.h1`, `5.h2`).
    Headers stay above the rows.
    """
    block = next((b for b in found.blocks if b.digit == digit), None)
    if block is None:
        return list(entries)

    trees = sorted(
        block.trees, key=lambda t: (not t.lead, found.arrangement.trees[(block.name, t.key)].letter)
    )
    place = {lemon.channel: i for i, lemon in enumerate(lemon for t in trees for lemon in t.lemons)}
    rows = [e for e in entries if isinstance(e, sections.Row)]
    return [
        *(e for e in entries if isinstance(e, sections.Header)),
        *sorted(rows, key=lambda r: place.get(r.notification.channel, len(place))),
    ]


def jump_bar(found: Grove, first: str) -> JumpBar:
    return JumpBar(found, first)
