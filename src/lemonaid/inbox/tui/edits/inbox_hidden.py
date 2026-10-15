"""Hiding a lemon through the same checked brief edit as `brief hide`."""

from ....brief import attached, hidden, status, verbs_cli
from ....log import get_logger
from ... import db, order, pins
from ..live.inbox_list import InboxList
from ..tables import row_keys

_log = get_logger("tui")


def _visibility(inbox: InboxList, notification: db.Notification, text: str) -> str:
    if notification.channel not in row_keys.channels(inbox.main) + row_keys.channels(inbox.other):
        return "; / search includes hidden lemons"

    with db.connect() as conn:
        pinned = notification.channel in pins.pinned_positions(conn)
    placed = "blocked" if notification.asks else status.split(text).status
    reason = (
        "pinned" if pinned else placed if order.special_status(placed) else "focus, search or deaf"
    )
    return f"; still visible: {reason}"


def toggle(inbox: InboxList, notification: db.Notification) -> str:
    with db.connect() as conn:
        path = attached.for_rows(conn, [notification]).get(notification.channel)
    if path is None:
        message = "No attached brief to hide this lemon"
        inbox.notify(message, severity="warning")
        return message

    try:
        text = path.read_text()
        hide = not hidden.is_hidden(text)
        error = verbs_cli.edit(path, lambda text: hidden.with_hidden(text, hide))
    except OSError as exc:
        _log.warning("Could not edit brief %s: %s", path, exc)
        error = str(exc)
    if error:
        inbox.notify(error, severity="warning")
        return error

    inbox.dismissed_key = str(notification.id) if hide else None
    inbox.redraw()
    message = (
        "Hidden" + _visibility(inbox, notification, text) if hide else "Shown in default inbox"
    ) + f" — {notification.name or notification.channel}"
    inbox.notify(message)
    return message
