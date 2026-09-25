"""The scratch pane's scrollable brief view, drawn as the lemon's card opened up."""

import time

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Markdown, Rule, Static

from ...brief import pr, render, target
from . import brief_card, utils


class _Card(Static):
    """A section's card header, laid out for whatever width the pane has."""

    DEFAULT_CSS = """
    _Card {
        height: 3;
        margin-bottom: 1;
    }
    """

    def __init__(self, section: render.Section, in_session: bool, now: float) -> None:
        super().__init__()
        self._section = section
        self._in_session = in_session
        self.now = now

    def render(self) -> Text:
        return brief_card.header(self._section, self._in_session, self.now, self.size.width)


class _SessionBar(Static):
    DEFAULT_CSS = f"""
    _SessionBar {{
        height: 1;
        margin-bottom: 1;
        content-align: center middle;
        background: {utils.ATTENTION_COLOR};
        color: #000000;
        text-style: bold;
    }}
    """

    def __init__(self, header: str) -> None:
        super().__init__(header.removeprefix("# ").strip(), markup=False)


class BriefView(VerticalScroll):
    DEFAULT_CSS = f"""
    BriefView {{
        height: 1fr;
        padding: 0 1;
    }}
    BriefView Markdown {{
        margin: 0;
        padding: 0;
    }}
    BriefView MarkdownBlockQuote {{
        border-left: outer {utils.ATTENTION_COLOR};
        color: {utils.ATTENTION_COLOR};
        margin: 0 0 1 0;
    }}
    BriefView Rule {{
        color: $foreground 30%;
        margin: 0;
    }}
    BriefView .brief-files {{
        color: $text-muted;
    }}
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._rendered_markdown: str | None = None
        self._pr_states = pr.Cache()

    def show(self, found: target.Target) -> None:
        self._rendered_markdown = None
        self.update_brief(found)
        self.scroll_home(animate=False)

    def _widgets(self, shown: render.View, now: float) -> list[Static | Markdown | Rule]:
        if not shown.sections:
            return [Markdown(render.to_markdown(shown, now))]

        top: list[Static | Markdown | Rule] = (
            [_SessionBar(shown.header)]
            if shown.header.startswith("# ")
            else [Markdown(shown.header)]
            if shown.header
            else []
        )
        sections = [
            widget
            for i, section in enumerate(shown.sections)
            for widget in (
                *([Rule()] if i else []),
                _Card(section, shown.in_session, now),
                *([Markdown(section.body)] if section.body else []),
            )
        ]
        return [
            *top,
            *sections,
            Rule(),
            Static(brief_card.files(shown), classes="brief-files"),
        ]

    def update_brief(self, found: target.Target) -> None:
        now = time.time()
        shown = render.view(found, now, self._pr_states.get)
        rendered = render.to_markdown(shown, now)
        if rendered == self._rendered_markdown:
            for card in self.query(_Card):
                card.now = now
                card.refresh()
            return

        self._rendered_markdown = rendered
        self.remove_children()
        self.mount_all(self._widgets(shown, now))
