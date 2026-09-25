"""The scratch pane's scrollable brief view."""

import time

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Markdown

from ...brief import pr, render, target


class BriefView(VerticalScroll):
    DEFAULT_CSS = """
    BriefView {
        height: 1fr;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._rendered_markdown: str | None = None
        self._pr_states = pr.Cache()

    def compose(self) -> ComposeResult:
        yield Markdown(id="brief_markdown")

    def show(self, found: target.Target) -> None:
        self._rendered_markdown = None
        self.update_brief(found)
        self.scroll_home(animate=False)

    def update_brief(self, found: target.Target) -> None:
        rendered = render.markdown(found, time.time(), self._pr_states.get)
        if rendered != self._rendered_markdown:
            self.query_one(Markdown).update(rendered)
            self._rendered_markdown = rendered
