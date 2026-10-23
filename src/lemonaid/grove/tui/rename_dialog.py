"""A small dialog over the grove for typing a new name."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class RenameDialog(ModalScreen[str | None]):
    """Dismisses with the name typed, or None when cancelled."""

    DEFAULT_CSS = """
    RenameDialog { align: center middle; background: #0b0e13 60%; }
    RenameDialog > Vertical {
        width: 64; height: auto; padding: 1 2;
        background: #121821; border: round #f2d94e;
    }
    RenameDialog Label { color: #9aa5b8; margin-bottom: 1; }
    RenameDialog Input { border: tall #3a4558; }
    """
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, title: str, current: str) -> None:
        super().__init__()
        self._title = title
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"{self._title} · enter saves · esc cancels")
            yield Input(self._current, select_on_focus=False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)
