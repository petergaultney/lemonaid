"""Modal screens for the TUI."""

import datetime as dt
import time
from collections import abc

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList
from textual.widgets.option_list import Option

from .. import snooze_time


def format_wake_time(until: float, now: float | None = None) -> str:
    """Render a wake time as a short human label (e.g. '14:30', 'Fri 09:00')."""
    now = now if now is not None else time.time()
    wake = dt.datetime.fromtimestamp(until)
    if wake.date() == dt.datetime.fromtimestamp(now).date():
        return wake.strftime("%H:%M")

    return wake.strftime("%a %H:%M")


class SnoozeScreen(ModalScreen[float | None]):
    """Duration picker for snoozing a session.

    The duration box has focus from the start; with it empty, Enter takes the
    highlighted preset, which Up and Down move. Dismisses with an absolute wake
    timestamp, or None on cancel.
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

    SnoozeScreen Input {
        width: 100%;
        margin-bottom: 1;
    }

    SnoozeScreen OptionList {
        height: auto;
        max-height: 10;
    }

    SnoozeScreen .hint {
        color: $text-muted;
        text-style: italic;
        padding-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("up", "preset(-1)", "Previous preset"),
        ("down", "preset(1)", "Next preset"),
    ]

    def __init__(
        self,
        session_name: str = "",
        presets: abc.Sequence[str] = snooze_time.DEFAULT_PRESETS,
        day_start: dt.time = snooze_time.DEFAULT_DAY_START,
    ) -> None:
        super().__init__()
        self.session_name = session_name
        self._presets = tuple(presets)
        self._day_start = day_start

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Snooze {self.session_name}".strip())
            yield Input(placeholder="type 45m, 2h, 3d, 1w - or pick below", id="snooze-custom")
            now = time.time()
            options = OptionList(
                *[
                    Option(snooze_time.describe(preset, now, self._day_start), id=str(index))
                    for index, preset in enumerate(self._presets)
                ],
                id="snooze-options",
            )
            options.can_focus = False
            yield options
            yield Label("Enter to snooze, Up/Down for a preset, Escape to cancel", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#snooze-options", OptionList).highlighted = 0
        self.query_one("#snooze-custom", Input).focus()

    def _wake_for_preset(self, key: str | None) -> float | None:
        if key is None or not self._presets:
            return None

        return snooze_time.parse_wake(self._presets[int(key)], time.time(), self._day_start)

    def action_preset(self, step: int) -> None:
        options = self.query_one("#snooze-options", OptionList)
        current = options.highlighted if options.highlighted is not None else 0
        options.highlighted = (current + step) % options.option_count

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        until = self._wake_for_preset(event.option.id)
        if until is not None:
            self.dismiss(until)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if not event.value.strip():
            options = self.query_one("#snooze-options", OptionList)
            until = self._wake_for_preset(options.get_option_at_index(options.highlighted or 0).id)
        else:
            until = snooze_time.parse_wake(event.value, time.time(), self._day_start)
        if until is None:
            self.notify(f"Enter {snooze_time.SYNTAX}", severity="warning")
            return

        self.dismiss(until)

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
