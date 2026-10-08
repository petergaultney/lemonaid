"""Resume failures stay visible while the user reads their recovery instructions."""

from textual import events
from textual.containers import Vertical
from textual.widgets import Label

from .error_screen import ErrorScreen


class ResumeErrorScreen(ErrorScreen):
    DEFAULT_CSS = (
        ErrorScreen.CSS.replace("ErrorScreen", "ResumeErrorScreen")
        + """
    ResumeErrorScreen > Vertical {
        max-height: 95%;
        overflow-y: auto;
    }
    ResumeErrorScreen Label {
        height: auto;
        text-wrap: wrap;
    }
    """
    )

    def on_mount(self) -> None:
        self.query_one(".hint", Label).update(
            (f"Press a to {self._offer}; " if self._offer else "") + "Escape or Enter closes"
        )

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        if event.key in {"escape", "enter", "q"}:
            self.dismiss(False)
        elif self._offer and event.key == "a":
            self.dismiss(True)
        elif event.key in {"up", "down", "pageup", "pagedown"}:
            amount = {"up": -1, "down": 1, "pageup": -10, "pagedown": 10}[event.key]
            self.query_one(Vertical).scroll_relative(y=amount, animate=False)

    def on_click(self) -> None:
        pass
