"""Where the inbox cursor goes when its table has been rebuilt."""

from collections import abc


def after_unread_action(unread_rows: abc.Sequence[int], current_index: int) -> int:
    """The next unread row at or below the cursor, else the last one above, else the top.

    Pins and blocked rows mean unread rows need not be contiguous.
    """
    if not unread_rows:
        return 0

    return next((i for i in unread_rows if i >= current_index), unread_rows[-1])
