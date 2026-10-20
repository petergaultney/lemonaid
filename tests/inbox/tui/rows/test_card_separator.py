"""Card separators clear the cursor fill and end a group's rail."""

import asyncio

import pytest
from rich.text import Text
from textual.app import App, ComposeResult

from lemonaid.inbox.tui.rows import table_rows
from lemonaid.inbox.tui.tables.table import ClickToActTable
from lemonaid.inbox.tui.utils import HERE_BAR, jump_gutter


@pytest.mark.parametrize("width", [32, 58])
@pytest.mark.parametrize("marked", ["a", "b", "c"])
def test_separators_use_normal_background_and_only_continue_rails_within_a_group(
    width, marked, monkeypatch
):
    monkeypatch.delenv("NO_COLOR", raising=False)

    async def render():
        class SeparatorApp(App):
            CSS = """
            ClickToActTable { background: #101820; }
            ClickToActTable > .datatable--cursor { background: #345678; }
            """

            def compose(self) -> ComposeResult:
                yield ClickToActTable(cursor_type="row", show_header=False, cell_padding=0)

            def on_mount(self) -> None:
                table = self.query_one(ClickToActTable)
                table.add_column("Card", width=width)
                rows = [
                    (
                        key,
                        [
                            Text("12:00"),
                            Text(""),
                            Text("CC"),
                            jump_gutter(index, key == marked) + Text(f"task-{key}"),
                            Text(""),
                            Text("~/w"),
                            Text(f"message-{key}"),
                        ],
                    )
                    for index, key in enumerate("abc")
                ]
                rows.insert(2, ("header", [Text("Next group")]))
                table_rows.sync_rows(
                    table,
                    rows,
                    card_width=width,
                    gutter_width=2,
                    headers={"header": ([Text("Next group")], None)},
                    rails_by_row={"a": "#ff0000", "b": "#ff0000", "c": "#00ff00"},
                )
                table.move_cursor(row=table.get_row_index(marked))
                table.focus()

        app = SeparatorApp()
        async with app.run_test(size=(width + 2, 24)) as pilot:
            await pilot.pause()
            table = app.query_one(ClickToActTable)
            assert [row.height for row in table.ordered_rows] == [4, 4, 1, 4]
            strips = app.screen._compositor.render_strips()
            for key in "abc":
                message = next(
                    i for i, strip in enumerate(strips) if f"message-{key}" in strip.text
                )
                bottom = strips[message + 1]
                assert bottom.text.startswith(HERE_BAR if key == "a" else " ")
                assert all(
                    segment.style.bgcolor == table.rich_style.bgcolor
                    for segment in bottom
                    if segment.text
                ), [(segment.text, str(segment.style)) for segment in bottom]
                if key == marked:
                    assert "\u2586" in bottom.text
                    content = next(
                        segment for segment in strips[message] if f"message-{key}" in segment.text
                    )
                    assert content.style.bgcolor.name == "#345678"
                assert strips[message].text.startswith(HERE_BAR)
            assert "Next group" in strips[8].text

    asyncio.run(render())
