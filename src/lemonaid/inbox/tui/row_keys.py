"""What a table row's key names: a notification, a group header, or a lemon under its group."""

from textual.coordinate import Coordinate
from textual.widgets import DataTable
from textual.widgets.data_table import RowKey

from .. import sections


def key_id(key: RowKey | None) -> int | None:
    """The notification a table row's key names, or None for none or a group header."""
    return sections.notification_id(str(key.value)) if key is not None and key.value else None


def at_cursor(table: DataTable) -> str | None:
    """The key of the row at a table's cursor: a notification's, or a group header's."""
    if table.row_count == 0:
        return None
    try:
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        return row_key.value if row_key else None
    except Exception:
        return None


def notification_at_cursor(table: DataTable) -> str | None:
    """The notification ID at a table's cursor, or None on a group header.

    A lemon in two groups is drawn twice, under keys `<id>@<group>`; both
    name the same notification.
    """
    raw = at_cursor(table)
    found = sections.notification_id(raw) if raw else None
    return str(found) if found is not None else None


def at_row(table: DataTable, row: int) -> RowKey:
    return table.coordinate_to_cell_key(Coordinate(row, 0))[0]
