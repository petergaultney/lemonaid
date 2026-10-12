"""Moving the cursor across the inbox's stacked tables as though they were one list.

The other-terminals table sits under the main one, and while searching the
archive's matches sit under both.
"""

from textual.widgets import DataTable


def _to_last(table: DataTable) -> None:
    table.focus()
    if table.row_count > 0:
        table.move_cursor(row=table.row_count - 1)


def _shown(table: DataTable) -> bool:
    return bool(table.display and table.row_count)


def up(table: DataTable, main: DataTable, other: DataTable, searching: bool) -> None:
    """From the top of a lower table, up to the bottom of the one above it."""
    if table.id == "history_table" and searching and table.cursor_coordinate.row == 0:
        _to_last(other if _shown(other) else main)
    elif table is other and table.cursor_coordinate.row == 0:
        _to_last(main)
    else:
        table.action_cursor_up()


def down(
    table: DataTable, main: DataTable, other: DataTable, archive: DataTable, searching: bool
) -> None:
    """From the bottom of a table, down to the top of the one below it."""
    at_bottom = table.cursor_coordinate.row >= table.row_count - 1
    below = (
        other
        if table is main and at_bottom and _shown(other)
        else archive
        if searching and table in (main, other) and at_bottom and _shown(archive)
        else None
    )
    if below is None:
        table.action_cursor_down()
        return

    below.focus()
    below.move_cursor(row=0)


def to_end(table: DataTable, main: DataTable, last: bool) -> None:
    """To the first or last row of the focused table; from the other-terminals
    table, which nothing can be switched to, to the main table's.
    """
    if table.id == "other_sources_table":
        table = main
        table.focus()
    if table.row_count > 0:
        table.move_cursor(row=table.row_count - 1 if last else 0)


def into_results(main: DataTable, other: DataTable, archive: DataTable, searching: bool) -> None:
    """From the search box down to the first table with matches in it."""
    if not searching:
        archive.focus()
    elif main.row_count:
        main.focus()
    elif _shown(other):
        other.focus()
    elif _shown(archive):
        archive.focus()
    else:
        main.focus()
