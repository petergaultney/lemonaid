"""How wide a pane draws the inbox: cards or columns, and which columns."""

from collections import abc

from . import layout


def wants_cards(width: int, height: int, scratch_left: bool | None = None) -> bool:
    """Whether to draw cards rather than columns.

    The scratch pane is a sidebar or a strip by declaration - its position -
    never by measurement. It takes its height from whichever window it is in
    and can be any width for a moment while tmux rearranges a layout, and a
    layout that follows those is a sidebar rendering as a top pane.

    A plain `lma` in a terminal decides from its shape: a pane narrow enough
    to be a sidebar gets cards whatever its height. `scratch_left` is whether the
    scratch pane sits on the left, None outside scratch mode.
    """
    if scratch_left is not None:
        return scratch_left

    if width <= 0:
        return False

    if width < layout.SIDEBAR_COLS:
        return True

    return height >= width * layout.CARD_ASPECT


def card_shape(
    pane_height: int, notes_height: int, sessions: int, extra_lines: int = 0
) -> tuple[int, int]:
    """How many lines the context and message get inside one card.

    A card grows only while the sessions on screen still fit: vertical space
    is what a tall pane has spare, but not at the cost of scrolling a list
    that used to fit. Everything past what the pane can hold stays at the
    minimum, since a taller card can't help a list that already overflows.
    """
    rows = pane_height - layout.CARD_CHROME_ROWS - notes_height
    sessions = max(1, sessions)
    # layout.CARD_HEIGHT includes the first message line, but not the blank separator.
    # Account for it on brief cards without changing the existing card sizing.
    card_height = layout.CARD_HEIGHT + extra_lines + int(extra_lines > 0)
    spare = rows // sessions - card_height
    if spare <= 0:
        return 1, 1

    # A card only ever renders the lines its message actually fills, so this
    # is a ceiling rather than padding - a short message stays short. The
    # share cap keeps one long message from owning a mostly-empty pane.
    ceiling = min(
        layout.CARD_MAX_HEIGHT, max(layout.CARD_HEIGHT, int(rows * layout.CARD_MAX_SHARE))
    )

    # All of it goes to the message: context is one truncated line by
    # design, so lines handed to it would be discarded.
    return 1, 1 + min(spare, max(0, ceiling - card_height))


def card_width(column_widths: abc.Sequence[int]) -> int:
    """Width the card's body column was stretched to."""
    if len(column_widths) <= layout.CARD_BODY_COLUMN:
        return layout.CARD_MIN_TEXT

    return max(layout.CARD_MIN_TEXT, column_widths[layout.CARD_BODY_COLUMN])


def column_plan(width: int) -> tuple[set[int], list[tuple[int, int, float, int]]]:
    """The columns hidden at this terminal width, and the flex specs of the rest."""
    # Name carries Claude's conversation title, which is what actually
    # distinguishes one session from another, so it gets the largest share of
    # flex space. Narrower terminals can't fit every column, and starving
    # Name to keep the others is the wrong trade: TTY is diagnostic, Branch is
    # usually inferable from CWD, and Message is mostly "Waiting in <path>",
    # which CWD already says. They come back as the terminal widens.
    if width >= layout.WIDE_LAYOUT_COLS:
        return set(), [(3, 40, 0.46, 48), (4, 10, 0.11, 32), (5, 12, 0.13, 30), (6, 16, 0.30, 0)]

    if width >= layout.MEDIUM_LAYOUT_COLS:
        return {layout.TTY_COLUMN}, [
            (3, 36, 0.48, 44),
            (4, 9, 0.10, 28),
            (5, 11, 0.12, 28),
            (6, 14, 0.30, 0),
        ]

    return {layout.TTY_COLUMN, layout.BRANCH_COLUMN, layout.MESSAGE_COLUMN}, [
        (3, 30, 0.72, 0),
        (5, 10, 0.28, 0),
    ]


def where_label(table_id: str, card_fields: abc.Collection[str]) -> str:
    """History and the snoozed list keep the cwd: they are records, searched by path."""
    inbox = table_id in {"#main_table", "#other_sources_table"}
    return "Project" if inbox and "project" in card_fields else "CWD"


def column_labels(table_id: str, card_fields: abc.Collection[str]) -> dict[int, str]:
    return {
        0: "Time",
        3: "Name",
        layout.BRANCH_COLUMN: "Branch",
        5: where_label(table_id, card_fields),
        6: "Message",
        layout.TTY_COLUMN: "Wakes" if table_id == "#snoozed_table" else "TTY",
    }


def archive_fits(
    available_height: int,
    inbox_height: int,
    archive_header_height: int,
    first_archive_row_height: int,
) -> bool:
    """Room under a search's inbox matches for the archive's label, header and first row."""
    return available_height - inbox_height >= 1 + archive_header_height + first_archive_row_height
