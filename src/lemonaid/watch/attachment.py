"""Whether a waiter's brief is still attached to the lemon it serves."""

from collections import abc
from pathlib import Path

from ..brief import attached
from ..inbox import db


def holds(path: Path, channel: str, harness_alive: abc.Callable[[], bool]) -> bool:
    """An archived inbox row ends the watch unless the lemon's harness is known to run.

    The inbox archives a row when the lemon's process exits, and a resumed lemon's row
    stays archived until its first turn ends.
    """
    with db.connect() as conn:
        session = db.get_by_channel(conn, channel, unread_only=False)
        return attached.by_channel(conn, [channel]).get(channel) == path and (
            session is None or not session.is_archived or harness_alive()
        )
