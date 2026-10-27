"""Group-colored inbox bars with a symbol badge for each represented brief status.

The badges sit at the bar's right end. Where there is room, each status has its own
slot there, in the same place on every bar, so a status can be scanned down the list;
otherwise the badges present pack against the right end, and failing that follow the tally.
"""

import itertools
import sys
from collections import abc

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
_SLOT = 4  # a one-digit badge: its glyph and number, one cell of its color either side
_END = 3  # a card's ` ◀ `, kept clear on every card so a selected one's badges don't move
_NAME_ROOM = 20  # what a bar keeps for the group's name before giving badges their slots


def has_badge(status: str) -> bool:
    return status in _STATUS_GLYPHS


def badge(status: str, count: int) -> Text:
    """*count* lemons of *status* as its glyph and number, filled with the status's color."""
    return Text(
        f" {_STATUS_GLYPHS[status]}{count} ",
        STATUS_STYLES[status] + Style(bold=True, underline=False),
    )


def _clickable(status: str, count: int) -> Text:
    """A header's badge, which a click reports by its status: see `ClickToActTable.BadgeClicked`."""
    text = badge(status, count)
    text.stylize(Style.from_meta({"badge": status}))
    return text


def slot_width(headers: abc.Iterable[sections.Header]) -> int:
    """The slot every header gives a status: wide enough for the widest badge among *headers*."""
    return max(
        (badge(s, n).cell_len for header in headers for s, n in header.status_counts),
        default=_SLOT,
    )


def style(header: sections.Header) -> Style:
    color = Color.parse(header.group.color)
    luminance = sum(
        weight * (channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
        for channel, weight in zip(color.normalized, (0.2126, 0.7152, 0.0722), strict=True)
    )
    foreground = "#000000" if (luminance + 0.05) / 0.05 >= 1.05 / (luminance + 0.05) else "#ffffff"
    return Style(color=foreground, bgcolor=color.hex, bold=True, underline=True)


def _fill(bins: abc.Sequence[int], marks: abc.Sequence[Text]) -> list[list[Text]] | None:
    """*marks* packed into *bins* of those widths from the right, none split across two;
    None when they don't fit.
    """
    placed: list[list[Text]] = [[] for _ in bins]
    room = list(bins)
    at = len(bins) - 1
    for mark in reversed(marks):
        while at >= 0 and room[at] < mark.cell_len:
            at -= 1
        if at < 0:
            return None

        placed[at].insert(0, mark)
        room[at] -= mark.cell_len
    return placed


def _placed(header: sections.Header, bins: abc.Sequence[int], slot: int) -> list[list[Text]]:
    """The badges in *bins*, the first being the room beside the name: in *slot*-wide slots
    when every slot fits, which depends only on the widths, else packed against the right end
    and spilling into the first bin, where the name gives way to them.
    """
    counts = dict(header.status_counts)
    fill = style(header)
    gap = Text(" " * slot, style=fill + Style(underline=False))
    placed = (
        _fill(
            bins,
            [
                _right_justified([_clickable(s, counts[s])], slot, fill) if s in counts else gap
                for s in _STATUS_GLYPHS
            ],
        )
        if _fill(bins, [gap] * len(_STATUS_GLYPHS)) is not None
        else None
    )
    if placed is None:
        placed = _fill(
            [sys.maxsize, *bins[1:]], [_clickable(s, n) for s, n in header.status_counts]
        ) or [[] for _ in bins]
    return [list(itertools.dropwhile(lambda mark: mark is gap, marks)) for marks in placed]


def _right_justified(marks: abc.Sequence[Text], width: int, fill: Style) -> Text:
    text = Text.assemble(*marks)
    return Text(" " * max(0, width - text.cell_len), style=fill + Style(underline=False)) + text


def _bar(
    header: sections.Header,
    width: int,
    selected: bool,
    digit: str,
    end_marker: bool,
    marks: abc.Sequence[Text],
) -> Text:
    """The name and tally, then *marks* against the right end, *width* cells in all."""
    called = f"{digit} {header.group.name}" if digit else header.group.name
    arrow = "▸" if header.group.collapsed else "▾"
    name = Text(f"{arrow} {called}")
    tally = Text(f" ({header.tally})")
    fill = style(header)
    marker = Style(color=fill.bgcolor, bgcolor=fill.color, bold=True, underline=False)
    end = (
        (Text(" ◀ ", style=marker) if selected else Text(" " * _END, style=fill))
        if end_marker
        else Text("")
    )
    right = Text.assemble(*marks)
    gap = 1 if marks else 0
    if width:
        name.truncate(
            max(0, width - end.cell_len - right.cell_len - gap - tally.cell_len),
            overflow="ellipsis",
        )
    text = Text.assemble(name, tally, style=fill)
    if selected and text.cell_len:
        text.stylize(marker, 0, 1)
    if not width:
        return text

    text.append_text(_right_justified(marks, width - end.cell_len - text.cell_len, fill))
    text.truncate(max(0, width - end.cell_len))
    end.truncate(width)
    text.append_text(end)
    return text


def label(
    header: sections.Header,
    width: int = 0,
    selected: bool = False,
    digit: str = "",
    *,
    end_marker: bool = True,
    slot: int = _SLOT,
) -> Text:
    """A card's header: the tally and status badges stay visible before a long name does."""
    end = _END if end_marker else 0
    if not width:
        return _bar(header, 0, selected, digit, end_marker, []) + Text.assemble(
            Text(" " if header.status_counts else "", style=Style(underline=False)),
            *(_clickable(s, n) for s, n in header.status_counts),
        )

    (marks,) = _placed(header, [max(0, width - end - _NAME_ROOM)], slot)
    return _bar(header, width, selected, digit, end_marker, marks)


def cells(
    header: sections.Header,
    card_width: int,
    widths: abc.Sequence[int],
    name_cell: int,
    selected: bool = False,
    digit: str = "",
    slot: int = _SLOT,
) -> list[Text]:
    """The header as a card or as a row of cells of *widths*, its badges at the bar's right end.

    *slot* is `slot_width` of every header drawn with it, so their slots line up.
    """
    if card_width:
        return [label(header, card_width, selected, digit, slot=slot)]

    after = list(widths[name_cell + 1 :])
    beside, *right = _placed(header, [max(0, widths[name_cell] - _NAME_ROOM), *after], slot)
    fill = style(header)
    return [
        *(Text("", style=fill) for _ in widths[:name_cell]),
        _bar(header, widths[name_cell], selected, digit, False, beside),
        *(_right_justified(marks, width, fill) for marks, width in zip(right, after, strict=True)),
    ]


def slot_starts(
    card_width: int, widths: abc.Sequence[int], name_cell: int, padding: int, slot: int = _SLOT
) -> dict[str, int]:
    """Where each status's slot starts, in cells from the table's left, on bars drawn by `cells`
    with these arguments and cell *padding*; empty when the bars pack their badges instead.
    """
    if card_width:
        rights = [card_width - _END]
        rooms = [card_width - _END - _NAME_ROOM]
    else:
        lefts = list(itertools.accumulate((w + 2 * padding for w in widths), initial=padding))
        rights = [lefts[i] + widths[i] for i in range(name_cell, len(widths))]
        rooms = [widths[name_cell] - _NAME_ROOM, *widths[name_cell + 1 :]]
    gap = Text(" " * slot)
    placed = _fill([max(0, room) for room in rooms], [gap] * len(_STATUS_GLYPHS))
    if placed is None:
        return {}

    starts = [
        right - slot * (len(marks) - j)
        for right, marks in zip(rights, placed, strict=True)
        for j in range(len(marks))
    ]
    return dict(zip(_STATUS_GLYPHS, starts, strict=True))


def background(header: sections.Header) -> Style:
    return Style(bgcolor=header.group.color)
