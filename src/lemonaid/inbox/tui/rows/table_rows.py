"""Bring an inbox DataTable in line with its rows, as columns or cards."""

from collections import abc

from rich.style import Style
from rich.text import Text
from textual.coordinate import Coordinate
from textual.widgets import DataTable

from ..tables import layout
from ..tables.scroll_position import preserve_scroll
from ..tables.table import ClickToActTable
from ..utils import same_cell
from . import brief_cards, brief_rows, card_context, cards, family_highlight, parent_markers


def without_marker(cells: list[Text]) -> list[Text]:
    """Cells minus the unread marker, for a table built without that column."""
    return [cell for index, cell in enumerate(cells) if index != layout.UNREAD_CELL]


def row_height(cells: list[Text]) -> int:
    """A card is as tall as it needs to be - a padded one is mostly blank lines.

    The trailing separator counts: a row allocated shorter than its card clips
    that blank line, which made the gap between cards come and go depending on
    how far the message happened to wrap.
    """
    return len(cells[layout.CARD_BODY_COLUMN].plain.split("\n"))


@preserve_scroll
def sync_rows(
    table: DataTable,
    rows: list[tuple[str, list[Text]]],
    card_width: int = 0,
    shape: tuple[int, int] = (1, 1),
    gutter_width: int = 0,
    unread_style: str = "dot",
    emojis_by_row: abc.Mapping[str, str] | None = None,
    briefs_by_row: abc.Mapping[str, brief_cards.CardBrief | None] | None = None,
    now: float = 0.0,
    contexts_by_row: abc.Mapping[str, abc.Sequence[card_context.Part]] | None = None,
    age_inline: bool = False,
    neutral_timing: bool = False,
    headers: abc.Mapping[str, tuple[list[Text], Style | None]] | None = None,
    rails_by_row: abc.Mapping[str, str] | None = None,
    children_by_row: abc.Mapping[str, tuple[int, int]] | None = None,
    families: family_highlight.Highlighter | None = None,
    leads: abc.Set[str] = frozenset(),
) -> bool:
    """Bring a DataTable in line with `rows`, in place where possible.

    `headers` are group header rows by key, already drawn, with their fill.

    `table.clear()` plus re-adding resets the cursor and scroll offset, which
    reads as the list flashing to the top on every refresh tick. When the row set
    and its order are unchanged — the common case, where only a message or status
    moved — cells are updated in place and the cursor never moves.

    Returns True if the table was rebuilt, meaning the caller has to restore the
    cursor itself. Textual has no public row-reorder API, so a genuine order
    change still costs a rebuild.
    """
    carded = card_width > 0
    headers = headers or {}
    children_by_row = children_by_row or {}
    marker_width = max(
        (2 * len(str(total)) + 3 for _, total in children_by_row.values()), default=0
    )
    if families is not None:
        marker_width += 2
    if leads:
        marker_width += 2
    raw = dict(rows)
    end_rails = {
        key
        for i, (key, _) in enumerate(rows)
        if i + 1 == len(rows) or rows[i + 1][0] not in (rails_by_row or {})
    }

    def render(key: str, family: str) -> list[Text]:
        cells = raw[key]
        visible, total = children_by_row.get(key, (0, 0))
        role = family if families is not None else None
        if carded:
            return cards.as_card(
                cells,
                card_width,
                *shape,
                gutter_width,
                unread_style,
                (emojis_by_row or {}).get(key, ""),
                (briefs_by_row or {}).get(key),
                now,
                (contexts_by_row or {}).get(key),
                age_inline,
                neutral_timing,
                (rails_by_row or {}).get(key, ""),
                key in end_rails,
                total,
                visible,
                role,
                key in leads,
            )

        painted = brief_rows.styled(
            parent_markers.columns(
                cells, total, marker_width, gutter_width, visible, role, key in leads
            ),
            (briefs_by_row or {}).get(key),
            layout.UNREAD_CELL,
            layout.BACKEND_CELL,
            layout.NAME_CELL,
            gutter_width,
        )
        if role:
            painted[layout.NAME_CELL].stylize("bold not dim", gutter_width, gutter_width + 1)
        return painted

    if families is not None:
        families.bind(table, (key for key, _ in rows if key not in headers), render)
    shaped = [
        (key, headers[key][0])
        if key in headers
        else (key, render(key, families.roles.get(key, "") if families is not None else ""))
        for key, _ in rows
    ]

    if isinstance(table, ClickToActTable):
        table.card_row_keys = {key for key, _ in rows if carded and key not in headers}
        table.row_backgrounds = {
            key: fill
            for key, _ in rows
            if not carded
            and (
                fill := headers[key][1]
                if key in headers
                else brief_rows.background((briefs_by_row or {}).get(key))
            )
        }

    if [str(key.value) for key in table.rows] == [key for key, _ in shaped]:
        resized = False
        for key, cells in shaped:
            row_index = table.get_row_index(key)
            for column, value in enumerate(cells):
                if not same_cell(table.get_cell_at(Coordinate(row_index, column)), value):
                    table.update_cell_at((row_index, column), value, update_width=False)
            # A row keeps the height it was added with, so a card whose message
            # shortened would otherwise hold its old size and pad with blanks.
            if carded:
                row = table.rows[table.ordered_rows[row_index].key]
                height = row_height(cells)
                if row.height != height:
                    row.height = height
                    resized = True
        if resized:
            table._update_dimensions(table.rows.keys())
        return False

    table.clear()
    for key, cells in shaped:
        table.add_row(*cells, key=key, height=row_height(cells) if carded else 1)

    return True
