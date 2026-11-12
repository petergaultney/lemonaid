"""Editing the selected lemon's brief in the person's editor, through `lemonaid brief edit`."""

import os
import subprocess
from collections import abc

from textual.app import App

from ....brief import attached, hand_edit_cli, store
from ... import db


def edit(
    app: App,
    notification: db.Notification,
    open_popup: abc.Callable[[abc.Sequence[str], str], None],
) -> str:
    """Open the editor in a popup inside tmux, or in this terminal outside it; a notice, or "" when it opened."""
    with db.connect(timeout=db.UI_TIMEOUT_SECONDS) as conn:
        path = attached.for_rows(conn, [notification]).get(notification.channel)
    if path is None:
        return "No attached brief to edit"

    if error := store.outside_error(path):
        return error  # said here, since a popup's own error closes with it

    editor = hand_edit_cli.editor()
    if os.environ.get("TMUX"):
        open_popup(
            hand_edit_cli.command(path, editor, popup=True),
            f"edit {notification.name or path.stem}",
        )
        return ""

    with app.suspend():
        subprocess.run(hand_edit_cli.command(path, editor), check=False)
    return ""
