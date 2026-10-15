"""A group's saved color: what `lemonaid group color` and the inbox set.

It outranks `[tui.group_colors]`, which outranks the palette's choice.
"""

__lazy_modules__ = ["textual.color"]

import sqlite3
from collections import abc

from textual.color import Color, ColorParseError

from .. import palette
from . import store


def parsed(text: str) -> str:
    """*text* (`#rrggbb`, `#rgb`, `rgb(...)` or a CSS name) as `#rrggbb`; empty clears.

    Raises GroupError for anything else, such as an ANSI name or a transparent color.
    """
    if not text.strip():
        return ""

    try:
        color = Color.parse(text.strip()).hex.lower()
    except ColorParseError:
        color = ""
    if not palette.is_color(color):
        raise store.GroupError(f"{text.strip()!r} isn't a color; give #rrggbb or a name like teal")

    return color


def save(conn: sqlite3.Connection, group: store.Group, color: str) -> store.Group:
    """Give *group* the `#rrggbb` *color*, or none saved when it's empty."""
    conn.execute("UPDATE lemon_groups SET color = ? WHERE group_id = ?", (color, group.group_id))
    conn.commit()
    return store.find(conn, group.name)


def drawn(groups: abc.Iterable[store.Group], configured: abc.Mapping[str, str]) -> dict[str, str]:
    """The color each group is drawn in: saved, else *configured* by name, else the palette's."""
    listed = list(groups)
    return palette.assign_groups(
        (g.name for g in listed),
        {**configured, **{g.name: g.saved_color for g in listed if g.saved_color}},
    )
