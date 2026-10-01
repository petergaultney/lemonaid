"""Choosing and answering the questions a brief view shows under what its lemons need."""

from collections import abc
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label

from ...brief import render, store
from ...config import KeybindingsConfig
from ...messages import to_brief

Choice = tuple[Path, str]  # a section's brief, and the label of one of its questions


def choices(sections: abc.Iterable[render.Section]) -> list[Choice]:
    return [
        (section.path, item.label)
        for section in sections
        if section.path
        for item in section.questions
        if item.label
    ]


def step(available: abc.Sequence[Choice], current: Choice | None, by: int) -> Choice | None:
    """The choice *by* places from *current*, stopping at either end; the first when it is gone."""
    if not available:
        return None

    if current not in available:
        return available[0]

    return available[max(0, min(len(available) - 1, available.index(current) + by))]


def hint(kb: KeybindingsConfig) -> str:
    moves = " ".join(key for key in (kb.question_previous, kb.question_next) if key)
    return " · ".join(
        part
        for part in (
            moves and f"{moves} question",
            kb.answer and f"{kb.answer} answer",
            kb.more_detail and f"{kb.more_detail} more detail",
        )
        if part
    )


def send(path: Path, body: str) -> str:
    """Send *body* to the lemon of the brief at *path*; "" when sent, else why not."""
    try:
        to_brief.send(path, body)
    except (OSError, ValueError, store.ChangedUnderneath) as error:
        return str(error)

    return ""


class AnswerScreen(ModalScreen[str | None]):
    """A one-line answer to a question; None on cancel."""

    CSS = """
    AnswerScreen {
        align: center middle;
    }

    AnswerScreen > Vertical {
        width: 80%;
        max-width: 100;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    AnswerScreen Label {
        width: 100%;
        padding-bottom: 1;
    }

    AnswerScreen Input {
        width: 100%;
    }

    AnswerScreen .hint {
        color: $text-muted;
        text-style: italic;
        padding-top: 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, label: str, lemon: str) -> None:
        super().__init__()
        self._label = label
        self._lemon = lemon

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Answer {self._lemon}: {self._label}", markup=False)
            yield Input(placeholder="Your answer", id="answer-input")
            yield Label("Enter to send, Escape to cancel", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#answer-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
