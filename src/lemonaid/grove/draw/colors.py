"""The grove's palette: the inbox's status colors, plus leaves, bark and ground."""

from ...brief import colors
from ...inbox import context_color
from ..model import Lemon
from .canvas import BACKGROUND, mix

STATUS = {
    "alert": colors.ALERT_COLOR,
    "blocked": colors.ATTENTION_COLOR,
    "running": colors.RUNNING_COLOR,
    "merge": colors.MERGE_COLOR,
    "approve": colors.APPROVE_COLOR,
    "review": colors.REVIEW_COLOR,
    "done": "#285995",
}
ON_STATUS = {"blocked": "#000000", "merge": "#000000"}  # text on a status fill; white otherwise
# The inbox's order, most urgent first, for a tree that shows one status for all its lemons.
RANK = ("alert", "blocked", "running", "merge", "approve", "review", "done")

TEXT = "#e6ebf2"
MUTED = "#7c8696"
IDLE = "#8b949e"
TAG = "#4a5260"
LEMON = "#f2d94e"
LEAF = ("#2b5230", "#3d7039", "#548f45", "#79b25a")  # a crown's shades, darkest first
LEAD_LEAF = ("#33602f", "#4a8540", "#66a850", "#93cc68")
TRUNK = "#8a6239"
TRUNK_SHADE = "#5a3c24"
BAR = "#161b24"


def status_text(status: str) -> str:
    """A status word's color on a plain dark background."""
    return colors.status_text_style(status).removeprefix("bold ") or TEXT


def on_status(status: str) -> str:
    return ON_STATUS.get(status, "#ffffff")


def tree_status(lemons: tuple[Lemon, ...]) -> str:
    """The most urgent status among *lemons*, in the inbox's order; "" when none has one."""
    present = {lemon.status for lemon in lemons}
    return next((status for status in RANK if status in present), "")


_ON_LEAF = {"done": "#6f9fe0"}  # status colors too dark to see on a crown


def lemon_color(lemon: Lemon, phase: float) -> str:
    """A lemon's dot: its status color, grey when it has none, pulsing toward the background mid-turn."""
    base = _ON_LEAF.get(lemon.status) or STATUS.get(lemon.status, IDLE)
    if lemon.quiet:
        base = mix(base, BACKGROUND, 0.4)
    return mix(base, BACKGROUND, 0.85 * phase) if lemon.working else base


def reading_color(context: str) -> str:
    """A context reading's color, as the inbox colors it; *context* is like "42%"."""
    if not context.rstrip("%").isdigit():
        return IDLE

    return context_color.color(int(context.rstrip("%"))).triplet.hex


def lemon_glyph(lemon: Lemon) -> str:
    return "∘" if lemon.status == "done" else "●"
