"""Rows another tool keeps in the inbox for a lemon, rather than sessions of their own.

`lemonaid inbox add <channel> <message> --metadata '{"under": "<lemon channel>"}'` makes one:
the row is drawn right under that lemon, in its groups, wherever the lemon is drawn, and an
unread one brings a folded or hidden lemon back. A row whose lemon has no terminal, or that
names none (`"under": ""`), is drawn on its own. With `"hide_when_read": true` the row leaves
the inbox once read. Its activation is the row's own: `open_uri`, or an `opener` (see
handlers.py).
"""

import typing as ty

from . import db

UNDER: ty.Final = "under"
HIDE_WHEN_READ: ty.Final = "hide_when_read"


def is_item(n: db.Notification) -> bool:
    return isinstance((n.metadata or {}).get(UNDER), str)


def lemon_of(n: db.Notification) -> str:
    """The channel of the lemon *n* is kept under, or ""."""
    lemon = (n.metadata or {}).get(UNDER)
    return lemon if isinstance(lemon, str) else ""


def hidden_when_read(n: db.Notification) -> bool:
    return is_item(n) and (n.metadata or {}).get(HIDE_WHEN_READ) is True and not n.is_unread
