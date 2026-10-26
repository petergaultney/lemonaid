"""What the grove's scenes share: search highlighting, fading, drawing one tree, and the size check."""

import dataclasses
from collections import abc

from ..layout import sizes
from ..layout.arrange import Arrangement
from ..model import WORLD_HEIGHT, WORLD_WIDTH, Block, Tree
from . import colors, tag_fit, tree_stats, trees
from .canvas import Canvas, text
from .plots import View


@dataclasses.dataclass(frozen=True)
class Highlight:
    """What a search matched: everything else is drawn faded."""

    channels: frozenset[str]
    selected: str  # the channel `enter` would jump to
    # What an edit would change: a lemon's channel, or `lemon_list.session(tree)`.
    edited: str = ""


def fade(highlight: Highlight | None, channels: abc.Iterable[str]) -> float:
    if highlight is None:
        return 0.0

    return 0.0 if highlight.channels & set(channels) else 0.8


def block_channels(block: Block) -> list[str]:
    return [lemon.channel for tree in block.trees for lemon in tree.lemons]


def tree_channels(tree: Tree) -> list[str]:
    return [lemon.channel for lemon in tree.lemons]


def place_tree(
    block: Block,
    tree: Tree,
    arrangement: Arrangement,
    view: View,
    scale: float,
    full_tag: bool,
    tallest: float = trees.GROWN,
) -> tuple[float, float, trees.Shape]:
    """Where *tree*'s crown is centered on screen, and its shape there, no taller than *tallest*
    rows from its center.
    """
    standing = arrangement.trees[(block.name, tree.key)]
    plot = arrangement.plots[block.name]
    shape = trees.shape(
        dataclasses.replace(tree, label=standing.label),
        standing.letter if full_tag else f"{block.digit}{standing.letter}",
        standing.size * scale,
        full_tag,
        tallest,
    )
    ax, ay = view.screen(plot.x + standing.cx, plot.y + standing.cy)
    return ax, ay, shape


@dataclasses.dataclass(frozen=True)
class Planted:
    """A tree to draw: where it stands on screen, how faded, and the columns its block spans.
    *whole_key* tags it with its block's digit as well as its letter, as the grove view does.
    """

    block: Block
    tree: Tree
    placed: tuple[float, float, trees.Shape]
    dim: float
    bounds: tuple[int, int]
    whole_key: bool = False


def plant(
    canvas: Canvas,
    planted: abc.Sequence[Planted],
    arrangement: Arrangement,
    phase: float,
    highlight: Highlight | None,
    taken: abc.Iterable[tag_fit.Rect] = (),
    stats: bool = False,
) -> list[tag_fit.Fitted]:
    """Draw every tree, then every tag where it covers nothing already drawn or in *taken*. With
    *stats*, a tag shows its tree's stats in place of its name, emoji and pin.
    """
    tags = []
    occupied = list(taken)
    for p in planted:
        ax, ay, shape = p.placed
        letter = arrangement.trees[(p.block.name, p.tree.key)].letter
        canvas.dim, canvas.target = p.dim, (p.block.digit, letter)
        bottom = trees.draw(
            canvas,
            p.tree,
            shape,
            ax,
            ay,
            phase,
            hits=highlight.channels if highlight else (),
            pennant=p.block.color if p.tree.lead else "",
        )
        occupied.append(trees.crown_box(shape, ax, ay))
        if p.tree.lead:
            occupied.append(trees.pennant_box(shape, ax, ay))
        labeled = dataclasses.replace(
            p.tree, label=arrangement.trees[(p.block.name, p.tree.key)].label
        )
        shown = f"{p.block.digit}{letter}" if p.whole_key else letter
        if stats:
            labeled = tree_stats.tagged(labeled)
            shape = dataclasses.replace(shape, tag=(trees.short_tag(labeled, shown, shape.width),))
        tags.append(tag_fit.Tag(labeled, shown, shape, ax, ay, bottom, p.bounds))
    order = sorted(range(len(tags)), key=lambda i: (tags[i].bottom, tags[i].ax))
    fitted = dict(zip(order, tag_fit.fit([tags[i] for i in order], occupied), strict=True))
    for i, p in enumerate(planted):
        found = fitted[i]
        letter = arrangement.trees[(p.block.name, p.tree.key)].letter
        canvas.dim, canvas.target = p.dim, (p.block.digit, letter)
        trees.draw_tag(
            canvas,
            tags[i].tree,
            found.lines,
            found.x,
            found.y,
            found.trunk,
            phase,
            selected=bool(highlight and highlight.selected in tree_channels(p.tree)),
            key=len(tags[i].letter),
            bark=tags[i].shape.bark,
        )
        if stats:
            tree_stats.color_context(canvas, found.lines[0], found.x, found.y)
    canvas.dim, canvas.target = 0.0, ()
    return [fitted[i] for i in range(len(planted))]


# The grove view shrinks to fit the screen down to this many cells a grove unit, across and
# down; past that, trees and tags get too cramped to read, and the view pans instead.
LEAST_SCALE = (1.1, sizes.ROWS_PER_UNIT)


def extent(arrangement: Arrangement) -> tuple[int, int]:
    """How far the grove reaches, across and down, in grove units."""
    grounds = [*arrangement.plots.values(), *arrangement.open]
    return (
        max([WORLD_WIDTH, *(p.x + p.w for p in grounds)]),
        max([WORLD_HEIGHT, *(p.y + p.h for p in grounds)]),
    )


def grove_view(
    size: tuple[int, int], arrangement: Arrangement, pan: tuple[float, float] = (0.0, 0.0)
) -> View:
    """The grove scaled to fit a screen of *size* below the title row and above the prompt
    row, or, on a screen too small for that, at its least scale with *pan*'s grove point at the
    top left, as near it as the grove's edges allow.
    """
    width, height = size
    right, bottom = extent(arrangement)
    sx = max(LEAST_SCALE[0], width / right)
    sy = max(LEAST_SCALE[1], (height - 2) / bottom)
    left = min(pan[0], max(0, right - width / sx))
    top = min(pan[1], max(0, bottom - (height - 2) / sy))
    return View(left, top, sx, sy)


def pans(canvas: Canvas, arrangement: Arrangement) -> bool:
    """Whether the grove is too big for *canvas* and pans."""
    right, bottom = extent(arrangement)
    return canvas.width / right < LEAST_SCALE[0] or (canvas.height - 2) / bottom < LEAST_SCALE[1]


# Room framed around a tree standing past its plot's edge, the same whatever its lemons, so the
# view never moves as they come and go: half a tree's width, and its crown's height.
_SPILL = (9, 6)


def block_view(canvas: Canvas, arrangement: Arrangement, block: Block) -> View:
    """*block* filling the screen, centered, with the grove view's proportions, so a block
    zoomed in keeps the shape it has in the grove. Trees that spill past its plot are framed too.
    """
    plot = arrangement.plots[block.name]
    ground = [(0, 0, plot.w, plot.h)]
    for tree in block.trees:
        s = arrangement.trees[(block.name, tree.key)]
        if not (0 <= s.cx <= plot.w and 0 <= s.cy <= plot.h):
            ground.append((s.cx - _SPILL[0], s.cy - _SPILL[1], 2 * _SPILL[0], _SPILL[1] + 3))
    left, top = min(r[0] for r in ground), min(r[1] for r in ground)
    w = max(r[0] + r[2] for r in ground) - left
    h = max(r[1] + r[3] for r in ground) - top
    whole = grove_view((canvas.width, canvas.height), arrangement)
    ratio = whole.sx / whole.sy
    sx = min((canvas.width - 6) / w, (canvas.height - 6) / h * ratio)
    sy = sx / ratio
    return View(
        plot.x + left,
        plot.y + top,
        sx,
        sy,
        ox=round((canvas.width - w * sx) / 2),
        oy=round((canvas.height - h * sy) / 2),
    )


MIN_WIDTH, MIN_HEIGHT = 30, 10


def fits(canvas: Canvas) -> bool:
    """Whether *canvas* is big enough to draw on; when not, it says so in its first row."""
    if canvas.width >= MIN_WIDTH and canvas.height >= MIN_HEIGHT:
        return True

    text(canvas, 0, 0, f"The grove needs {MIN_WIDTH}x{MIN_HEIGHT}", colors.TEXT)
    return False
