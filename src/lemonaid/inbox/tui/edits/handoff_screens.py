"""Destination selection and explicit confirmation for harness handoff."""

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select


class HandoffScreen(ModalScreen[tuple[str, bool] | None]):
    CSS = """
    HandoffScreen, HandoffConfirm { align: center middle; }
    HandoffScreen > VerticalScroll, HandoffConfirm > VerticalScroll {
        width: 64; max-width: 100%; height: auto; max-height: 100%;
        padding: 1 2; background: $surface; border: thick $primary;
    }
    HandoffScreen Label, HandoffConfirm Label { width: 100%; height: auto; margin-bottom: 1; }
    HandoffScreen Horizontal, HandoffConfirm Horizontal { height: auto; }
    """
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, source: str, destinations: tuple[str, ...]) -> None:
        super().__init__()
        self.source = source
        self.destinations = destinations

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Label(f"Hand off {self.source}", markup=False)
            yield Select(
                [(name, name) for name in self.destinations], allow_blank=False, id="destination"
            )
            yield Select(
                [
                    ("Cooperative: request a fresh handoff note", "cooperative"),
                    ("Recovery: use saved context, no outgoing turn", "recovery"),
                ],
                allow_blank=False,
                id="handoff-mode",
            )
            yield Label("Recovery stops the outgoing process and replaces it in the same pane.")
            with Horizontal():
                yield Button("Cancel", id="cancel")
                yield Button("Review handoff", id="review", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "review":
            destination = self.query_one("#destination", Select).value
            recovery = self.query_one("#handoff-mode", Select).value == "recovery"
            self.dismiss((str(destination), recovery))
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class HandoffConfirm(ModalScreen[bool]):
    CSS = HandoffScreen.CSS
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, source: str, destination: str, recovery: bool) -> None:
        super().__init__()
        self.source = source
        self.destination = destination
        self.recovery = recovery

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Label(f"Hand off {self.source} to {self.destination}?", markup=False)
            yield Label(
                "Recovery uses only existing durable context, which may be incomplete. "
                "It requests no final outgoing turn. The outgoing process is stopped and replaced in this same pane. "
                "No second live lemon is kept. The previous conversation remains in session history."
                if self.recovery
                else "Ask the outgoing lemon to write a fresh handoff note, then replace it "
                "in its current pane after readiness. Its original session remains recoverable."
            )
            with Horizontal():
                yield Button("Cancel", id="cancel")
                yield Button(
                    "Confirm recovery" if self.recovery else "Confirm handoff",
                    id="confirm",
                    variant="warning",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)
