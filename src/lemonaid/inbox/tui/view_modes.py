"""The inbox's alternate views: which table each shows, and how the footer changes for it."""

import dataclasses
from collections import abc

INBOX_ONLY_ACTIONS = ("jump_unread", "mark_read", "mark_unread", "snooze", "toggle_fold")


@dataclasses.dataclass(frozen=True)
class Mode:
    table_id: str
    sub_title: str
    toggle_action: str
    toggle_label: str  # "Exit <label>" while the view is shown
    select_label: str  # Enter's footer label while shown; empty leaves "Switch" alone
    hidden_actions: tuple[str, ...]
    shown_actions: tuple[str, ...] = ()


HISTORY = Mode(
    "#history_table",
    "session history",
    "toggle_history",
    "History",
    "Resume",
    (*INBOX_ONLY_ACTIONS, "archive"),
    ("copy_resume", "filter_history", "tmux_resume"),
)
SNOOZED = Mode("#snoozed_table", "snoozed", "toggle_snoozed", "Snoozed", "Wake", INBOX_ONLY_ACTIONS)
USAGE = Mode("#usage_table", "usage", "toggle_usage", "Usage", "", INBOX_ONLY_ACTIONS)


def footer(mode: Mode, enabled: bool) -> abc.Iterator[tuple[str, bool | None, str | None]]:
    """How each footer binding changes as *mode* opens or closes: (action, show, label)."""
    for action in mode.hidden_actions:
        yield action, not enabled, None
    for action in mode.shown_actions:
        yield action, enabled, None
    yield mode.toggle_action, None, f"Exit {mode.toggle_label}" if enabled else mode.toggle_label
    if mode.select_label:
        yield "select", None, mode.select_label if enabled else "Switch"
