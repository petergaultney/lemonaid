"""A temporary action result that survives periodic status refreshes."""

from rich.markup import escape
from textual.timer import Timer
from textual.widgets import Static

from .utils import update_static


class StatusLine(Static):
    def __init__(self, *, id: str) -> None:
        super().__init__("", id=id)
        self._status = ""
        self._notice = ""
        self._expiry: Timer | None = None

    def set_status(self, text: str) -> None:
        self._status = text
        update_static(self, self._notice or text)

    def _clear_notice(self) -> None:
        self._notice = ""
        update_static(self, self._status)

    def show_notice(self, message: str) -> None:
        if self._expiry is not None:
            self._expiry.stop()
        self._notice = escape(message)
        update_static(self, self._notice)
        self._expiry = self.set_timer(10, self._clear_notice)
