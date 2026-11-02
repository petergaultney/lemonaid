"""The grove's palette: the inbox's status colors, plus leaves, bark and ground."""

from ... import config, status_registry
from ...brief import colors
from ...inbox import context_color, provider_color
from ..model import Lemon
from .canvas import BACKGROUND, mix

ALERT = colors.ALERT_COLOR  # warnings that aren't a lemon's status
WARN = colors.ATTENTION_COLOR
TEXT = "#e6ebf2"
MUTED = "#7c8696"
IDLE = "#8b949e"
BRANCH = "#c678dd"  # the inbox draws branches in the terminal's magenta; the canvas needs a hex
TAG = "#4a5260"
PULSE_DEPTH = 0.45
LEMON = "#f2d94e"
LEAF = ("#2b5230", "#3d7039", "#548f45", "#79b25a")  # a crown's shades, darkest first
LEAD_LEAF = ("#33602f", "#4a8540", "#66a850", "#93cc68")
TRUNK = "#8a6239"
TRUNK_SHADE = "#5a3c24"
BAR = "#161b24"


def status_text(status: str) -> str:
    """A status word's color on a plain dark background."""
    return colors.status_text_style(status).removeprefix("bold ") or TEXT


def fill(status: str) -> str:
    """A status's fill color; "" for a word that isn't a configured status."""
    found = status_registry.by_name(config.brief_statuses()).get(status)
    return found.fill if found else ""


def on_status(status: str) -> str:
    found = status_registry.by_name(config.brief_statuses()).get(status)
    return found.on_fill if found else "#ffffff"


def tree_status(lemons: tuple[Lemon, ...]) -> str:
    """The most urgent status among *lemons*, in the inbox's order; "" when none has one."""
    present = {lemon.status for lemon in lemons}
    return next((s.name for s in config.brief_statuses() if s.name in present), "")


def lemon_color(lemon: Lemon, phase: float) -> str:
    """A lemon's dot: its status's text color, which shows on a crown where its fill wouldn't,
    grey when it has none, pulsing toward the background mid-turn.
    """
    base = status_text(lemon.status) if fill(lemon.status) else IDLE
    if lemon.quiet:
        base = mix(base, BACKGROUND, 0.4)
    return mix(base, BACKGROUND, PULSE_DEPTH * phase) if lemon.working else base


def reading_color(context: str) -> str:
    """A context reading's color, as the inbox colors it; *context* is like "42%"."""
    if not context.rstrip("%").isdigit():
        return IDLE

    return context_color.color(int(context.rstrip("%"))).triplet.hex


def lemon_glyph(lemon: Lemon) -> str:
    if lemon.jump_problem:
        return "x"

    return "∘" if lemon.status == "done" else "●"


def model_color(lemon: Lemon) -> str:
    """A lemon's model label color, as the inbox colors it by provider."""
    return provider_color.color(lemon.channel, lemon.provider) or MUTED
