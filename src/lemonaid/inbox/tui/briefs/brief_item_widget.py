"""A selectable entry whose links, double clicks and drag selection keep working."""

from collections import abc

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.geometry import Offset
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Markdown, Static

from . import brief_items


class ItemView(Vertical):
    DEFAULT_CSS = """
    ItemView {
        height: auto;
        border-left: thick transparent;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    ItemView.-selected {
        border-left: thick $accent;
        background: $accent 12%;
    }
    ItemView .item-title {
        height: auto;
        text-style: bold;
        color: $text-muted;
    }
    ItemView.-selected .item-title {
        color: $accent;
    }
    """

    class Chosen(Message):
        def __init__(self, item: brief_items.Item, activate: bool) -> None:
            super().__init__()
            self.item, self.activate = item, activate

    def __init__(
        self,
        item: brief_items.Item,
        markdown: str,
        factory: abc.Callable[[str], Markdown],
        selected: bool,
    ) -> None:
        super().__init__()
        self.item, self.markdown, self.factory = item, markdown, factory
        self._down: Offset | None = None
        self._activation: Timer | None = None
        self.set_class(selected, "-selected")
        self._title = Static(self._title_text(), classes="item-title", markup=False)

    def _title_text(self) -> str:
        title = {"need": "Needs", "answer": "Saved answer", "archived": "Archived answer"}[
            self.item.kind
        ]
        return f"{'▶ ' if self.has_class('-selected') else ''}{title}: {self.item.label}"

    def compose(self) -> ComposeResult:
        yield self._title
        yield self.factory(self.markdown)

    def select(self, selected: bool) -> None:
        self.set_class(selected, "-selected")
        self._title.update(self._title_text())

    def scroll_title(self) -> None:
        if self._title.is_attached:
            self._title.scroll_visible(animate=False)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._down = event.screen_offset

    def _activate(self) -> None:
        if (
            self.is_mounted
            and self.app.screen is self.screen
            and self.has_class("-selected")
            and not self.screen.get_selected_text()
        ):
            self.post_message(self.Chosen(self.item, True))

    def on_click(self, event: events.Click) -> None:
        if self._activation:
            self._activation.stop()
        if (
            event.button != 1
            or event.shift
            or event.ctrl
            or event.meta
            or event.chain != 1
            or event.screen_offset != self._down
            or event.style.link
            or event.style.meta.get("@click")
            or self.screen.get_selected_text()
        ):
            return

        event.stop()
        if self.has_class("-selected"):
            self._activation = self.set_timer(
                self.app.CLICK_CHAIN_TIME_THRESHOLD + 0.05, self._activate
            )
        else:
            self.post_message(self.Chosen(self.item, False))
