"""Text in lemonaid's own colours stays readable on a light theme's background.

The attention, running and link colours were chosen for a dark background and
fall to 2:1 contrast or less on white. Under a light theme, text takes darker
ones; fills, a colour behind black or white text, read on either and stay.
"""

import asyncio
from types import SimpleNamespace

import pytest
from rich.console import Console
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Markdown

from lemonaid.brief import colors
from lemonaid.config import Config
from lemonaid.inbox.tui import app, brief_cards, brief_detail, brief_popup, utils
from lemonaid.inbox.tui.brief_cards import CardBrief
from lemonaid.inbox.tui.brief_view import BriefView
from lemonaid.inbox.tui.utils import jump_gutter


@pytest.fixture(autouse=True)
def _dark_after(monkeypatch):
    monkeypatch.setattr(utils, "_light_theme", False)


def _cells(unread: bool = True) -> list[Text]:
    return [
        Text("12:30"),
        Text("●" if unread else ""),
        Text("CC"),
        jump_gutter(0, False) + Text("task"),
        Text("branch"),
        Text("~/work"),
        Text("message"),
    ]


def _colour_of(body: Text, text: str) -> str:
    style = body.get_style_at_offset(Console(color_system="truecolor"), body.plain.index(text))
    return style.color.name


def _contrast_on_white(colour: str) -> float:
    rgb = [int(colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
    return 1.05 / (0.2126 * r + 0.7152 * g + 0.0722 * b + 0.05)


def test_a_dark_theme_keeps_the_original_colours():
    assert utils.unread_marker_style() == f"bold {utils.ATTENTION_COLOR}"
    assert brief_cards.running_text() == brief_cards.RUNNING_TEXT_COLOR


def test_a_light_theme_darkens_text_but_not_fills():
    utils.use_light_theme(True)

    assert utils.attention_text() == utils.ATTENTION_TEXT_LIGHT
    assert brief_cards.running_text() == brief_cards.RUNNING_TEXT_COLOR_LIGHT
    assert brief_cards.STATUS_STYLES["blocked"].bgcolor.name == utils.ATTENTION_COLOR


@pytest.mark.parametrize(
    "colour",
    [
        utils.ATTENTION_TEXT_LIGHT,
        utils.LINK_COLOR_LIGHT,
        brief_cards.RUNNING_TEXT_COLOR_LIGHT,
        *(style.split()[-1] for style in colors._STATE_STYLES_LIGHT.values() if "#" in style),
    ],
)
def test_every_light_text_colour_reads_on_white(colour):
    """4.5:1 is the usual floor for body text."""
    assert _contrast_on_white(colour) >= 4.5


def test_a_cards_needs_line_and_dot_follow_the_theme():
    brief = CardBrief("", "", 0, needs="answer")

    (dark,) = app._as_card(_cells(), 40, gutter_width=2, card_brief=brief, now=60)
    utils.use_light_theme(True)
    (light,) = app._as_card(_cells(), 40, gutter_width=2, card_brief=brief, now=60)

    assert _colour_of(dark, "Needs: answer") == utils.ATTENTION_COLOR
    assert _colour_of(light, "Needs: answer") == utils.ATTENTION_TEXT_LIGHT
    assert _colour_of(light, "●") == utils.ATTENTION_TEXT_LIGHT


def test_a_cards_running_line_follows_the_theme():
    utils.use_light_theme(True)
    brief = CardBrief("running", "", 0, running="deploy in ops:2")

    (body,) = app._as_card(_cells(unread=False), 40, gutter_width=2, card_brief=brief, now=60)

    assert _colour_of(body, "deploy") == brief_cards.RUNNING_TEXT_COLOR_LIGHT


def test_the_status_word_follows_the_theme():
    assert brief_detail._state_style("approve") == "bold #b39ddb"
    utils.use_light_theme(True)
    assert brief_detail._state_style("approve") == "bold #5e35b1"
    assert brief_detail._state_style("nonsense", "dim") == "dim"


def test_a_held_status_age_uses_the_theme_appropriate_text_colour():
    brief = CardBrief("blocked", "", 0, mid_turn=True, held_mid_turn=True)
    dark = brief.age_text(60)
    utils.use_light_theme(True)
    light = brief.age_text(60)
    console = Console(color_system="truecolor")

    assert dark.get_style_at_offset(console, 0).color.name == utils.ATTENTION_COLOR
    assert light.get_style_at_offset(console, 0).color.name == utils.ATTENTION_TEXT_LIGHT


@pytest.mark.parametrize("app_class", [app.LemonaidApp, brief_popup.BriefPopup])
@pytest.mark.parametrize("dark", [True, False])
def test_the_apps_set_text_colours_from_their_theme(app_class, dark):
    fake = SimpleNamespace(current_theme=SimpleNamespace(dark=dark), is_mounted=False)

    app_class.watch_theme(fake, "any")

    assert utils.light_theme() is (not dark)


def _brief_view_colours(theme: str, mid_turn: bool) -> tuple[str, str, str]:
    """(quote text, quote border, link) for a quote and a link in a BriefView under `theme`."""

    class Probe(App):
        def compose(self) -> ComposeResult:
            yield BriefView(None, [], Config().tui.keybindings, False, [])

        async def on_mount(self) -> None:
            self.theme = theme
            box = Vertical(classes="brief-needs-mid-turn" if mid_turn else "")
            await self.query_one(BriefView).mount(box)
            await box.mount(Markdown("> needs an answer\n\n[a link](https://example.com)"))

    async def run() -> tuple[str, str, str]:
        probe = Probe()
        async with probe.run_test() as pilot:
            await pilot.pause()
            quote = probe.query("MarkdownBlockQuote").first()
            paragraph = probe.query("MarkdownParagraph").first()
            return (
                quote.styles.color.hex,
                quote.styles.border_left[1].hex,
                paragraph.styles.link_color.hex,
            )

    return asyncio.run(run())


def test_the_brief_view_darkens_its_quote_and_links_on_a_light_theme():
    assert _brief_view_colours("textual-light", mid_turn=False) == (
        utils.ATTENTION_TEXT_LIGHT.upper(),
        utils.ATTENTION_TEXT_LIGHT.upper(),
        utils.LINK_COLOR_LIGHT.upper(),
    )
    assert _brief_view_colours("textual-dark", mid_turn=False) == (
        utils.ATTENTION_COLOR.upper(),
        utils.ATTENTION_COLOR.upper(),
        utils.LINK_COLOR.upper(),
    )


def test_mid_turn_still_mutes_the_quote_on_a_light_theme():
    """The light rule must not outrank the mid-turn rule, which has the same specificity."""
    text, _border, _link = _brief_view_colours("textual-light", mid_turn=True)

    assert text != utils.ATTENTION_TEXT_LIGHT.upper()
