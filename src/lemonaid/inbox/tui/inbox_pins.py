"""Pinning sessions at their places in the inbox list, and trading pinned places."""

from collections import abc

from ...log import get_logger
from .. import db, pins
from .inbox_list import InboxList

_log = get_logger("tui")


def toggle_pin(inbox: InboxList, channel: str) -> None:
    """Hold the session at its place in the list, or release it."""
    with db.connect() as conn:
        now_pinned = pins.toggle(conn, channel)

    _log.info("pin: %s -> %s", channel, now_pinned)
    inbox.redraw()
    inbox.notify(f"{'Pinned' if now_pinned else 'Unpinned'} {channel}")


def move_pin(inbox: InboxList, channel: str, row_channels: abc.Sequence[str], offset: int) -> bool:
    """Trade places with the nearest pinned session `offset` away on screen.

    The neighbour is taken from the rendered list rather than from the pins
    table, so a pinned session that is currently snoozed keeps its position
    and returns between the same two rows it sat between before.
    """
    with db.connect() as conn:
        if not pins.is_pinned(conn, channel):
            return False

        pinned_now = pins.pinned_positions(conn)
        on_screen = [c for c in row_channels if c in pinned_now]
        if channel not in on_screen:
            return False

        neighbour = on_screen.index(channel) + offset
        if not 0 <= neighbour < len(on_screen):
            return False

        pins.swap(conn, channel, on_screen[neighbour])

    inbox.redraw()
    return True
