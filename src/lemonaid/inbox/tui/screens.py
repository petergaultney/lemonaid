"""Modal screens for the TUI."""

import time
import typing as ty
from datetime import datetime, timedelta

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList
from textual.widgets.option_list import Option

_MORNING_HOUR: ty.Final = 9


def next_morning(now: float) -> float:
    """The next 9am strictly after `now`."""
    dt = datetime.fromtimestamp(now)
    target = dt.replace(hour=_MORNING_HOUR, minute=0, second=0, microsecond=0)
    if target <= dt:
        target += timedelta(days=1)

    return target.timestamp()


def parse_duration(text: str) -> float | None:
    """Parse a relative duration like '45m', '2h', '3d' into seconds.

    A bare number is read as minutes. Returns None if unparseable or not
    positive, which the caller surfaces rather than snoozing by accident.
    """
    text = text.strip().lower()
    if not text:
        return None

    units = {"m": 60, "h": 3600, "d": 86400}
    multiplier = 60
    if text[-1] in units:
        multiplier = units[text[-1]]
        text = text[:-1]

    try:
        value = float(text)
    except ValueError:
        return None

    return value * multiplier if value > 0 else None


def format_wake_time(until: float, now: float | None = None) -> str:
    """Render a wake time as a short human label (e.g. '14:30', 'Fri 09:00')."""
    now = now if now is not None else time.time()
    dt = datetime.fromtimestamp(until)
    if dt.date() == datetime.fromtimestamp(now).date():
        return dt.strftime("%H:%M")

    return dt.strftime("%a %H:%M")


class SnoozeScreen(ModalScreen[float | None]):
    """Duration picker for snoozing a session.

    Dismisses with an absolute wake timestamp, or None on cancel.
    """

    CSS = """
    SnoozeScreen {
        align: center middle;
    }

    SnoozeScreen > Vertical {
        width: 52;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    SnoozeScreen Label {
        width: 100%;
        text-align: center;
        padding-bottom: 1;
    }

    SnoozeScreen OptionList {
        height: auto;
        max-height: 10;
    }

    SnoozeScreen Input {
        width: 100%;
        display: none;
    }

    SnoozeScreen .custom Input {
        display: block;
    }

    SnoozeScreen .hint {
        color: $text-muted;
        text-style: italic;
        padding-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    # (id, label, seconds from now) — None seconds means a computed/custom target.
    _PRESETS: ty.Final = (
        ("15m", "15 minutes", 15 * 60),
        ("1h", "1 hour", 3600),
        ("4h", "4 hours", 4 * 3600),
        ("morning", "Tomorrow morning (9am)", None),
        ("custom", "Custom...", None),
    )

    def __init__(self, session_name: str = "") -> None:
        super().__init__()
        self.session_name = session_name

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Snooze {self.session_name}".strip())
            yield OptionList(
                *[Option(label, id=key) for key, label, _ in self._PRESETS],
                id="snooze-options",
            )
            yield Input(placeholder="e.g. 45m, 2h, 3d", id="snooze-custom")
            yield Label("Enter to pick, Escape to cancel", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#snooze-options", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        key = event.option.id
        if key == "custom":
            self.query_one(Vertical).add_class("custom")
            self.query_one("#snooze-custom", Input).focus()
            return

        if key == "morning":
            self.dismiss(next_morning(time.time()))
            return

        for preset_key, _, seconds in self._PRESETS:
            if preset_key == key and seconds is not None:
                self.dismiss(time.time() + seconds)
                return

    def on_input_submitted(self, event: Input.Submitted) -> None:
        seconds = parse_duration(event.value)
        if seconds is None:
            self.notify("Enter a duration like 45m, 2h, or 3d", severity="warning")
            return

        self.dismiss(time.time() + seconds)

    def action_cancel(self) -> None:
        self.dismiss(None)


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
