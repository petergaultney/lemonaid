"""Where the inbox cursor goes when its table has been rebuilt."""

import contextlib
from collections import abc

from textual.widgets import DataTable

from .. import sections


def after_unread_action(unread_rows: abc.Sequence[int], current_index: int) -> int:
    """The next unread row at or below the cursor, else the last one above, else the top.

    Pins and blocked rows mean unread rows need not be contiguous.
    """
    if not unread_rows:
        return 0

    return next((i for i in unread_rows if i >= current_index), unread_rows[-1])


def after_rebuild(
    table: DataTable, current_row: str | None, current_key: str | None, current_index: int
) -> int:
    """The same row, else the same lemon wherever it went, else the same place."""
    for key in (current_row, current_key):
        if key:
            with contextlib.suppress(Exception):
                return table.get_row_index(key)

    if current_key:
        # Into or out of a group, or between groups, its key changed.
        moved = next(
            (
                i
                for i, key in enumerate(table.rows)
                if str(sections.notification_id(str(key.value))) == current_key
            ),
            None,
        )
        if moved is not None:
            return moved

    return min(current_index, table.row_count - 1)


def kept(table: DataTable, key: str | None, index: int) -> int:
    """The row *key* is on now, else the same place, kept in range."""
    if key:
        with contextlib.suppress(Exception):
            return table.get_row_index(key)

    return min(index, table.row_count - 1)
