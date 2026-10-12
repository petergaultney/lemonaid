"""What a table row's key names: a notification, a group header, or a lemon under its group."""

from textual.coordinate import Coordinate
from textual.widgets import DataTable
from textual.widgets.data_table import RowKey

from ... import db, sections


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


def notification(key: str | None) -> db.Notification | None:
    """The notification a cursor key names, read fresh."""
    if not key:
        return None

    with db.connect() as conn:
        return db.get(conn, int(key))


def channels(table: DataTable) -> list[str]:
    """The channel of every row on screen, in the order they are drawn; "" for a header.

    Read from the table rather than re-queried, so a reorder acts on the
    list the user is looking at even when the watcher has changed the
    inbox since the last refresh.
    """
    with db.connect() as conn:
        return [
            n.channel
            if (found := key_id(at_row(table, row))) is not None and (n := db.get(conn, found))
            else ""
            for row in range(table.row_count)
        ]


def select_channel(table: DataTable, channel: str) -> None:
    """Put the cursor back on a channel after the list around it moved."""
    for index, c in enumerate(channels(table)):
        if c == channel and index < table.row_count:
            table.move_cursor(row=index)
            return
