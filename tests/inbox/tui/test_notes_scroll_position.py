import asyncio

import pytest
from textual.app import App
from textual.widgets._markdown import MarkdownParagraph

from lemonaid.inbox.tui.notes import NotesPanel


@pytest.mark.parametrize("prefix", ["Additional notes.\n\n", ""])
def test_notes_edit_keeps_visible_text(tmp_path, prefix):
    path = tmp_path / "notes.md"
    paragraphs = "\n\n".join(f"Note paragraph {i}." for i in range(50))
    path.write_text("Original introduction.\n\n" + paragraphs)

    async def check():
        app = App()
        async with app.run_test(size=(60, 25)) as pilot:
            panel = NotesPanel(path)
            await app.mount(panel)
            panel.reload()
            await pilot.pause()
            paragraph = next(
                p
                for p in panel.query(MarkdownParagraph)
                if p._content.plain == "Note paragraph 15."
            )
            panel.scroll_to(
                y=paragraph.region.y - panel.content_region.y, animate=False, immediate=True
            )
            await pilot.pause()
            before = paragraph.region.y
            path.write_text(prefix + paragraphs)
            panel.reload()
            await pilot.pause()
            await pilot.pause()
            paragraph = next(
                p
                for p in panel.query(MarkdownParagraph)
                if p._content.plain == "Note paragraph 15."
            )
            assert paragraph.region.y == before

    asyncio.run(check())
