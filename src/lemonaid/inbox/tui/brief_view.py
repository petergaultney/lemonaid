"""The scratch pane's scrollable brief view, drawn as the lemon's card opened up."""

import ast
import re
import subprocess
import sys
import time
import typing as ty

from markdown_it.token import Token
from rich.text import Text
from textual.containers import VerticalScroll
from textual.content import Content, Span
from textual.style import Style
from textual.widgets import Markdown, Rule, Static
from textual.widgets._markdown import MarkdownBlock, MarkdownParagraph  # no public name

from ...brief import links, pr, render, target
from ...log import get_logger
from . import brief_card, utils

_log = get_logger("tui.brief_view")
_OPENER = ["open"] if sys.platform == "darwin" else ["xdg-open"]

_CLICK_LINK = re.compile(r"link\((?P<href>'[^']*'|\"[^\"]*\")\)")


def _href(style: Style) -> str:
    """The URL of a Markdown link's `@click` action, or ""."""
    match = _CLICK_LINK.fullmatch(str(style.meta.get("@click", "")))
    return ast.literal_eval(match["href"]) if match else ""


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


def open_link(url: str) -> None:
    """Hand *url* to the system opener, which knows which app owns its scheme.

    Textual's default goes through `webbrowser`, which gives an `obsidian://`
    link to the browser instead of Obsidian.
    """
    try:
        subprocess.Popen([*_OPENER, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        _log.warning("could not open %s with %s: %s", url, _OPENER[0], e)


class _LinkedParagraph(MarkdownParagraph):
    """A paragraph whose links are terminal hyperlinks too, and open in their own app.

    Textual makes a link clickable inside the app only. A hyperlink lets the
    terminal open it on cmd-click, from any line a wrapped label lands on. A
    click here opens the URL as written: Textual's own click message decodes it,
    which breaks an encoded `obsidian://` file path.
    """

    async def action_link(self, href: str) -> None:
        open_link(href)

    def _token_to_content(self, token: Token) -> Content:
        content = super()._token_to_content(token)
        return Content(
            content.plain,
            spans=[
                Span(span.start, span.end, span.style + Style(link=href))
                if isinstance(span.style, Style) and (href := _href(span.style))
                else span
                for span in content.spans
            ],
        )


class _Markdown(Markdown):
    BLOCKS: ty.ClassVar[dict[str, type[MarkdownBlock]]] = {
        **Markdown.BLOCKS,
        "paragraph_open": _LinkedParagraph,
    }


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
    BriefView MarkdownBlock {{
        link-color: {utils.LINK_COLOR};
        link-style: underline;
        link-color-hover: {utils.LINK_COLOR};
        link-style-hover: bold underline;
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

    def __init__(self, pr_state: pr.Lookup = pr.no_state, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._rendered_markdown: str | None = None
        self._pr_states = pr.Cache(pr_state)

    def show(self, found: target.Target) -> None:
        self._rendered_markdown = None
        self.update_brief(found)
        self.scroll_home(animate=False)

    def _widgets(self, shown: render.View, now: float) -> list[Static | Markdown | Rule]:
        if not shown.sections:
            return [_Markdown(links.linkify(render.to_markdown(shown, now)))]

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
                *([_Markdown(links.linkify(section.body))] if section.body else []),
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
