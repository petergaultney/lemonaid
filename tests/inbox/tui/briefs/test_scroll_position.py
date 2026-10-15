import asyncio

import pytest
from textual.widgets._markdown import MarkdownParagraph

from lemonaid.config import Config
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.briefs.brief_popup import BriefPopup
from lemonaid.inbox.tui.briefs.brief_view import BriefView

from ..shared import lemons, until


@pytest.mark.parametrize("popup", [False, True])
@pytest.mark.parametrize(
    "change", ["status", "needs", "body", "shrink", "notice", "consecutive", "refresh", "reorder"]
)
def test_refresh_keeps_visible_brief_text(monkeypatch, tmp_path, change, popup):
    _, state = lemons(monkeypatch, tmp_path, 1)
    path = state["targets"][0].attached[0]
    paragraphs = "\n\n".join(f"Paragraph {i} with enough words to read." for i in range(70))
    source = "# Work\n\nStatus: blocked\n\n## Now\n\n{prefix}\n\n" + paragraphs
    prefix = "\n\n".join(f"Intro {i}" for i in range(15))
    path.write_text(source.format(prefix=prefix))

    async def check():
        app = BriefPopup(state["targets"][0], Config()) if popup else LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(60, 25)) as pilot:
            if not popup:
                await pilot.press("b")
                await until(pilot, lambda: app._brief_target is not None)
            await pilot.pause()
            await pilot.pause()  # The popup mounts Markdown children after its initial refresh.
            view = app.query_one(BriefView)
            assert "Work" in view.query_one("_Card").render().plain
            paragraph = next(
                p
                for p in view.query(MarkdownParagraph)
                if p._content.plain.startswith("Paragraph 25 ")
            )
            view.scroll_to_widget(paragraph, top=True, animate=False, immediate=True)
            await pilot.pause()
            assert paragraph.region.y == view.content_region.y
            old_y = paragraph.region.y
            old_scroll = view.scroll_y
            updated = source.format(prefix=prefix)
            if change == "status":
                updated = updated.replace("Status: blocked", "Status: merge")
            elif change == "needs":
                updated = updated.replace(
                    "## Now", "## Now\n\n### Needs Sam\n\n- Please review the update."
                )
            elif change == "body":
                updated = updated.replace("Paragraph 1 ", "A new paragraph.\n\nParagraph 1 ")
            elif change == "reorder":
                paragraph25 = "Paragraph 25 with enough words to read."
                updated = updated.replace(paragraph25, "").replace(
                    "Paragraph 10 ", paragraph25 + "\n\nParagraph 10 "
                )
            elif change == "shrink":
                updated = source.format(prefix="Intro shortened.")
            path.write_text(updated)
            if change == "refresh" and not popup:
                app.action_refresh()
            elif change == "notice":
                view.notice("The terminal is unavailable.")
            else:
                view.update_brief(state["targets"][0])
                if change == "consecutive":
                    path.write_text(
                        updated.replace("Paragraph 1 ", "Inserted text.\n\nParagraph 1 ")
                    )
                    view.update_brief(state["targets"][0])
            await pilot.pause()
            await pilot.pause()
            paragraph = next(
                p
                for p in view.query(MarkdownParagraph)
                if p._content.plain.startswith("Paragraph 25 ")
            )
            assert paragraph.region.y == old_y
            if change == "status":
                assert view.scroll_y == old_scroll
            scrolled = view.scroll_y
            await pilot.press("pagedown")
            await pilot.pause()
            assert view.scroll_y > scrolled

    asyncio.run(check())
