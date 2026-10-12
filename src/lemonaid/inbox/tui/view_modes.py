"""Which panes show, and which footer actions apply, in the inbox's alternate views."""

from textual.widget import Widget

INBOX_ONLY_ACTIONS = ("jump_unread", "mark_read", "mark_unread", "snooze", "toggle_fold")
HISTORY_ONLY_ACTIONS = ("copy_resume", "filter_history", "tmux_resume")


def hide_inbox_panes(*panes: Widget) -> None:
    for pane in panes:
        pane.display = False
