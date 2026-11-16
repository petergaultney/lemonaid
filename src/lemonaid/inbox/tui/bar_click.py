"""A click on an attention bar, the inbox's or the brief view's, as one message."""

from textual.message import Message
from textual.widgets import Static


class BarClicked(Message):
    pass


class SummaryBar(Static):
    def on_click(self) -> None:
        self.post_message(BarClicked())
