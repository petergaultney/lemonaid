"""The current card's frame occupies existing space, inside its group's rail."""

import asyncio

import pytest
from rich.console import Console
from rich.text import Text
from textual.app import App, ComposeResult

from lemonaid.inbox.tui import utils
from lemonaid.inbox.tui.rows import cards
from lemonaid.inbox.tui.rows.brief_cards import CardBrief
from lemonaid.inbox.tui.tables.table import ClickToActTable
from lemonaid.inbox.tui.utils import HERE_BAR, jump_gutter


@pytest.mark.parametrize("width", [24, 40, 58])
@pytest.mark.parametrize("rail", ["", "#ff0000"])
@pytest.mark.parametrize("status", ["blocked", ""])
@pytest.mark.parametrize("light", [False, True])
def test_frame_preserves_geometry_and_colors(width, rail, status, light, monkeypatch):
    monkeypatch.setattr(utils, "_light_theme", light)
    cells = [Text("12:00"), Text(""), Text("CC"), Text(""), Text(""), Text("~/w"), Text("msg")]
    cells[3] = jump_gutter(0, True) + Text("task")
    (marked,) = cards.as_card(
        cells, width, gutter_width=2, rail=rail, card_brief=CardBrief(status, "", 0)
    )
    cells[3] = jump_gutter(0, False) + Text("task")
    (plain,) = cards.as_card(
        cells, width, gutter_width=2, rail=rail, card_brief=CardBrief(status, "", 0)
    )
    lines = marked.split("\n")
    inset = bool(rail)
    assert len(lines) == len(plain.plain.split("\n"))
    assert marked.plain.index("task") == plain.plain.index("task")
    assert all(line.cell_len == width for line in lines)
    assert all(
        line.plain[inset] == HERE_BAR and line.plain.endswith("\u2590") for line in lines[:-1]
    )
    assert lines[-1].plain[inset:] == "\u2586" * (width - inset)
    console = Console(color_system="truecolor")
    assert lines[-1].get_style_at_offset(console, inset).reverse
    assert not lines[0].get_style_at_offset(console, inset).reverse
    for line in lines:
        assert line.get_style_at_offset(console, inset).color.name == (
            "#1c1c1c" if light else "#f2f2f2"
        )
        assert not line.get_style_at_offset(console, inset).dim
        if rail:
            assert line.plain[0] == HERE_BAR
            assert line.get_style_at_offset(console, 0).color.name == rail


@pytest.mark.parametrize("width", [32, 58])
@pytest.mark.parametrize("position", [0, 1, 2])
def test_rendered_frame_stays_in_its_row_before_a_header(width, position):
    async def render():
        class FrameApp(App):
            def compose(self) -> ComposeResult:
                yield ClickToActTable(cursor_type="row", show_header=False, cell_padding=0)

            def on_mount(self) -> None:
                table = self.query_one(ClickToActTable)
                table.add_column("Card", width=width)
                for index in range(3):
                    cells = [
                        Text("12:00"),
                        Text(""),
                        Text("CC"),
                        jump_gutter(index, index == position) + Text("task"),
                        Text(""),
                        Text("~/w"),
                        Text("message"),
                    ]
                    (card,) = cards.as_card(
                        cells,
                        width,
                        gutter_width=2,
                        rail="#ff0000",
                        card_brief=CardBrief("blocked", "", 0),
                    )
                    table.add_row(card, height=len(card.split("\n")))
                    if index == position:
                        table.add_row(Text("Next group", style="bold underline"), height=1)
                table.focus()

        app = FrameApp()
        async with app.run_test(size=(width + 2, 30)) as pilot:
            await pilot.pause()
            strips = app.screen._compositor.render_strips()
            text = [strip.text for strip in strips]
            bottom = next(i for i, line in enumerate(text) if "\u2586" in line)
            assert "Next group" in text[bottom + 1]
            assert text[bottom].startswith(HERE_BAR + "\u2586" * (width - 1))
            assert text[bottom - 1].startswith(HERE_BAR + HERE_BAR)
            assert text[bottom - 1][width - 1] == "\u2590"
            assert sum("\u2586" in line for line in text) == 1
            bottom_segments = [segment for segment in strips[bottom] if "\u2586" in segment.text]
            assert bottom_segments
            for segment in bottom_segments:
                assert segment.style.reverse
                assert segment.style.color.name == "#f2f2f2"
                assert segment.style.bgcolor is not None

    asyncio.run(render())
