"""A lemon's context use before its model label, coloured from blue to red at its threshold."""

import itertools

from rich.color import Color
from rich.style import Style
from rich.text import Text

_META = "lemonaid_context"
# Percent of the threshold to colour, interpolated between stops. Red is the
# threshold itself; past it the colour keeps going to magenta.
_STOPS = (
    (0, (75, 0, 130)),  # deep purple, which a working lemon is already past
    (15, (50, 130, 255)),  # blue
    (40, (0, 200, 100)),  # green
    (70, (255, 220, 0)),  # yellow
    (100, (255, 60, 30)),  # red
    (130, (255, 0, 255)),  # magenta
)


def _color(percent: int) -> Color:
    clamped = max(_STOPS[0][0], min(_STOPS[-1][0], percent))
    for (p1, c1), (p2, c2) in itertools.pairwise(_STOPS):
        if clamped <= p2:
            t = (clamped - p1) / (p2 - p1)
            return Color.from_rgb(*(a + t * (b - a) for a, b in zip(c1, c2, strict=True)))

    return Color.from_rgb(*_STOPS[-1][1])


def text(percent: int) -> Text:
    # Two cells before the model, as a filled row has: the badge's padding and the model's.
    reading = Text.assemble((f"{min(percent, 999)}%", Style(color=_color(percent))), "  ")
    reading.stylize(Style(meta={_META: percent}))
    return reading


def split(cell: Text) -> tuple[Text, Text]:
    """A backend cell as its context reading, possibly empty, and its model label."""
    end = next(
        (
            span.end
            for span in cell.spans
            if isinstance(span.style, Style) and span.style.meta.get(_META) is not None
        ),
        0,
    )
    return cell[:end], cell[end:]


def filled(reading: Text) -> Text:
    """The reading as a badge in its colour, padded a cell each side, as a status fill shows the model."""
    percent = next(
        (
            span.style.meta[_META]
            for span in reading.spans
            if isinstance(span.style, Style) and span.style.meta.get(_META) is not None
        ),
        None,
    )
    if percent is None:
        return reading

    background = _color(percent)
    red, green, blue = background.get_truecolor()
    dark = 0.299 * red + 0.587 * green + 0.114 * blue < 110  # the purple end
    badge = Style(color="#ffffff" if dark else "#000000", bgcolor=background)
    return Text.assemble((f" {reading.plain.rstrip()} ", badge))


def padded_model(reading: Text, model: Text, style: Style) -> Text:
    """A model badge one cell wider on the left when a reading badge sits beside it."""
    return Text.assemble((" ", style), model) if reading.plain else model
