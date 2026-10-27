"""Group-colored inbox bars with a symbol badge for each represented brief status."""

from rich.style import Style
from rich.text import Text
from textual.color import Color

from ... import sections
from ..rows.brief_cards import STATUS_STYLES

_STATUS_GLYPHS = {
    "alert": "!",
    "blocked": "?",
    "running": "N",
    "merge": "m",
    "approve": "✓",
    "review": "r",
    "done": "d",
}


def _badges(header: sections.Header) -> Text:
    text = Text(" " if header.status_counts else "", style=Style(underline=False))
    for status, count in header.status_counts:
        text.append(
            f" {_STATUS_GLYPHS[status]}{count} ",
            STATUS_STYLES[status] + Style(bold=True, underline=False),
        )
    return text


def style(header: sections.Header) -> Style:
    color = Color.parse(header.group.color)
    luminance = sum(
        weight * (channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
        for channel, weight in zip(color.normalized, (0.2126, 0.7152, 0.0722), strict=True)
    )
    foreground = "#000000" if (luminance + 0.05) / 0.05 >= 1.05 / (luminance + 0.05) else "#ffffff"
    return Style(color=foreground, bgcolor=color.hex, bold=True, underline=True)


def label(
    header: sections.Header,
    width: int = 0,
    selected: bool = False,
    digit: str = "",
    *,
    end_marker: bool = True,
) -> Text:
    """Keep the tally and status badges visible before shortening a long group name."""
    called = f"{digit} {header.group.name}" if digit else header.group.name
    arrow = "▸" if header.group.collapsed else "▾"
    name = Text(f"{arrow} {called}")
    tail = Text.assemble(f" ({header.tally})", _badges(header))
    fill = style(header)
    marker = Style(color=fill.bgcolor, bgcolor=fill.color, bold=True, underline=False)
    end = Text(" ◀ ", style=marker) if selected and end_marker else Text("")
    if width:
        name.truncate(max(0, width - tail.cell_len - end.cell_len), overflow="ellipsis")
    text = Text.assemble(name, tail, style=fill)
    if selected and text.cell_len:
        text.stylize(marker, 0, 1)
    if width:
        text.truncate(max(0, width - end.cell_len))
        text.append(" " * max(0, width - end.cell_len - text.cell_len))
        end.truncate(width)
        text.append_text(end)
    return text


def cells(
    header: sections.Header,
    card_width: int,
    columns: int,
    name_cell: int,
    selected: bool = False,
    digit: str = "",
    *,
    name_width: int = 0,
) -> list[Text]:
    """The header as a card or as a row of cells."""
    if card_width:
        return [label(header, card_width, selected, digit)]

    return [
        label(header, name_width, selected, digit, end_marker=False)
        if i == name_cell
        else Text("", style=style(header))
        for i in range(columns)
    ]


def background(header: sections.Header) -> Style:
    return Style(bgcolor=header.group.color)
