"""The scratch pane's scrollable brief view, drawn as the lemon's card opened up."""

import ast
import functools
import re
import subprocess
import sys
import time
import urllib.parse

from markdown_it.token import Token
from rich.text import Text
from textual.containers import VerticalScroll
from textual.content import Content, Span
from textual.style import Style
from textual.widgets import Markdown, Rule, Static
from textual.widgets._markdown import MarkdownBlock  # no public name

from ...brief import family, links, pr, render, target
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

    def __init__(self, section: render.Section, in_session: bool, now: float, unread: bool) -> None:
        super().__init__()
        self._section = section
        self._in_session = in_session
        self.now = now
        self.unread = unread

    def render(self) -> Text:
        return brief_card.header(
            self._section, self._in_session, self.now, self.size.width, self.unread
        )


def open_link(url: str) -> None:
    """Hand *url* to the system opener, which knows which app owns its scheme.

    Textual's default goes through `webbrowser`, which gives an `obsidian://`
    link to the browser instead of Obsidian.
    """
    try:
        subprocess.Popen([*_OPENER, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        _log.warning("could not open %s with %s: %s", url, _OPENER[0], e)


def _linked(content: Content) -> Content:
    """*content* with each link a terminal hyperlink too, clicked with its URL quoted once more.

    Textual makes a link clickable inside the app only. A hyperlink lets the
    terminal open it on cmd-click, from any line a wrapped label lands on.
    Textual's click message unquotes the URL, which breaks an encoded
    `obsidian://` file path, so the click action carries it quoted.
    """
    return Content(
        content.plain,
        spans=[
            Span(
                span.start,
                span.end,
                span.style
                + Style(link=href)
                + Style.from_meta({"@click": f"link({urllib.parse.quote(href, safe='')!r})"}),
            )
            if isinstance(span.style, Style) and (href := _href(span.style))
            else span
            for span in content.spans
        ],
    )


@functools.cache
def _linked_block(block: type[MarkdownBlock]) -> type[MarkdownBlock]:
    """*block* with its links made by `_linked`; a direct subclass, so its CSS is unchanged."""

    def _token_to_content(self: MarkdownBlock, token: Token) -> Content:
        return _linked(block._token_to_content(self, token))

    return type(block.__name__, (block,), {"_token_to_content": _token_to_content})


class _Markdown(Markdown):
    """Markdown whose links open in their own app, from any block: a heading, paragraph or table cell."""

    def get_block_class(self, block_name: str) -> type[MarkdownBlock]:
        return _linked_block(super().get_block_class(block_name))

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        event.prevent_default()
        open_link(event.href)


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
    BriefView .brief-children {{
        margin-bottom: 1;
    }}
    BriefView .brief-files {{
        color: $text-muted;
    }}
    """

    def __init__(self, pr_state: pr.Lookup = pr.no_state, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._rendered_markdown: str | None = None
        self._pr_states = pr.Cache(pr_state)

    def show(self, found: target.Target, unread: bool = False) -> None:
        self._rendered_markdown = None
        self.update_brief(found, unread)
        self.scroll_home(animate=False)

    def _widgets(
        self, shown: render.View, now: float, unread: bool
    ) -> list[Static | Markdown | Rule]:
        if not shown.sections:
            return [_Markdown(links.linkify(render.to_markdown(shown, now)))]

        top: list[Static | Markdown | Rule] = (
            [_SessionBar(shown.header)]
            if shown.header.startswith("# ")
            else [_Markdown(shown.header)]
            if shown.header
            else []
        )
        sections = [
            widget
            for i, section in enumerate(shown.sections)
            for widget in (
                *([Rule()] if i else []),
                _Card(section, shown.in_session, now, unread),
                *([_Markdown(f"**Parent:** `{section.parent}`")] if section.parent else []),
                *([_Markdown(links.linkify(section.body))] if section.body else []),
                *(
                    [Static(brief_card.children(section), classes="brief-children")]
                    if section.children
                    else []
                ),
                *([_Markdown(links.linkify(section.tail))] if section.tail else []),
            )
        ]
        return [
            *top,
            *sections,
            Rule(),
            Static(brief_card.files(shown), classes="brief-files"),
        ]

    def update_brief(self, found: target.Target, unread: bool = False) -> None:
        """Redraw *found*, whose inbox row is *unread* or not."""
        now = time.time()
        shown = family.added(render.view(found, now, self._pr_states.get))
        rendered = render.to_markdown(shown, now)
        if rendered == self._rendered_markdown:
            for card in self.query(_Card):
                card.now = now
                card.unread = unread
                card.refresh()
            return

        self._rendered_markdown = rendered
        self.remove_children()
        self.mount_all(self._widgets(shown, now, unread))
