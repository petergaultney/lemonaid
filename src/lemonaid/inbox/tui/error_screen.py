"""A modal that says why a key did nothing."""

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label


class ErrorScreen(ModalScreen[bool]):
    """Says why an action did nothing. Any key or click dismisses it.

    A toast is easy to miss, and in a narrow scratch pane it may not show at
    all, which leaves a keypress that apparently did nothing.

    With an *offer*, `a` dismisses it with True, for the caller to act on.
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

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title, classes="title")
            yield Label(self._message)
            if self._details:
                yield Label(self._details, classes="details")
            yield Label(
                f"Press a to {self._offer}, any other key to close"
                if self._offer
                else "Press any key to close",
                classes="hint",
            )

    def on_key(self, event: events.Key) -> None:
        event.stop()
        self.dismiss(bool(self._offer) and event.key == "a")

    def on_click(self) -> None:
        self.dismiss(False)
