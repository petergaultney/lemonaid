"""What tmux must have recorded, before a crash, to bring a running lemon back after it."""

from ..inbox import db, doctor

ADVICE = "See `lemonaid tmux doctor`; `lemonaid tmux adopt` adds unknown panes."


def unready(row: db.Notification) -> str:
    """Why restore couldn't bring *row*'s lemon back to its tmux window, or ""."""
    if not row.metadata.get("tmux_session") or row.metadata.get("tmux_window") is None:
        return "no recorded tmux window"

    if not row.metadata.get("tmux_socket") or not row.metadata.get("tmux_session_order"):
        return "no recorded tmux server, so its loss can't be told"

    return ""


def strays() -> list[str]:
    """Running lemon panes the inbox has no row for, which no restore would bring back."""
    return [
        f"{pane.session}:{pane.window}: a running {pane.command} the inbox doesn't know"
        for pane in doctor.unknown_panes()
    ]
