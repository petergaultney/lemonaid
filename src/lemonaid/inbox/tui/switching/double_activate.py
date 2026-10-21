"""Showing a lemon without leaving the inbox, until the row is activated twice."""

from ....config import Config
from ....handlers import show_tmux_keeping_focus
from ... import db

Activation = tuple[str, float]  # row key, monotonic seconds


def is_double(previous: Activation | None, key: str, now: float, window_ms: int) -> bool:
    return previous is not None and previous[0] == key and now - previous[1] <= window_ms / 1000


def is_own_focus_cycle(shown: Activation | None, now: float, window_ms: int) -> bool:
    """Whether a focus change just after a show is the show's own select-pane round trip."""
    return shown is not None and now - shown[1] <= window_ms / 1000


def show_keeping_focus(notification: db.Notification, config: Config) -> bool:
    """Show a lemon whose tmux pane exists, focus staying in the inbox pane; else False."""
    return show_tmux_keeping_focus(
        {**notification.metadata, "channel": notification.channel, "name": notification.name or ""},
        config,
        notification.switch_source,
    )
