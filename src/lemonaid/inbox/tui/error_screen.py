"""A modal that says why a key did nothing."""

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label

from ...log import get_logger

_log = get_logger("tui")


class ErrorScreen(ModalScreen[bool]):
    """Says why an action did nothing. Any key or click dismisses it.

    A toast is easy to miss, and in a narrow scratch pane it may not show at
    all, which leaves a keypress that apparently did nothing.

    With an *offer*, the `dialog_accept` key dismisses it with True, for the caller to act on.
    """

    CSS = """
    ErrorScreen {
        align: center middle;
    }

    ErrorScreen > Vertical {
        width: 60;
        max-width: 95%;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $error;
    }

    ErrorScreen Label {
        width: 100%;
    }

    ErrorScreen .title {
        text-style: bold;
        padding-bottom: 1;
    }

    ErrorScreen .details {
        padding-top: 1;
        color: $text-muted;
    }

    ErrorScreen .hint {
        color: $text-muted;
        text-style: italic;
        padding-top: 1;
    }
    """

    def __init__(self, title: str, message: str, offer: str = "", details: str = "") -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._offer = offer
        self._details = details

    @property
    def accept_key(self) -> str:
        return self.app.config.tui.keybindings.dialog_accept  # type: ignore[attr-defined]

    def accepts(self, event: events.Key) -> bool:
        return bool(self.accept_key) and self.accept_key in (event.key, event.character)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title, classes="title")
            yield Label(self._message)
            if self._details:
                yield Label(self._details, classes="details")
            yield Label(
                f"Press {self.accept_key} to {self._offer}, any other key to close"
                if self._offer
                else "Press any key to close",
                classes="hint",
            )

    def on_key(self, event: events.Key) -> None:
        event.stop()
        self.dismiss(bool(self._offer) and self.accepts(event))

    def on_click(self) -> None:
        self.dismiss(False)


def show(app: App, title: str, message: str) -> None:
    _log.warning("%s: %s", title, message)
    app.push_screen(ErrorScreen(title, message))
