"""Pinned sessions: a channel held at a chosen place in the inbox.

Position values are sparse on purpose. A pinned session that is snoozed or
otherwise absent keeps its number while it is away, so the gaps in a rendered
list are where the absent pins will return. Nothing compacts them.

Moving a pin swaps two positions and leaves every other row alone, so a pin you
cannot see is never renumbered by a move you made without it on screen.
"""

import sqlite3

_SPACING = 10.0


def pinned_positions(conn: sqlite3.Connection) -> dict[str, float]:
    """Every pinned channel and its position."""
    return {row["channel"]: row["position"] for row in conn.execute("SELECT * FROM pins")}


def is_pinned(conn: sqlite3.Connection, channel: str) -> bool:
    return conn.execute("SELECT 1 FROM pins WHERE channel = ?", (channel,)).fetchone() is not None


def pin(conn: sqlite3.Connection, channel: str) -> None:
    """Pin a channel below every existing pin. Pinning twice does nothing."""
    if is_pinned(conn, channel):
        return

    conn.execute(
        "INSERT INTO pins (channel, position) VALUES (?, ?)",
        (channel, (conn.execute("SELECT MAX(position) FROM pins").fetchone()[0] or 0) + _SPACING),
    )
    conn.commit()


def unpin(conn: sqlite3.Connection, channel: str) -> None:
    conn.execute("DELETE FROM pins WHERE channel = ?", (channel,))
    conn.commit()


def toggle(conn: sqlite3.Connection, channel: str) -> bool:
    """Pin an unpinned channel or unpin a pinned one. Returns the new state."""
    if is_pinned(conn, channel):
        unpin(conn, channel)
        return False

    pin(conn, channel)
    return True


def swap(conn: sqlite3.Connection, channel: str, other: str) -> None:
    """Exchange the positions of two pinned channels.

    The caller picks `other` from what is on screen, so a move only ever
    reorders rows the user can see. Both must already be pinned.
    """
    positions = pinned_positions(conn)
    if channel not in positions or other not in positions:
        return

    conn.executemany(
        "UPDATE pins SET position = ? WHERE channel = ?",
        [(positions[other], channel), (positions[channel], other)],
    )
    conn.commit()
