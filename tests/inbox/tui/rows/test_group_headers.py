"""Group fills survive the table's cursor and hover styles, including cell padding."""

import asyncio

import pytest
from textual.app import App, ComposeResult

from lemonaid import groups
from lemonaid.inbox import sections
from lemonaid.inbox.tui.live import group_headers
from lemonaid.inbox.tui.rows import table_rows
from lemonaid.inbox.tui.tables.table import ClickToActTable


@pytest.mark.parametrize("theme", ["textual-dark", "textual-light"])
@pytest.mark.parametrize("card_width", [0, 35])
@pytest.mark.parametrize(
    "color, marker_background",
    [
        ("#75bca0", "#000000"),
        ("#ffffff", "#000000"),
        ("#000000", "#ffffff"),
        ("#00cc00", "#000000"),
    ],
)
def test_selected_and_hovered_header_keeps_its_group_fill(
    theme, card_width, color, marker_background, monkeypatch
):
    monkeypatch.delenv("NO_COLOR", raising=False)

    async def render():
        class HeaderApp(App):
            CSS = """
            ClickToActTable > .datatable--cursor { background: #345678; }
            ClickToActTable > .datatable--hover { background: #654321; }
            """

            def compose(self) -> ComposeResult:
                yield ClickToActTable(
                    cursor_type="row", show_header=False, cell_padding=0 if card_width else 1
                )

            def on_mount(self) -> None:
                self.theme = theme
                table = self.query_one(ClickToActTable)
                table.add_column("Group", width=35)
                if not card_width:
                    table.add_column("Padding", width=15)
                header = sections.Header(
                    groups.store.Group(
                        1,
                        "Kitchen projects with a very long descriptive group name",
                        0,
                        (),
                        color=color,
                    ),
                    0,
                    (("alert", 2), ("done", 12)),
                )
                cells = group_headers.cells(
                    header, card_width, len(table.columns), 0, selected=True, name_width=35
                )
                table_rows.sync_rows(
                    table,
                    [(header.key, cells)],
                    card_width=card_width,
                    headers={header.key: (cells, group_headers.background(header))},
                )
                table.focus()

        app = HeaderApp()
        async with app.run_test(size=(card_width or 60, 8)) as pilot:
            await pilot.pause()
            await pilot.hover(ClickToActTable, offset=(10, 0))
            await pilot.pause()
            strip = next(s for s in app.screen._compositor.render_strips() if "Kitchen" in s.text)
            painted = [
                (segment.text, segment.style.bgcolor.name)
                for segment in strip
                if segment.text.strip()
            ]
            assert "#345678" not in [bg for _, bg in painted]
            assert "#654321" not in [bg for _, bg in painted]
            arrow = next(segment for segment in strip if "▾" in segment.text)
            name = next(segment for segment in strip if "Kitchen" in segment.text)
            assert arrow.style.bgcolor.name == marker_background
            assert name.style.color.name == marker_background
            assert "  !2  d12 " in strip.text
            assert "(0)" in strip.text
            assert any(bg == color for _, bg in painted)
            assert all(
                segment.style.bgcolor.name in {color, marker_background, "#c62828", "#285995"}
                for segment in strip
                if segment.text and segment.style.meta.get("row") == 0
            )

    asyncio.run(render())
