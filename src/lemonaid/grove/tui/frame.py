"""One screenful of the grove: the scene for where the keys have taken it, with its title and prompt."""

import dataclasses
from typing import Any

from ..draw import bars, block_scene, canvas, colors, lemon_list, scene_parts, scenes
from ..layout.arrange import Arrangement
from ..model import Block
from . import keys, picking


@dataclasses.dataclass(frozen=True)
class Grove:
    blocks: tuple[Block, ...]
    arrangement: Arrangement
    saved: dict[str, Any]  # the layout *arrangement* was made from, as `arrange` keeps it


def _summary(grove: Grove) -> str:
    lemons = [lemon for block in grove.blocks for tree in block.trees for lemon in tree.lemons]
    working = sum(lemon.working for lemon in lemons)
    trees = sum(len(block.trees) for block in grove.blocks)
    return f"{len(lemons)} lemons on {trees} trees · {working} mid-turn"


def _picked_prompt(where: keys.Where, grove: Grove) -> str:
    block = next((b for b in grove.blocks if b.digit == where.block), None)
    letter = grove.arrangement.trees.get((block.name, where.picked_tree)) if block else None
    return picking.prompt(where, grove.blocks, letter.letter if letter else "")


def _prompt(where: keys.Where, grove: Grove) -> tuple[str, str]:
    if where.note:
        return where.note, colors.STATUS["blocked"]
    if picked := _picked_prompt(where, grove):
        return picked, colors.TEXT
    if where.search is not None:
        found = keys.matches(grove.blocks, where.search)
        if not where.search:
            return "/ type a Brief-ID, a session or a name · esc cancels", colors.TEXT
        if not found:
            return f"/{where.search}  no match · esc cancels", colors.TEXT
        chosen = found[where.chosen % len(found)]
        blocks = len({m.block.digit for m in found})
        letter = grove.arrangement.trees[(chosen.block.name, chosen.tree.key)].letter
        return (
            f"/{where.search}  {len(found)} match{'es' * (len(found) > 1)} in {blocks} block{'s' * (blocks > 1)}"
            f" · {chosen.lemon.brief_id or chosen.lemon.name} on {chosen.block.digit}{letter}"
            " · enter jumps · ↑↓ choose · esc cancels",
            colors.TEXT,
        )
    if where.tree:
        what = "letter" if where.number else "place on the tree, 2 to 9, or 0 and a letter past 9"
        return (
            f"{where.block}{where.tree.upper()}{where.number}: type the lemon's {what} · esc backs out",
            colors.TEXT,
        )
    block = next((b for b in grove.blocks if b.digit == where.block), None)
    if block:
        longer = [
            b.digit
            for b in grove.blocks
            if b.digit != where.block and b.digit.startswith(where.block)
        ]
        more = f"  (another digit: {', '.join(longer)})" if longer else ""
        return (
            f"{where.block} · {block.name or 'no group'}: a tree's letter takes its first lemon, l is the lead's, a capital and a place the others, Alt and r, s, a, p, g or c edits{more}",
            colors.TEXT,
        )
    return "type a block number, or / to search · ? keys · esc closes", colors.MUTED


def _picked(grove: Grove, where: keys.Where) -> scene_parts.Highlight | None:
    tree = next(
        (
            tree
            for block in grove.blocks
            if block.digit == where.block
            for tree in block.trees
            if tree.key == where.picked_tree
        ),
        None,
    )
    if tree is None:
        return None

    channels = frozenset(lemon.channel for lemon in tree.lemons)
    edited = where.picked_lemon or lemon_list.session(tree)
    return scene_parts.Highlight(channels, where.picked_lemon or tree.lemons[0].channel, edited)


def clamp_pan(grove: Grove, where: keys.Where, width: int, height: int) -> keys.Where:
    """*where* with its pan no further than the grove's edges allow on a screen this size."""
    view = scene_parts.grove_view((width, height), grove.arrangement, where.pan)
    pan = (view.left, view.top)
    return where if pan == where.pan else dataclasses.replace(where, pan=pan)


# Where each zoomed block's lemon lists went, by (block digit, screen width, height), then tree.
Lists = dict[tuple[str, int, int], dict[str, tuple[int, int]]]


def render(
    grove: Grove,
    where: keys.Where,
    width: int,
    height: int,
    phase: float,
    lists: Lists | None = None,
) -> canvas.Canvas:
    """The grove's picture for *where*. With *lists*, a zoomed block's lemon lists stay where they
    were drawn last time while they cover nothing.
    """
    picture = canvas.blank(width, height)
    if not scene_parts.fits(picture):
        return picture

    found = keys.matches(grove.blocks, where.search) if where.search else []
    highlight = (
        scene_parts.Highlight(
            frozenset(m.lemon.channel for m in found),
            found[where.chosen % len(found)].lemon.channel,
        )
        if found
        else None
    )
    highlight = _picked(grove, where) or highlight
    found_blocks = {m.block.digit for m in found}
    zoom = where.block or (next(iter(found_blocks)) if len(found_blocks) == 1 else "")
    block = next((b for b in grove.blocks if b.digit == zoom), None)
    if block:
        block_scene.zoomed(
            picture,
            block,
            grove.arrangement,
            phase,
            highlight,
            where.tree.lower(),
            None if lists is None else lists.setdefault((block.digit, width, height), {}),
        )
    else:
        scenes.overview(picture, grove.blocks, grove.arrangement, phase, highlight, where.pan)
    panning = not block and scene_parts.pans(picture, grove.arrangement)
    bars.title(
        picture,
        _summary(grove),
        "digit zooms · letter jumps · / searches · "
        + ("arrows pan · ⇧1-8 compass · " if panning else "")
        + "? keys · space closes",
    )
    bars.prompt(picture, *_prompt(where, grove))
    return picture
