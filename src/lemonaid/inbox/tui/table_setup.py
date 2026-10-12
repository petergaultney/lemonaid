"""The inbox tables' columns: which ones each table has, and how wide they are drawn."""

from collections import abc

from textual.widgets import DataTable

from ...config import TuiConfig
from . import layout, table_columns, table_layout

TABLE_IDS = ("#main_table", "#other_sources_table", "#history_table", "#snoozed_table")


def setup(
    table: DataTable,
    cards: bool,
    tui: TuiConfig,
    wake_column: bool = False,
    marker_column: bool = True,
) -> None:
    """Give *table* the columns of a card or column layout, replacing any it has."""
    table.cursor_type = "row"
    # Idempotent: a resize across the card threshold re-runs this on a table
    # that already has the other layout's columns.
    if table.columns:
        table.clear(columns=True)

    if cards:
        table.cell_padding = layout.CARD_CELL_PADDING
        table.show_header = False  # The card column has no label
        table.add_column("", width=20)  # The card body, stretched on resize
        return

    table.cell_padding = layout.COLUMN_CELL_PADDING
    if table.id != "other_sources_table":
        table.show_header = True
    # Time holds "HH:MM:SS", "y HH:MM" for yesterday, or "YYYY-MM-DD".
    table.add_column("Time", width=10)
    # Everything in history is archived, so the marker would always be
    # empty. Dropping it shifts every row left, which is a structural cue
    # that this is a different list rather than a differently-tinted one.
    if marker_column:
        table.add_column("", width=1)  # Unread indicator
    table.add_column(  # Model, right-aligned
        "",
        width=layout.BACKEND_WIDTH + (layout.CONTEXT_WIDTH if tui.context_threshold else 0),
    )
    table.add_column("Name", width=24)
    table.add_column("Branch", width=12)
    table.add_column(table_layout.where_label(f"#{table.id}", tui.card_fields), width=16)
    table.add_column("Message", width=30)  # Stretched on resize
    # TTY holds "ttysNNN"; the snoozed view's wake label is "Fri 09:00".
    table.add_column("Wakes" if wake_column else "TTY", width=9 if wake_column else 7)


def stretch(
    tables: abc.Mapping[str, DataTable], cards: bool, width: int, card_fields: abc.Collection[str]
) -> None:
    """Fit each table, by id, to a pane *width* wide."""
    if width <= 0:
        return

    if cards:
        for table in tables.values():
            table_columns.fill_card_columns(
                table, width - table_columns.vertical_scrollbar_width(table)
            )
        return

    hidden, flex = table_layout.column_plan(width)
    for table_id, table in tables.items():
        # The snoozed view's last column is a wake time, not a TTY, and is
        # the whole point of that view — never hide it.
        table_hidden = hidden - {layout.TTY_COLUMN} if table_id == "#snoozed_table" else hidden
        table_columns.hide_columns(
            table, table_hidden, table_layout.column_labels(table_id, card_fields)
        )
        # Which columns to show keys off the terminal width, so the layout doesn't
        # reshuffle when a scrollbar appears; how wide to draw them keys off what
        # the table can actually paint into.
        table_columns.stretch_columns(
            table, flex, width - table_columns.vertical_scrollbar_width(table)
        )
