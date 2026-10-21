"""Dim the whole inbox while its tmux pane is not the selected one."""

from functools import lru_cache

from rich.color import Color as RichColor
from rich.segment import Segment
from rich.style import Style
from rich.terminal_theme import DEFAULT_TERMINAL_THEME
from textual.color import Color
from textual.filter import LineFilter, dim_color

_FAINT = Style(dim=True)


_BLACK = RichColor.from_rgb(0, 0, 0)


def _rgb(color: RichColor | None, default: RichColor) -> RichColor:
    """*color* as RGB; a palette index is resolved, and no colour or the terminal default is *default*."""
    if color is None or color.is_default:
        return default

    if color.triplet is None:
        return RichColor.from_triplet(color.get_truecolor(DEFAULT_TERMINAL_THEME))

    return color


@lru_cache(1024)
def _faded(style: Style, background: RichColor, keep: float) -> Style:
    if style.color is None or style.color.is_default:
        return style

    behind = _rgb(style.bgcolor, _rgb(background, _BLACK))
    return style + Style.from_color(dim_color(behind, _rgb(style.color, _BLACK), keep), None)


class Dim(LineFilter):
    """Quiets everything drawn without painting a background.

    `strength` is the share of each foreground colour blended away toward the
    background behind it; None uses the terminal's own faint attribute instead.
    Backgrounds are left as they are, so a transparent terminal stays transparent.
    """

    def __init__(self, strength: float | None = None, enabled: bool = True) -> None:
        super().__init__(enabled=enabled)
        self.strength = strength

    def apply(self, segments: list[Segment], background: Color) -> list[Segment]:
        strength = self.strength
        behind = background.rich_color
        return [
            segment
            if segment.control or segment.style is None
            else Segment(
                segment.text,
                segment.style + _FAINT
                if strength is None
                else _faded(segment.style, behind, 1 - strength),
            )
            for segment in segments
        ]


def strength(setting: str) -> float | None:
    """The blend for a `[tui] unfocused_dim` setting; None for `off` and the faint attribute."""
    return None if setting in ("off", "dim") else float(setting) / 100
