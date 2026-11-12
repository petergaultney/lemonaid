"""Editing a lemon's brief in the person's editor from a running app.

The app keeps the copy, merges it and tells the lemon itself (`brief.hand_edit`), and
starts only the editor: in the front end's popup, waited on from a worker so the app
keeps drawing, or in the app's own terminal while the app is suspended.
"""

import dataclasses
import subprocess
from collections import abc
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ....brief import attached, hand_edit, store
from ....front_end import interface
from ....log import get_logger
from ... import db

_log = get_logger("tui.brief_edit")

SEVERAL_BRIEFS = "This view shows more than one brief; open one lemon's brief to edit it"

Popup = abc.Callable[[abc.Sequence[str], str], int | None]


def row_brief(notification: db.Notification) -> Path | None:
    with db.connect(timeout=db.UI_TIMEOUT_SECONDS) as conn:
        return attached.for_rows(conn, [notification]).get(notification.channel)


def edit(app: App, path: Path, title: str, front_end: interface.FrontEnd | None) -> str:
    """Start editing *path*; a notice, or "" once the editor is starting.

    What happens when the editor exits arrives later, as a notification or a dialog.
    """
    if error := store.outside_error(path):
        return error

    try:
        session = hand_edit.start(path)
    except OSError as error:
        return f"Couldn't copy {path.name} to edit: {error}"

    popup = front_end.popup if front_end else None
    _Edit(app, session, hand_edit.editor_command(), f"edit {title}", popup).open_editor()
    return ""


class EditAgainScreen(ModalScreen[bool]):
    """Why the edit didn't apply; True to edit the copy again, False to stop."""

    CSS = """
    EditAgainScreen {
        align: center middle;
    }

    EditAgainScreen > Vertical {
        width: 80%;
        height: auto;
        border: round $warning;
        background: $panel;
        padding: 0 1;
    }
    """
    BINDINGS = [
        Binding("e", "choose(True)", "Edit again"),
        Binding("s", "choose(False)", "Stop"),
        Binding("escape", "choose(False)", "Stop"),
    ]

    def __init__(self, why: str, copy: Path) -> None:
        super().__init__()
        self._why = why
        self._copy = copy

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._why, markup=False)
            yield Static("")
            yield Static("e  edit your copy again", markup=False)
            yield Static(
                "s  stop: the brief stays as it is now, and its lemon isn't told anything."
                f" Your edited copy is kept at {self._copy}",
                markup=False,
            )

    def action_choose(self, again: bool) -> None:
        self.dismiss(again)


@dataclasses.dataclass
class _Edit:
    app: App
    session: hand_edit.Session
    editor: list[str]
    title: str
    popup: Popup | None  # None: run the editor in the app's own terminal

    def open_editor(self) -> None:
        argv = [*self.editor, str(self.session.copy)]
        if self.popup is None:
            with self.app.suspend():
                exit_status = _run_here(argv)
            self._exited(exit_status)
            return

        popup = self.popup
        self.app.run_worker(
            lambda: self.app.call_from_thread(self._exited, _run_in(popup, argv, self.title)),
            thread=True,
            group="brief-edit",
            exit_on_error=False,
        )

    def _exited(self, exit_status: int | None) -> None:
        if exit_status is None:
            self.app.notify(
                f"The editor didn't start. {hand_edit.stop(self.session)}", severity="error"
            )
            return

        try:
            result = hand_edit.after_editor(self.session, exit_status)
        except (OSError, ValueError) as error:
            _log.warning("Editing %s failed: %s", self.session.path, error)
            self.app.notify(f"{error}. {hand_edit.stop(self.session)}", severity="error")
            return

        match result:
            case hand_edit.Finished(message):
                self.app.notify(message)
            case hand_edit.Choose(why):
                self.app.push_screen(EditAgainScreen(why, self.session.copy), self._chose)

    def _chose(self, again: bool | None) -> None:
        if again:
            self.open_editor()
            return

        self.app.notify(hand_edit.stop(self.session), severity="warning", timeout=15)


def _run_here(argv: list[str]) -> int | None:
    try:
        return subprocess.run(argv, check=False).returncode
    except OSError as error:
        _log.warning("Couldn't start the editor %r: %s", argv[0], error)
        return None


def _run_in(popup: Popup, argv: list[str], title: str) -> int | None:
    try:
        return popup(argv, title)
    except OSError as error:
        _log.warning("Couldn't open the editor's popup: %s", error)
        return None
