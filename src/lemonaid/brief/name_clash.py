"""Warn a lemon coming back whose name a newer lemon took while it was idle.

The lemon keeps its name; it hears about the clash in its inbox, once, and whoever
brought it back sees the same line. A warning never stops the launch it accompanies.
"""

import sqlite3

from .. import messages
from ..log import get_logger
from . import active_names

_log = get_logger("brief.name_clash")


def _queued(lemon_id: str, text: str) -> bool:
    return any(
        text in path.read_text(encoding="utf-8")
        for path in messages.store.inbox_for_id(lemon_id).glob("*.md")
    )


def warn(conn: sqlite3.Connection, lemon_id: str) -> str:
    """The warning for *lemon_id*, queued in its inbox unless already there; "" when its name is its own.

    A failure to look the name up or queue the warning is logged, never raised.
    """
    try:
        text = active_names.warning(lemon_id, active_names.sharing(conn, lemon_id))
    except (OSError, sqlite3.Error) as error:
        _log.warning("Could not check %s for a shared name: %s", lemon_id, error)
        return ""

    if not text:
        return ""

    try:
        if not _queued(lemon_id, text):
            messages.store.send(messages.store.inbox_for_id(lemon_id), text, "lemonaid")
    except (OSError, ValueError) as error:
        _log.warning("Could not queue the shared-name warning for %s: %s", lemon_id, error)
    return text
