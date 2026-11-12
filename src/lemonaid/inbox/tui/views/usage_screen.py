"""The usage view: each limit window's pace, projection and reset, as a modal over the inbox or a brief."""

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label

from ....config import Config
from ....usage import table
from ..tables.scroll_position import StableTable
from . import usage_view


class UsageScreen(ModalScreen[None]):
    CSS = """
    UsageScreen {
        align: center middle;
    }

    UsageScreen > Vertical {
        width: 100%;
        height: auto;
        max-height: 100%;
        padding: 0 1;
        background: $surface;
        border: thick $primary;
    }

    UsageScreen .title {
        width: 100%;
        text-align: center;
        text-style: bold;
    }

    UsageScreen DataTable {
        height: auto;
        max-height: 85vh;  /* scrolls itself, leaving room for the title and border */
    }
    """

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        for key in {self._config.tui.keybindings.usage_view, "escape", "q", "backspace"}:
            self._bindings.bind(key, "dismiss", "Close", show=False)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Usage", classes="title")
            yield StableTable(id="usage_modal_table", cursor_type="none")

    def on_mount(self) -> None:
        usage_view.setup_table(self.query_one(DataTable))
        self._load()
        self.set_interval(self._config.usage.poll_seconds, self._load)

    def _load(self) -> None:
        def read() -> None:
            current = usage_view.read_samples()
            self.app.call_from_thread(self._fill, current)

        self.run_worker(read, thread=True, group="usage-modal", exclusive=True)

    def _fill(self, current: dict) -> None:
        if self.is_mounted:
            usage_view.fill_table(
                self.query_one(DataTable),
                table.rows(current, time.time(), self._config.usage),
                self._config.usage,
            )
