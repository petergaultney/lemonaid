"""Editing a lemon's brief in the person's editor, through `lemonaid brief edit`."""

import subprocess
from pathlib import Path

from textual.app import App

from ....brief import attached, hand_edit_cli, store
from ....front_end import interface
from ... import db

SEVERAL_BRIEFS = "This view shows more than one brief; open one lemon's brief to edit it"


def row_brief(notification: db.Notification) -> Path | None:
    with db.connect(timeout=db.UI_TIMEOUT_SECONDS) as conn:
        return attached.for_rows(conn, [notification]).get(notification.channel)


def edit(app: App, path: Path, title: str, front_end: interface.FrontEnd | None) -> str:
    """Open the editor in the front end's popup, or in *app*'s own terminal without one.

    Returns a notice, or "" when the editor opened.
    """
    if error := store.outside_error(path):
        return error  # said here, since a popup's own error closes with it

    editor = hand_edit_cli.editor()
    if front_end and front_end.popup:
        front_end.popup(hand_edit_cli.command(path, editor, popup=True), f"edit {title}")
        return ""

    with app.suspend():
        subprocess.run(hand_edit_cli.command(path, editor), check=False)
    return ""
