"""Fold a column row into a card cell."""

from collections import abc

from rich.console import Console
from rich.style import Style
from rich.text import Text

from .. import utils
from ..tables import layout
from ..utils import ATTENTION_COLOR, HERE_BAR, HERE_BLOCK, PIN_MARK
from . import brief_cards, card_context, card_frame, context_reading, parent_markers

_CONSOLE = Console()  # for measuring wraps only; nothing is printed through it


def _overlay(target: Text, piece: Text, offset: int) -> None:
    """Apply `piece`'s styles to the same text in `target`, starting at `offset`."""
    for span in piece.spans:
        target.stylize(span.style, offset + span.start, offset + span.end)


def _truncated(line: Text, width: int) -> Text:
    line.truncate(width, overflow="ellipsis")
    return line


def _right_aligned(left: Text, right: Text, width: int) -> Text:
    """Fit a right-hand label beside a line without reserving later lines."""
    left = left.copy()
    right = right.copy()
    _truncated(right, width)
    if not right.plain:
        return _truncated(left, width)

    left_width = max(0, width - right.cell_len - 1)
    _truncated(left, left_width)
    gap = max(0, width - left.cell_len - right.cell_len)
    return left + Text(" " * gap) + right


def _wrapped(line: Text, width: int, budget: int) -> list[Text]:
    """`line` over at most `budget` lines, or fewer when it doesn't need them."""
    # rich pads a wrap to the full width, which yields a blank last line when the
    # text ends near a boundary - and a blank there reads as a second separator.
    wrapped = [line for line in list(line.wrap(_CONSOLE, width))[:budget] if line.plain.strip()]
    if wrapped:
        # Whatever didn't fit in the budget is gone; say so on the last line.
        _truncated(wrapped[-1], width)

    return wrapped


def as_card(
    cells: list[Text],
    width: int,
    context_lines: int = 1,
    message_lines: int = 1,
    gutter_width: int = 0,
    unread_style: str = "dot",
    emoji: str = "",
    card_brief: brief_cards.CardBrief | None = None,
    now: float = 0.0,
    context_parts: abc.Sequence[card_context.Part] | None = None,
    age_inline: bool = False,
    neutral_timing: bool = False,
    rail: str = "",
    end_rail: bool = False,
    children: int = 0,
    visible_children: int | None = None,
    family: str | None = None,
) -> list[Text]:
    """Fold a column row into the cells of a card.

    Line 1 is the name, line 2 the short identifiers that place it, then the
    message. Every field the column layout carries survives except the TTY, which
    the two narrower column layouts already drop.

    The name and the context line are truncated, never wrapped: they are fields
    you scan for, so each has to sit in one predictable place down the list. Only
    the message wraps, because it is the one field that reads as prose.

    `gutter_width` is how much of the name cell the column layout's gutter takes,
    for a card to strip before laying out its own. `context_parts` is the second
    line, the time, cwd and branch cells when not given.
    """
    # Cells arrive already coloured by field and dimmed by read state, so a card
    # rearranges them rather than restyling: both layouts then agree on what a
    # colour means, and fixing one fixes the other.
    #
    # The dot rides on the name rather than owning a column: it is empty for most
    # rows, and a permanently-indented card wastes width a narrow pane hasn't got.
    # Styled only when there is a dot to style. The marker style is bold, and a
    # bold empty placeholder still emits the attribute - which the name that
    # follows then inherits, since a colour change does not clear it.
    marker = cells[layout.UNREAD_CELL]
    dot = Text("●", style=utils.unread_marker_style()) if marker.plain else Text(" ")

    # The first cell is one stable navigation slot: a jump digit, or blank for
    # the current session, which has no reason to be jumped to. Read titles
    # start in the fourth cell; an unread dot, with breathing room on both
    # sides, nudges the title one cell right as part of the attention signal.
    name = cells[layout.NAME_CELL]
    is_here = name.plain.startswith(HERE_BLOCK)
    selector = Text(layout.INDENT)
    if gutter_width:
        selector = Text(layout.INDENT) if is_here else name[: len(layout.INDENT)]
        name = name[gutter_width:]
    if emoji and name.plain.startswith(f"{emoji} "):
        name = name[len(emoji) + 1 :]

    edge = Text(layout.INDENT)

    # Every card reserves the right edge; the frame's left and bottom edges
    # occupy the existing gutter and separator without moving content.
    width -= len(HERE_BAR)

    # A card in an open group gives up its first column to an unbroken rail in
    # the group's colour, so the run of colour shows where the group starts and
    # ends. Ungrouped cards keep the full width.
    if rail:
        width -= 1
    bar_unread = unread_style == "bar" and bool(marker.plain) and card_brief is None
    if bar_unread:
        headline = selector + Text("  ") + name
    else:
        headline = (
            selector + Text(" ") + dot + Text(" ") + name
            if marker.plain
            else selector + Text("  ") + name
        )

    message = cells[layout.MSG_CELL]
    dimmed = bool(card_brief and card_brief.shown == "idle" and not marker.plain)
    if dimmed:
        headline.stylize("dim")
        message = message.copy()
        message.stylize("dim")

    # The bar is a column of the card's width, not an extra one beside it, so
    # every line's budget shrinks by it. Without that the context line overflows
    # the pane and wraps - and a wrapped line starts at column 0, breaking the
    # edge the bar is there to draw.
    body = width - len(layout.INDENT)
    backend = cells[layout.BACKEND_CELL].copy()
    pin = Text("")
    if backend.plain.endswith(PIN_MARK):
        pin = backend[-len(PIN_MARK) :]
        backend = backend[: -len(PIN_MARK)]
    reading, backend = context_reading.split(backend)
    reading.justify = None
    backend.justify = None
    pin.justify = None
    if card_brief and card_brief.shown == "idle" and not marker.plain:
        backend.stylize("dim")
        reading.stylize("dim")
    markers = parent_markers.indicators(children, emoji, pin, visible_children, family)
    context = card_context.fitted(
        context_parts
        if context_parts is not None
        else [
            card_context.Part("time", cells[layout.TIME_CELL], cells[layout.TIME_CELL].cell_len),
            card_context.Part("cwd", cells[layout.CWD_CELL]),
            card_context.Part("branch", cells[layout.BRANCH_CELL]),
        ],
        body - (markers.cell_len + 1 if markers.plain else 0),
    )
    if dimmed:
        context.stylize("dim")

    if bar_unread:
        backend_style = backend.get_style_at_offset(_CONSOLE, 0)
        badge = Text(f" {backend.plain} ")
        badge.stylize(
            Style(
                color="#000000",
                bgcolor=backend_style.color or ATTENTION_COLOR,
            )
        )
        filled = context_reading.filled(reading)
        headline = _right_aligned(headline, filled + badge, width)
        # Keep the selected-session bar green; everything after it is the
        # yellow title bar until the provider-coloured model badge begins.
        headline.stylize(
            Style(color="#000000", bgcolor=ATTENTION_COLOR),
            0,
            len(headline) - len(badge),
        )
        _overlay(headline, filled, len(headline) - len(badge) - len(filled))
        name_offset = len(selector) + 2
        for span in name.spans:
            if isinstance(span.style, Style) and span.style.meta.get("lemonaid_wordybin"):
                headline.stylize(
                    Style(color="bright_black", bgcolor=ATTENTION_COLOR),
                    name_offset + span.start,
                    name_offset + span.end,
                )
    else:
        if card_brief and card_brief.shown in brief_cards.STATUS_STYLES:
            backend = context_reading.padded_model(
                reading, backend, backend.get_style_at_offset(_CONSOLE, 0)
            )
            reading = context_reading.filled(reading)
        headline = _right_aligned(headline, reading + backend, width)

    if card_brief and card_brief.shown in brief_cards.STATUS_STYLES:
        headline.stylize(brief_cards.STATUS_STYLES[card_brief.shown])
        if backend.plain:
            # The model keeps its provider colour, as a badge, like the column row's.
            provider = backend.get_style_at_offset(_CONSOLE, 0).color
            headline.stylize(
                Style(color="#000000", bgcolor=provider or ATTENTION_COLOR),
                len(headline) - len(backend),
            )
        _overlay(headline, reading, len(headline) - len(backend) - len(reading))
        if marker.plain:
            headline.stylize(
                brief_cards.DOT_STYLES.get(card_brief.shown, utils.unread_marker_style()),
                2,
                3,
            )

    # What the lemon needs from you sits right under who it is, in the attention
    # colour whatever the state: a waiting card dims everything else, not this.
    brief_lines = (
        [
            *(
                [Text(card_brief.needs_line, style=utils.unread_marker_style())]
                if card_brief.needs_line
                else []
            ),
            *(
                []
                if age_inline
                else [card_brief.age_text(now, style="bright_black" if neutral_timing else "dim")]
            ),
            *(
                [Text(card_brief.running_line, style=brief_cards.running_text())]
                if card_brief.running_line
                else []
            ),
            *([Text(card_brief.waiting_line, style="dim")] if card_brief.waiting_line else []),
            *(
                [Text(card_brief.stuck_line, style=utils.unread_marker_style())]
                if card_brief.stuck_line
                else []
            ),
        ]
        if card_brief
        else []
    )

    lines = [
        headline,
        _right_aligned(edge + context, markers, width),
        *(edge + _truncated(line, body) for line in brief_lines),
        # The message is the only field with the vertical space spent on it: it
        # is unbounded, and the one an ellipsis costs you most.
        *(edge + line for line in _wrapped(message, body, message_lines)),
        # The separator belongs to this card, including at the end of a group.
        Text(""),
    ]
    lines = card_frame.finished(
        lines, width, utils.here_bar_style() if is_here else "", rail, end_rail
    )
    # Model and pin live in the first two lines rather than a second table
    # column. That gives the message every column below them instead of making
    # a short label reserve a blank strip down the entire card.
    return [Text("\n").join(lines)]
