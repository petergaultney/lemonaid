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

from markdown_it import MarkdownIt
from markdown_it.token import Token
from rich.text import Text
from textual.binding import Binding, BindingsMap
from textual.content import Content, Span
from textual.geometry import Size
from textual.style import Style
from textual.widget import Widget
from textual.widgets import Markdown, Rule, Static
from textual.widgets._markdown import (  # no public name
    MarkdownBlock,
    MarkdownTable,
)

from ....brief import attached, family, identity, links, pr, questions, render, store, target
from ....config import KeybindingsConfig, PlaceRoot
from ....log import get_logger
from ... import db, turns
from .. import scroll_position, utils
from . import (
    brief_answers,
    brief_detail,
    brief_help,
    brief_item_content,
    brief_items,
    brief_questions,
    brief_tables,
)
from .brief_item_widget import ItemView

_log = get_logger("tui.brief_view")
_OPENER = ["open"] if sys.platform == "darwin" else ["xdg-open"]

_DEFAULT_KEYS = KeybindingsConfig()
_CLICK_LINK = re.compile(r"link\((?P<href>'[^']*'|\"[^\"]*\")\)")


def _href(style: Style) -> str:
    """The URL of a Markdown link's `@click` action, or ""."""
    match = _CLICK_LINK.fullmatch(str(style.meta.get("@click", "")))
    return ast.literal_eval(match["href"]) if match else ""


def _drawn(section: render.Section, mid_turn: bool, held_mid_turn: bool) -> render.Section:
    """*section* in the state its lemon shows: `active` or `idle` without a status of its own.

    With *held_mid_turn*, a set status shows `active` mid-turn, kept as `held`.
    """
    if section.path is None:
        return section

    if not section.state:
        return dataclasses.replace(section, state="active" if mid_turn else "idle")

    state = turns.shown(section.state) if mid_turn and held_mid_turn else section.state
    return (
        section
        if state == section.state
        else dataclasses.replace(section, state=state, held=section.state)
    )


def _turns(shown: render.View, now: float, held_mid_turn: bool) -> render.View:
    """*shown* with each section in the state its lemon shows."""
    with db.connect() as conn:
        rows = db.get_active(conn)
        working = turns.briefs(rows, attached.by_channel(conn, (n.channel for n in rows)), now)

    return dataclasses.replace(
        shown,
        sections=tuple(
            _drawn(section, section.path in working, held_mid_turn) for section in shown.sections
        ),
    )


class _Card(Static):
    """A section's card header, laid out for whatever width the pane has."""

    DEFAULT_CSS = """
    _Card {
        height: auto;
        margin: 1 0;
    }
    """

    def __init__(
        self,
        section: render.Section,
        in_session: bool,
        now: float,
        unread: bool,
        neutral_timing: bool,
    ) -> None:
        super().__init__()
        self._section = section
        self._in_session = in_session
        self.now = now
        self.unread = unread
        self.neutral_timing = neutral_timing

    def _header(self, width: int) -> Text:
        return brief_detail.header(
            self._section,
            self._in_session,
            self.now,
            width,
            self.unread,
            self.neutral_timing,
        )

    def render(self) -> Text:
        return self._header(self.size.width)

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        return len(self._header(width).wrap(self.app.console, width)) if width else 0


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


class _BriefTable(_linked_block(MarkdownTable)):
    def compose(self):
        headers, rows = self._get_headers_and_rows()
        self._headers, self._rows = headers, rows
        yield brief_tables.content(headers, rows)


class _BriefParser(MarkdownIt):
    def __init__(self) -> None:
        super().__init__("gfm-like")

    def validateLink(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() == "file":
            return parsed.netloc in {"", "localhost"} and parsed.path.startswith("/")
        return super().validateLink(url)


class _Markdown(Markdown):
    """Markdown whose links open in their own app, from any block: a heading, paragraph or table cell."""

    def __init__(self, markdown: str | None = None, **kwargs) -> None:
        kwargs.setdefault("parser_factory", _BriefParser)
        super().__init__(markdown, **kwargs)

    def get_block_class(self, block_name: str) -> type[MarkdownBlock]:
        return (
            _BriefTable
            if block_name == "table_open"
            else _linked_block(super().get_block_class(block_name))
        )

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


class BriefView(scroll_position.StableScroll):
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
    /* Darker text on a light theme. :light also outranks Markdown's own light
       rule for the quote. Before the mid-turn rule, which has the same
       specificity and must still win. */
    BriefView MarkdownBlock:light {{
        link-color: {utils.LINK_COLOR_LIGHT};
        link-color-hover: {utils.LINK_COLOR_LIGHT};
    }}
    BriefView MarkdownBlockQuote:light {{
        border-left: outer {utils.ATTENTION_TEXT_LIGHT};
        color: {utils.ATTENTION_TEXT_LIGHT};
    }}
    BriefView .brief-needs-mid-turn MarkdownBlockQuote {{
        border-left: outer $foreground 30%;
        color: $text-muted;
    }}
    BriefView .brief-terminal-notice {{
        height: auto;
        color: $warning;
        margin-bottom: 1;
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
        height: auto;
        max-height: 4;
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
        neutral_timing: bool = False,
        browsing: bool = False,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._browsing = browsing
        self._mid_turn_working = mid_turn_working
        self._neutral_timing = neutral_timing
        self._roots = roots
        self._rendered_markdown: str | None = None
        self._pr_states = pr.Cache(pr_state)
        self._vaults = vaults
        self._lemons: frozenset[str] = frozenset()
        self._keys = keys
        self._sections: tuple[render.Section, ...] = ()
        self._selected: brief_questions.Choice | None = None
        self._items: tuple[brief_items.Item, ...] = ()
        self._notice = ""
        self._found: target.Target | None = None
        self._unread = False
        self._answers_expanded = False
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
                        (keys.answer_yes, "answer_yes", "Yes, approved"),
                        (keys.more_detail, "more_detail", "More detail"),
                        (keys.answer_archive, "archive_answer(False)", "Archive selected answer"),
                        (keys.answer_archive_all, "archive_answer(True)", "Archive all answers"),
                        (keys.answers_expand, "expand_answers", "Expand archived answers"),
                        ("question_mark", "brief_help", "Brief keys"),
                    )
                    if key
                ),
            ]
        )

    def show(self, found: target.Target, unread: bool = False) -> None:
        self._notice = ""
        self._rendered_markdown = None
        self._selected = None
        self._answers_expanded = False
        self.update_brief(found, unread)
        self.scroll_home(animate=False)

    def notice(self, message: str) -> None:
        self._notice = message
        self.call_later(scroll_position.notice, self, message)

    def _widgets(self, shown: render.View, now: float, unread: bool) -> list[Widget]:
        notice = (
            [Static(self._notice, classes="brief-terminal-notice", markup=False)]
            if self._notice
            else []
        )
        if not shown.sections:
            return [
                *notice,
                _Markdown(
                    links.linkify(render.to_markdown(shown, now), self._vaults, self._lemons)
                ),
            ]

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
                _Card(section, shown.in_session, now, unread, self._neutral_timing),
                *(
                    [
                        _Markdown(
                            links.linkify(
                                "## Executive Summary of Results\n\n" + section.summary,
                                self._vaults,
                            )
                        )
                    ]
                    if section.summary
                    else []
                ),
                *brief_item_content.widgets(
                    section,
                    self._items,
                    self._selected,
                    lambda text: _Markdown(links.linkify(text, self._vaults, self._lemons)),
                ),
                *(
                    [Static(brief_detail.children(section), classes="brief-children")]
                    if section.children
                    else []
                ),
                *(
                    [_Markdown(links.linkify(section.tail, self._vaults, self._lemons))]
                    if section.tail
                    else []
                ),
            )
        ]
        return [
            *notice,
            *top,
            *sections,
            Rule(),
            Static(brief_detail.files(shown), classes="brief-files"),
            *(
                [Static(self._selection_hint(), classes="brief-question-keys")]
                if self._selected
                else []
            ),
        ]

    def _selected_item(self) -> brief_items.Item | None:
        return next((item for item in self._items if item.choice == self._selected), None)

    def _selection_hint(self) -> str:
        item = self._selected_item()
        return brief_items.hint(item, self._keys) if item else ""

    def _needs_markdown(self, section: render.Section) -> str:
        item = self._selected_item()
        selected = (
            item.label if item and item.kind == "need" and item.choice[0] == section.path else ""
        )
        complete = tuple(
            dataclasses.replace(
                need, label=need.label or next(iter(questions.labels(need.text)), need.text)
            )
            for need in brief_items.needs(section)
        )
        return links.linkify(
            render.needs(dataclasses.replace(section, questions=complete), True, selected),
            self._vaults,
            self._lemons,
        )

    def _choices(self) -> list[brief_items.Choice]:
        return [item.choice for item in self._items]

    def _section(self, path: Path) -> render.Section | None:
        return next((s for s in self._sections if s.path == path), None)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        item = self._selected_item()
        if action == "question":
            return bool(self._items)
        if action in {"answer", "answer_yes", "more_detail"}:
            return bool(item and item.kind == "need")
        if action == "archive_answer":
            return bool(item and item.kind == "answer")

        return True

    def _select_item(self, choice: brief_items.Choice, scroll: bool = False) -> None:
        self._selected = choice
        self.focus()
        for widget in self.query(ItemView):
            selected = widget.item.choice == choice
            widget.select(selected)
            if selected and scroll:
                widget.query_one(".item-title").scroll_visible(animate=False)
        for hint in self.query(".brief-question-keys").results(Static):
            hint.update(self._selection_hint())

    def action_question(self, by: int) -> None:
        choice = brief_questions.step(self._choices(), self._selected, by)
        if choice:
            self._select_item(choice, scroll=True)

    def on_item_view_chosen(self, event: ItemView.Chosen) -> None:
        if event.item.choice not in self._choices():
            return

        self._select_item(event.item.choice)
        if event.activate:
            if event.item.kind == "need":
                self.action_answer()
            elif event.item.kind == "answer":
                self.action_archive_answer()
            else:
                self.action_expand_answers()

    def _lemon_name(self, path: Path) -> str:
        section = self._section(path)
        return (section.lemon.name if section and section.lemon else "") or path.stem

    def _send(self, choice: brief_questions.Choice, body: str) -> None:
        if why := brief_questions.send(choice[0], body):
            self.notify(why, title="Not sent", severity="error")
            return

        self.notify(f"Sent to {self._lemon_name(choice[0])}: {choice[1]}")

    def action_answer(self) -> None:
        item = self._selected_item()
        if item is None or item.kind != "need":
            return

        choice = item.choice[0], item.label

        def answered(text: str | None) -> None:
            if text:
                self._send(choice, brief_questions.answer(*choice, text))

        self.app.push_screen(
            brief_questions.AnswerScreen(choice[1], self._lemon_name(choice[0])), answered
        )

    def action_answer_yes(self) -> None:
        if (item := self._selected_item()) and item.kind == "need":
            choice = item.choice[0], item.label
            self._send(choice, brief_questions.answer(*choice, "Yes, approved"))

    def action_more_detail(self) -> None:
        if (item := self._selected_item()) and item.kind == "need":
            self._send((item.choice[0], item.label), questions.more_detail(item.label))

    def action_brief_help(self) -> None:
        self.app.push_screen(
            brief_help.BriefHelpScreen(
                self._keys, self._browsing, self._selection_hint(), wide=self.app.size.width >= 100
            )
        )

    def action_archive_answer(self, all_answers: bool = False) -> None:
        item = self._selected_item()
        if item is None or item.kind != "answer":
            return

        try:
            message = brief_answers.archive(item, all_answers)
        except (OSError, ValueError, store.ChangedUnderneath) as cause:
            self.notify(str(cause), title="Answers not archived", severity="error")
            return

        self.notify(message)
        if self._found:
            self.update_brief(self._found, self._unread)

    def action_expand_answers(self) -> None:
        self._answers_expanded = not self._answers_expanded
        if self._found:
            self.update_brief(self._found, self._unread)

    def update_brief(self, found: target.Target, unread: bool = False) -> None:
        """Redraw *found*, whose inbox row is *unread* or not."""
        self._found, self._unread = found, unread
        now = time.time()
        shown = family.added(render.view(found, now, self._pr_states.get, self._roots))
        shown = _turns(shown, now, self._mid_turn_working)
        with db.connect() as conn:
            self._lemons = identity.known(conn)

        items = brief_items.items(shown.sections, self._answers_expanded)
        rendered = render.to_markdown(shown, now, expanded=True) + repr(items)
        if rendered == self._rendered_markdown:
            for card in self.query(_Card):
                card.now = now
                card.unread = unread
                card.refresh()
            return

        preserve = self._rendered_markdown is not None
        self._rendered_markdown = rendered
        self._sections = shown.sections
        self._items = items
        available = self._choices()
        self._selected = (
            self._selected if self._selected in available else next(iter(available), None)
        )
        self.call_later(scroll_position.replace, self, self._widgets(shown, now, unread), preserve)
