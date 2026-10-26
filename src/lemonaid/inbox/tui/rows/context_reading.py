"""A lemon's context use before its model label, coloured from blue to red at its threshold."""

from rich.style import Style
from rich.text import Text

from ...context_color import color

_META = "lemonaid_context"


def text(percent: int) -> Text:
    # Two cells before the model, as a filled row has: the badge's padding and the model's.
    reading = Text.assemble((f"{min(percent, 999)}%", Style(color=color(percent))), "  ")
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

    background = color(percent)
    red, green, blue = background.get_truecolor()
    dark = 0.299 * red + 0.587 * green + 0.114 * blue < 110  # the purple end
    badge = Style(color="#ffffff" if dark else "#000000", bgcolor=background)
    return Text.assemble((f" {reading.plain.rstrip()} ", badge))


def padded_model(reading: Text, model: Text, style: Style) -> Text:
    """A model badge one cell wider on the left when a reading badge sits beside it."""
    return Text.assemble((" ", style), model) if reading.plain else model
