"""Hiding a lemon through the same checked brief edit as `brief hide`."""

from ....brief import attached, hidden, verbs_cli
from ....log import get_logger
from ... import db
from ..live.inbox_list import InboxList

_log = get_logger("tui")


def toggle(inbox: InboxList, notification: db.Notification) -> None:
    with db.connect() as conn:
        path = attached.for_rows(conn, [notification]).get(notification.channel)
    if path is None:
        inbox.notify("No attached brief to hide this lemon", severity="warning")
        return

    try:
        hide = not hidden.is_hidden(path.read_text())
        error = verbs_cli.edit(path, lambda text: hidden.with_hidden(text, hide))
    except OSError as exc:
        _log.warning("Could not edit brief %s: %s", path, exc)
        error = str(exc)
    if error:
        inbox.notify(error, severity="warning")
        return

    inbox.dismissed_key = str(notification.id) if hide else None
    inbox.redraw()
    inbox.notify(
        f"{'Hidden' if hide else 'Shown'} {notification.name or notification.channel}"
        + ("; / search includes hidden lemons" if hide else "")
    )
