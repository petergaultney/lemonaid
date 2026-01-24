"""Lemonaid Inbox - attention management for notifications from lemons and other tools."""

from .db import (
    Notification,
    add,
    add_notification,
    clear_old,
    connect,
    get,
    get_by_channel,
    get_db_path,
    get_unread,
    mark_all_read_for_channel,
    mark_read,
    update_name,
)
from .tui import LemonaidApp

__all__ = [
    # Types
    "Notification",
    # New functional API
    "connect",
    "get",
    "get_by_channel",
    "get_unread",
    "add",
    "mark_read",
    "mark_all_read_for_channel",
    "update_name",
    "clear_old",
    "get_db_path",
    # Legacy
    "add_notification",
    # TUI
    "LemonaidApp",
]
