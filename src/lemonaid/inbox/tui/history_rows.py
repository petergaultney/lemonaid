"""The cells of one row in the session-history list."""

from collections import abc

from rich.text import Text

from .. import db
from . import brief_cards, card_context, cards, row_cells, table_rows
from .utils import styled_cell


def history_row(
    n: db.Notification,
    card: brief_cards.CardBrief | None,
    backend: Text,
    where: Text,
    context_parts: abc.Callable[[], list[card_context.Part]],
    neutral_timing: bool,
    card_width: int,
    card_shape: tuple[int, int],
) -> tuple[list[Text], int]:
    """The row's cells (one card cell when `card_width` is set) and its height."""
    name_cell = styled_cell(n.name or "", False, "name", history=True)
    if card and card.status:
        name_cell.append(
            f" · {card.status}",
            style=brief_cards.STATUS_STYLES.get(card.status, "dim"),
        )

    cells = [
        styled_cell(
            row_cells.format_timestamp(n.created_at),
            False,
            "time",
            history=True,
            neutral_timing=neutral_timing,
        ),
        Text(""),  # archived: never a marker, but cards index by position
        backend,
        name_cell,
        styled_cell(n.metadata.get("git_branch", ""), False, "branch", history=True),
        where,
        styled_cell(n.message, False, "message", history=True),
        Text(""),  # No TTY for archived
    ]
    if not card_width:
        shown = table_rows.without_marker(cells)  # columns drop the marker
        return shown, 1

    # Cards have no columns to drop, and index their fields by position.
    shown = cards.as_card(cells, card_width, *card_shape, context_parts=context_parts())
    return shown, table_rows.row_height(shown)
