"""The inbox's alternate views: which table each shows, and how the footer changes for it."""

import dataclasses

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
