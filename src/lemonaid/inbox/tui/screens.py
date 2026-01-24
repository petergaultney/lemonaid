"""Modal screens for the TUI."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class RenameScreen(ModalScreen[str | None]):
    """Modal dialog for renaming a session.

    Returns the new name on submit, None on cancel.
    Empty string means "clear the override".
    """

    CSS = """
    RenameScreen {
        align: center middle;
    }

    RenameScreen > Vertical {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    RenameScreen Label {
        width: 100%;
        text-align: center;
        padding-bottom: 1;
    }

    RenameScreen Input {
        width: 100%;
    }

    RenameScreen .hint {
        color: $text-muted;
        text-style: italic;
        padding-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, current_name: str = "") -> None:
        super().__init__()
        self.current_name = current_name

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Rename Session")
            yield Input(
                value=self.current_name,
                placeholder="Enter name (empty to use auto-name)",
                id="rename-input",
            )
            yield Label("Press Enter to save, Escape to cancel", classes="hint")

    def on_mount(self) -> None:
        # Focus the input and select all text
        input_widget = self.query_one("#rename-input", Input)
        input_widget.focus()
        input_widget.action_select_all()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)
