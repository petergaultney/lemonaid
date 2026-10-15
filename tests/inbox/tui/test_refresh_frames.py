import asyncio

import pytest
from textual.app import App
from textual.widgets import Markdown
from textual.widgets._markdown import MarkdownParagraph

from lemonaid.config import Config
from lemonaid.inbox.tui import scroll_position
from lemonaid.inbox.tui.briefs.brief_popup import BriefPopup
from lemonaid.inbox.tui.briefs.brief_view import BriefView
from lemonaid.inbox.tui.tables.scroll_position import StableTable

from .shared import lemons


@pytest.mark.parametrize("surface", ["table", "brief", "notes", "popup", "notice"])
def test_refresh_never_paints_an_unanchored_frame(monkeypatch, tmp_path, surface):
    _, state = lemons(monkeypatch, tmp_path, 1)

    async def check():
        source = "\n\n".join(f"Paragraph {i}." for i in range(80))
        path = state["targets"][0].attached[0]
        path.write_text("# Work\n\n## Now\n\n" + source)
        app = BriefPopup(state["targets"][0], Config()) if surface == "popup" else App()
        async with app.run_test(size=(60, 20)) as pilot:
            if surface == "popup":
                view = app.query_one(BriefView)
            elif surface == "table":
                view = StableTable()
                await app.mount(view)
                view.add_column("Text")
                for i in range(80):
                    view.add_row(str(i), key=str(i))
            else:
                view = scroll_position.StableScroll()
                await app.mount(view)
                await view.mount(Markdown(source))
            await pilot.pause()
            await pilot.pause()
            view.scroll_to(y=40, animate=False, immediate=True)
            await pilot.pause()

            def anchor_y():
                if surface == "table":
                    return view.get_row_index("40") - view.scroll_y
                paragraph = next(
                    (
                        p
                        for p in view.query(MarkdownParagraph)
                        if p._content.plain == "Paragraph 20."
                    ),
                    None,
                )
                return paragraph.region.y if paragraph else None

            before = anchor_y()
            assert before is not None
            if surface != "table":
                assert view.content_region.y <= before < view.content_region.bottom
            frames = []
            display = app._display

            def record(screen, renderable):
                if renderable is not None and not app._batch_count:
                    frames.append(anchor_y())
                display(screen, renderable)

            monkeypatch.setattr(app, "_display", record)
            if surface == "table":
                with view.preserve_scroll():
                    view.clear()
                    for i in range(-3, 80):
                        view.add_row(str(i), key=str(i))
            elif surface == "popup":
                path.write_text("# Work\n\n## Now\n\nAdded above.\n\n" + source)
                view.update_brief(state["targets"][0])
            elif surface == "notice":
                await scroll_position.notice(view, "The terminal is unavailable.")
            elif surface == "brief":
                await scroll_position.replace(view, [Markdown("Added above.\n\n" + source)], True)
            else:
                scroll_position.update(view, view.query_one(Markdown), "Added above.\n\n" + source)
            await pilot.pause()
            await pilot.pause()
            assert frames
            assert frames == [before] * len(frames)

    asyncio.run(check())
