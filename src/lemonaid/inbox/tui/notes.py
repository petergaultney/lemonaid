"""Your own notes, kept in view under the sessions in a sidebar.

A Markdown file you write: key hints while you learn tmux, a checklist,
anything worth a glance. It is read again whenever it changes, so an edit
shows on the next refresh without restarting the pane.
"""

from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import Markdown

from ...log import get_logger
from . import scroll_position

_log = get_logger("tui.notes")


def _version(path: Path) -> tuple[int, float] | None:
    """What changes when the file does, or None when there is no file to read."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime


class NotesPanel(scroll_position.StableScroll):
    """The notes file as Markdown, never more than a share of the pane's height.

    A file longer than that scrolls inside the panel, so the sessions above it
    keep the rest of the pane. It scrolls with the mouse wheel only: a panel
    that took focus would take the arrow keys from the list with it.
    """

    can_focus = False

    class Resized(Message):
        """The panel's height changed, so the cards above it can size to what is left."""

    DEFAULT_CSS = """
    NotesPanel {
        height: auto;
        max-height: 40%;
        border-top: solid $panel-lighten-2;
        scrollbar-size-vertical: 1;
    }

    NotesPanel > Markdown {
        margin: 0;
        padding: 0 1;
    }
    """

    def __init__(self, path: Path, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.path = path
        self._shown: tuple[int, float] | None | bool = False  # False: nothing read yet

    def compose(self) -> ComposeResult:
        yield Markdown()

    def on_resize(self, event: events.Resize) -> None:
        # Its height is known only once it is laid out, after whatever showed or
        # changed it has already sized the cards.
        self.post_message(self.Resized())

    def reload(self) -> None:
        """Show the file as it is now, reading and rendering it only when it has changed."""
        version = _version(self.path)
        if version == self._shown:
            return

        self._shown = version
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            _log.warning("could not read notes %s: %s", self.path, e)
            text = f"*No notes at `{self.path}`*"
        scroll_position.update(self, self.query_one(Markdown), text)
