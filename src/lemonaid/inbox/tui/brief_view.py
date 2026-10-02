"""The scratch pane's scrollable brief view, drawn as the lemon's card opened up."""

import ast
import dataclasses
import functools
import re
import subprocess
import sys
import time
import urllib.parse
from collections import abc
from pathlib import Path

from markdown_it.token import Token
from rich.text import Text
from textual.binding import Binding, BindingsMap
from textual.containers import VerticalScroll
from textual.content import Content, Span
from textual.style import Style
from textual.widgets import Markdown, Rule, Static
from textual.widgets._markdown import MarkdownBlock  # no public name

from ...brief import attached, family, links, pr, questions, render, target
from ...config import KeybindingsConfig, PlaceRoot
from ...log import get_logger
from .. import db, turns
from . import brief_card, brief_questions, utils

_log = get_logger("tui.brief_view")
_OPENER = ["open"] if sys.platform == "darwin" else ["xdg-open"]

_DEFAULT_KEYS = KeybindingsConfig()
_CLICK_LINK = re.compile(r"link\((?P<href>'[^']*'|\"[^\"]*\")\)")


def _href(style: Style) -> str:
    """The URL of a Markdown link's `@click` action, or ""."""
    match = _CLICK_LINK.fullmatch(str(style.meta.get("@click", "")))
    return ast.literal_eval(match["href"]) if match else ""


def _working(section: render.Section) -> render.Section:
    """*section* as its lemon shows mid-turn, its brief's status kept as `held`."""
    state = turns.shown(section.state)
    return (
        section
        if state == section.state
        else dataclasses.replace(section, state=state, held=section.state)
    )


def _mid_turn(shown: render.View, now: float) -> render.View:
    """*shown* with each section whose lemon is mid-turn in the state it shows meanwhile."""
    with db.connect() as conn:
        rows = db.get_active(conn)
        working = turns.briefs(rows, attached.by_channel(conn, (n.channel for n in rows)), now)

    return dataclasses.replace(
        shown,
        sections=tuple(
            _working(section) if section.path in working else section for section in shown.sections
        ),
    )


class _Card(Static):
    """A section's card header, laid out for whatever width the pane has."""

    DEFAULT_CSS = """
    _Card {
        height: auto;
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
    BriefView .brief-needs-mid-turn MarkdownBlockQuote {{
        border-left: outer $foreground 30%;
        color: $text-muted;
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
    BriefView .brief-question-keys {{
        dock: bottom;
        height: 1;
        color: $text-muted;
        background: $panel;
    }}
    """

    def __init__(
        self,
        pr_state: pr.Lookup = pr.no_state,
        vaults: abc.Collection[Path] = (),
        keys: KeybindingsConfig = _DEFAULT_KEYS,
        mid_turn_working: bool = False,
        roots: abc.Sequence[PlaceRoot] = (),
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._mid_turn_working = mid_turn_working
        self._roots = roots
        self._rendered_markdown: str | None = None
        self._pr_states = pr.Cache(pr_state)
        self._vaults = vaults
        self._keys = keys
        self._sections: tuple[render.Section, ...] = ()
        self._selected: brief_questions.Choice | None = None
        self._needs: dict[Path, _Markdown] = {}
        # Built as a map, not bound one by one, so a character such as `(` becomes its key name.
        self._bindings = BindingsMap.merge(
            [
                self._bindings,
                BindingsMap(
                    Binding(key, action, description, show=False)
                    for key, action, description in (
                        (keys.question_previous, "question(-1)", "Previous question"),
                        (keys.question_next, "question(1)", "Next question"),
                        (keys.answer, "answer", "Answer"),
                        (keys.more_detail, "more_detail", "More detail"),
                    )
                    if key
                ),
            ]
        )

    def show(self, found: target.Target, unread: bool = False) -> None:
        self._rendered_markdown = None
        self._selected = None
        self.update_brief(found, unread)
        self.scroll_home(animate=False)

    def _widgets(
        self, shown: render.View, now: float, unread: bool
    ) -> list[Static | Markdown | Rule]:
        if not shown.sections:
            return [_Markdown(links.linkify(render.to_markdown(shown, now), self._vaults))]

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
                *([self._needs_widget(section)] if section.needs_text else []),
                *([_Markdown(links.linkify(section.body, self._vaults))] if section.body else []),
                *(
                    [Static(brief_card.children(section), classes="brief-children")]
                    if section.children
                    else []
                ),
                *([_Markdown(links.linkify(section.tail, self._vaults))] if section.tail else []),
            )
        ]
        return [
            *top,
            *sections,
            Rule(),
            Static(brief_card.files(shown), classes="brief-files"),
            *(
                [Static(brief_questions.hint(self._keys), classes="brief-question-keys")]
                if self._selected
                else []
            ),
        ]

    def _needs_markdown(self, section: render.Section) -> str:
        selected = self._selected[1] if self._selected and self._selected[0] == section.path else ""
        return links.linkify(render.needs(section, True, selected), self._vaults)

    def _needs_widget(self, section: render.Section) -> _Markdown:
        widget = _Markdown(
            self._needs_markdown(section), classes="brief-needs-mid-turn" if section.held else ""
        )
        if section.path:
            self._needs[section.path] = widget
        return widget

    def _choices(self) -> list[brief_questions.Choice]:
        return brief_questions.choices(self._sections)

    def _section(self, path: Path) -> render.Section | None:
        return next((s for s in self._sections if s.path == path), None)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"question", "answer", "more_detail"}:
            return self._selected is not None

        return True

    def action_question(self, by: int) -> None:
        before = self._selected
        self._selected = brief_questions.step(self._choices(), self._selected, by)
        for path in {choice[0] for choice in (before, self._selected) if choice}:
            if (widget := self._needs.get(path)) and (section := self._section(path)):
                widget.update(self._needs_markdown(section))

    def _lemon_name(self, path: Path) -> str:
        section = self._section(path)
        return (section.lemon.name if section and section.lemon else "") or path.stem

    def _send(self, choice: brief_questions.Choice, body: str) -> None:
        if why := brief_questions.send(choice[0], body):
            self.notify(why, title="Not sent", severity="error")
            return

        self.notify(f"Sent to {self._lemon_name(choice[0])}: {choice[1]}")

    def action_answer(self) -> None:
        choice = self._selected
        if choice is None:
            return

        def answered(text: str | None) -> None:
            if text:
                self._send(choice, brief_questions.answer(*choice, text))

        self.app.push_screen(
            brief_questions.AnswerScreen(choice[1], self._lemon_name(choice[0])), answered
        )

    def action_more_detail(self) -> None:
        if self._selected:
            self._send(self._selected, questions.more_detail(self._selected[1]))

    def update_brief(self, found: target.Target, unread: bool = False) -> None:
        """Redraw *found*, whose inbox row is *unread* or not."""
        now = time.time()
        shown = family.added(render.view(found, now, self._pr_states.get, self._roots))
        shown = _mid_turn(shown, now) if self._mid_turn_working else shown
        rendered = render.to_markdown(shown, now, expanded=True)
        if rendered == self._rendered_markdown:
            for card in self.query(_Card):
                card.now = now
                card.unread = unread
                card.refresh()
            return

        self._rendered_markdown = rendered
        self._sections = shown.sections
        available = self._choices()
        self._selected = (
            self._selected if self._selected in available else next(iter(available), None)
        )
        self._needs = {}
        self.remove_children()
        self.mount_all(self._widgets(shown, now, unread))
