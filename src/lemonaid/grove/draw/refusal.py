"""A drag that couldn't drop where it is, tinted red on the screen while it is there."""

import dataclasses

from ..model import Plot
from . import bars, plots
from .canvas import Canvas


@dataclasses.dataclass(frozen=True)
class Refusal:
    target: tuple[str, ...] = ()  # the click target of a dragged tree or bare tree
    plot: Plot | None = None  # a dragged block's or open ground's plot, where it would go


def tint(canvas: Canvas, refusal: Refusal, view: plots.View) -> None:
    """*refusal*'s tree or ground in alert red; *view* is the one its plot is drawn in."""
    if refusal.target:
        bars.flash(canvas, refusal.target)
    if refusal.plot is None:
        return

    for col, row in plots.ground_at(refusal.plot, view):
        if 0 < row < canvas.height - 1 and 0 <= col < canvas.width:  # the title and prompt stay
            bars.tint(canvas.rows[row][col])
