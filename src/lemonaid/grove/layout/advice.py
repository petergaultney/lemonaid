"""What a gardening lemon should know looks off in a laid-out grove: things to weigh, not refusals.

Judged as drawn on a screen of a given size: tags and crowns in the grove view, lemon lists in each
block zoomed in.
"""

import dataclasses
import itertools
import math
from typing import NamedTuple

from ..draw import block_scene, canvas, ground, scene_parts, scenes, tag_fit, trees
from ..model import Block
from . import landmarks
from .arrange import Arrangement

_LEVEL_GAP = 2  # columns between a tag and something on its row that read as bumping into it

Rect = tuple[int, int, int, int]


class Advice(NamedTuple):
    block: str  # its digit
    group: str
    tree: str  # its key
    letter: str
    kind: str
    reason: str


class _Drawn(NamedTuple):
    block: Block
    key: str
    name: str  # its whole key, as `5g`
    crown: Rect
    tag: Rect


def _drawn(
    blocks: tuple[Block, ...], arrangement: Arrangement, size: tuple[int, int]
) -> list[_Drawn]:
    drawn: list[tuple[scene_parts.Planted, tag_fit.Fitted]] = []
    scenes.overview(canvas.blank(*size), blocks, arrangement, 0.0, drawn=drawn)
    return [
        _Drawn(
            p.block,
            p.tree.key,
            f"{p.block.digit}{arrangement.trees[(p.block.name, p.tree.key)].letter}",
            trees.crown_box(p.placed[2], *p.placed[:2]),
            (f.x, f.y, len(f.lines[0]), len(f.lines)),
        )
        for p, f in drawn
        if f.lines and f.lines[0]
    ]


def _beside(tag: Rect, other: Rect) -> int | None:
    """Columns between *tag* and *other* when they share a row, negative when they overlap; None
    when they share no row.
    """
    tx, ty, tw, th = tag
    ox, oy, ow, oh = other
    if min(ty + th, oy + oh) <= max(ty, oy):
        return None

    return max(ox - tx - tw, tx - ox - ow)


def _bumps(drawn: list[_Drawn]) -> list[tuple[_Drawn, str, str]]:
    found = []
    for a, b in itertools.permutations(drawn, 2):
        for what, rect in (("crown", b.crown), ("tag", b.tag)):
            gap = _beside(a.tag, rect)
            if gap is None or gap > _LEVEL_GAP or (what == "tag" and a.key > b.key):
                continue

            if gap < 0:
                found.append(
                    (a, "touching", f"in the grove view its tag runs into {b.name}'s {what}")
                )
            else:
                found.append(
                    (
                        a,
                        "level",
                        f"in the grove view its tag sits level with {b.name}'s {what}, {gap} column{'' if gap == 1 else 's'} away",
                    )
                )
    return found


def _lead_far(block: Block, arrangement: Arrangement) -> list[tuple[str, str, str]]:
    """A warning on *block*'s lead when another of its trees stands nearer the grove's middle."""
    plot, house = arrangement.plots[block.name], arrangement.plots.get(landmarks.PACKHOUSE)
    lead = next((t for t in block.trees if t.lead), None)
    middle = landmarks.middle(dataclasses.asdict(house) if house else None)
    if lead is None or middle is None or plot.texture == "house":
        return []

    def away(key: str) -> float:
        s = arrangement.trees[(block.name, key)]
        return math.hypot(plot.x + s.cx - middle[0], (plot.y + s.cy - middle[1]) * 2)

    nearer = min((t for t in block.trees if not t.lead), key=lambda t: away(t.key), default=None)
    if nearer is None or away(nearer.key) >= away(lead.key):
        return []

    letter = arrangement.trees[(block.name, nearer.key)].letter
    return [
        (
            lead.key,
            "lead-far",
            f"it leads the block, but {block.digit}{letter} stands nearer the packhouse",
        )
    ]


def advise(
    blocks: tuple[Block, ...], arrangement: Arrangement, size: tuple[int, int]
) -> list[Advice]:
    """Each thing a lemon arranging the grove would want to weigh on a *size* screen: a tag that
    runs into or sits level beside another tree's crown or tag in the grove view, a crown past its
    block's edge, a trunk off its block's ground, a lead with another tree nearer the packhouse,
    and a lemon list drawn away from its tree when its block is zoomed in.
    """
    view = scene_parts.grove_view(size, arrangement)
    drawn = _drawn(blocks, arrangement, size)
    found: list[tuple[Block, str, str, str]] = [
        (a.block, a.key, kind, reason) for a, kind, reason in _bumps(drawn)
    ]
    for d in drawn:
        plot = arrangement.plots[d.block.name]
        left, _ = view.screen(plot.x, plot.y)
        right, bottom = view.screen(plot.x + plot.w, plot.y + plot.h)
        x, y, w, h = d.crown
        if x < left or x + w > right or y + h > bottom:
            found.append((d.block, d.key, "border", "its crown reaches past its block's edge"))
        s = arrangement.trees[(d.block.name, d.key)]
        if not ground.inside(plot, plot.x + s.cx, plot.y + s.cy):
            found.append((d.block, d.key, "off-ground", "its trunk stands off its block's ground"))
    for block in blocks:
        found += [(block, key, kind, why) for key, kind, why in _lead_far(block, arrangement)]
        astray: list[str] = []
        block_scene.zoomed(canvas.blank(*size), block, arrangement, 0.0, astray=astray)
        found += [
            (block, key, "list-away", "zoomed in, its lemon list is drawn away from it")
            for key in astray
        ]
    return [
        Advice(block.digit, block.name, key, arrangement.trees[(block.name, key)].letter, kind, why)
        for block, key, kind, why in found
    ]
