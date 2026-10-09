"""A group's header line in the inbox list.

An open group's header is plain bold. A collapsed one is filled with the
colour of its most pressing row's band, as that row's card would be, so a
collapsed group still shows what is waiting inside it. Being unread alone
doesn't fill it: an unread row in the group puts a dot on the header instead. The name takes a
stable colour from the palette project labels and tmux windows use: as its
text on an open header, and as a badge inside a collapsed one's fill. Every
header is underlined across its width, the thinnest rule a terminal draws, so
stacked collapsed headers of one colour stay apart.
"""

from rich.style import Style
from rich.text import Text

from .. import sections
from .brief_cards import DOT_STYLES, STATUS_STYLES
from .utils import project_color, unread_marker_style

# White is no status's colour, so the cursor's marker stands out on any fill.
_SELECTED = Style(color="#000000", bgcolor="#ffffff", bold=True, underline=False)


def _quiet(band: str) -> str:
    """The band without its unread half, since being unread alone fills nothing."""
    return {"unread done": "done", "unread": "read"}.get(band, band)


def _fill(header: sections.Header) -> Style:
    if not header.group.collapsed:
        return Style()

    return STATUS_STYLES.get(_quiet(header.band)) or Style(dim=True)


def _dot(header: sections.Header) -> Text:
    """The unread dot, dark on a fill the way a filled card's is."""
    if not header.unread:
        return Text("")

    filled = _quiet(header.band) if header.group.collapsed else ""
    return Text(" ●", style=DOT_STYLES.get(filled) or unread_marker_style())


def style(header: sections.Header) -> Style:
    return _fill(header) + Style(bold=True, underline=True)


def label(header: sections.Header, width: int = 0, selected: bool = False) -> Text:
    """Arrow, name and count, padded to *width* so the fill and rule reach the edge.

    The arrow takes the group's colour, above its cards' rail. Under the cursor
    it turns into a block of that colour, in place, and a white block ends the
    line, since the table's cursor colour is lost under a status fill.
    """
    colour = project_color(header.group.name)
    name = (
        Text(f" {header.group.name} ", style=Style(color="#000000", bgcolor=colour))
        if header.group.collapsed
        else Text(header.group.name, style=Style(color=colour))
    )
    arrow = "▸" if header.group.collapsed else "▾"
    text = Text.assemble(
        # Selected, the space joins the arrow's block, so it runs into a collapsed
        # header's badge rather than leaving a sliver of fill between them.
        (
            f"{arrow} ",
            Style(color="#000000", bgcolor=colour, bold=True, underline=False)
            if selected
            else Style(color=colour),
        ),
        name,
        f" ({header.tally})",
        _dot(header),
        style=style(header),
    )
    if width:
        end = Text(" ◀ ", style=_SELECTED) if selected else Text("")
        text.truncate(width - end.cell_len)
        text.pad_right(width - end.cell_len - text.cell_len)
        text.append_text(end)
    return text


def cells(
    header: sections.Header, card_width: int, columns: int, name_cell: int, selected: bool = False
) -> list[Text]:
    """The header as a card (one cell *card_width* wide) or as a row of *columns* cells."""
    if card_width:
        return [label(header, card_width, selected)]

    return [
        label(header, selected=selected)
        if i == name_cell
        else Text("", style=Style(underline=True))
        for i in range(columns)
    ]


def background(header: sections.Header) -> Style | None:
    """The fill a column-layout row paints across every cell, for a collapsed group."""
    fill = style(header)
    return Style(bgcolor=fill.bgcolor) if fill.bgcolor else None
