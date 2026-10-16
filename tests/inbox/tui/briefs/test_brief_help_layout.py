"""Brief help inherits the inbox help's actual styles and panel layout."""

import asyncio

import pytest
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Label, Static

from lemonaid.config import KeybindingsConfig
from lemonaid.inbox.tui.briefs.brief_help import BriefHelpScreen
from lemonaid.inbox.tui.help_screen import HelpScreen

from .test_brief_answer_keys import _brief, _popup


@pytest.mark.parametrize("width", [35, 80, 130])
def test_brief_help_keeps_the_shared_panel_styles_and_columns(width):
    async def run():
        app = _popup(_brief())
        async with app.run_test(size=(width, 40)) as pilot:
            await pilot.pause()
            await pilot.press("?")
            screen = app.screen
            assert isinstance(screen, BriefHelpScreen)
            panel = screen.query_one("BriefHelpScreen > Vertical", Vertical)
            assert panel.styles.padding.top == 1 and panel.styles.padding.left == 2
            assert panel.styles.border_left[0] == "thick"
            assert screen.query_one(".title", Label).styles.text_align == "center"
            assert screen.query_one(".section", Label).styles.padding.top == 1
            assert screen.query_one(".section", Label).styles.text_style.bold
            title = screen.query_one(".title")
            context = screen.query_one(".context")
            scroll = screen.query_one(VerticalScroll)
            assert "selected" in str(context.render()).lower()
            assert title.region.bottom <= context.region.y
            assert context.region.bottom <= scroll.region.y
            assert bool(screen.query(Horizontal)) == (width >= 100)
            key_row = next(
                w for w in screen.query(Static) if "Archive the selected" in str(w.render())
            )
            assert key_row.render().get_style_at_offset(0).bold
            assert panel.region.width <= (width if width >= 100 else 72)
            assert panel.region.height <= 40

    asyncio.run(run())


def test_inbox_and_brief_help_share_frame_and_heading_styles():
    async def run():
        app = _popup(_brief())
        async with app.run_test(size=(80, 40)) as pilot:
            styles = []
            for screen in (
                HelpScreen(KeybindingsConfig()),
                BriefHelpScreen(KeybindingsConfig(), True),
            ):
                app.push_screen(screen)
                await pilot.pause()
                panel = screen.query_one("Vertical", Vertical)
                title = screen.query_one(".title", Label)
                styles.append(
                    (
                        panel.styles.padding,
                        panel.styles.border_left,
                        title.styles.text_align,
                        title.styles.text_style,
                    )
                )
                await pilot.press("escape")
            assert styles[0] == styles[1]

    asyncio.run(run())


def test_wide_brief_help_can_scroll_in_a_short_pane():
    async def run():
        app = _popup(_brief())
        async with app.run_test(size=(130, 18)) as pilot:
            await pilot.pause()
            await pilot.press("?")
            scroll = app.screen.query_one(VerticalScroll)
            assert scroll.max_scroll_y > 0
            await pilot.press("end")
            await pilot.pause()
            assert scroll.scroll_y > 0
            title = app.screen.query_one(".title")
            context = app.screen.query_one(".context")
            assert title.region.bottom <= context.region.y
            assert context.region.bottom <= scroll.region.y
            assert app.screen.query_one(".hint").region.bottom <= 18

    asyncio.run(run())
