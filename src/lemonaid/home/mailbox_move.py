"""Moving a home's `inbox/` message folder to `mailbox/`, its name since 0.142.

The old path is left as a link to the new one, so an older lemonaid still
running (a waiter, the delivery service) reads, writes and locks the same files.
"""

from pathlib import Path

from ..log import get_logger
from .layout import MAILBOX, OLD_MAILBOX

_log = get_logger("home.mailbox_move")


def move(parent: Path) -> None:
    """Move *parent*'s `inbox/` to `mailbox/` and link it back; safe to repeat and to race.

    A link missing after an interrupted move is made again. `split` says whether
    what a race or a failed move leaves is usable.
    """
    old, new = parent / OLD_MAILBOX, parent / MAILBOX
    if old.is_dir() and not old.is_symlink() and not new.exists():
        try:
            old.rename(new)
        except (FileNotFoundError, IsADirectoryError) as error:  # another process moved it first
            _log.info("%s was already moved: %s", old, error)

    if new.is_dir() and not old.is_symlink() and not old.exists():
        try:
            old.symlink_to(MAILBOX)
        except FileExistsError as error:  # another process linked it, or an older one made it
            _log.info("did not link %s: %s", old, error)


def split(parent: Path) -> str:
    """Why message commands must wait for *parent*'s `inbox/` to be sorted out by hand, or ""."""
    old, new = parent / OLD_MAILBOX, parent / MAILBOX
    if old.is_symlink() or not old.is_dir():
        return ""

    if not new.is_dir():
        return f"{old} could not be moved to {new}; message commands wait until it is"

    return (
        f"{old} and {new} both exist; message commands wait until the messages in "
        f"{old} are moved into {new} and {old} is replaced by a link to it"
    )
