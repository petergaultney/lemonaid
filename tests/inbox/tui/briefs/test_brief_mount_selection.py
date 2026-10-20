"""Selection stays safe while a brief's children are being mounted."""

import asyncio

from textual.widgets import Markdown, Static

from lemonaid.brief import target
from lemonaid.config import Config
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.briefs.brief_item_widget import ItemView
from lemonaid.inbox.tui.briefs.brief_items import Item
from lemonaid.inbox.tui.briefs.brief_pane import BriefPane
from lemonaid.inbox.tui.briefs.brief_popup import BriefPopup
from lemonaid.inbox.tui.briefs.brief_view import BriefView

from ..shared import lemons


def test_rapid_selection(monkeypatch, tmp_path):
    _, state = lemons(monkeypatch, tmp_path, 2)
    for found in state["targets"]:
        found.attached[0].write_text(
            "# Work\n\nStatus: blocked\n\n## Now\n\n### Needs Sam\n\n- choice: decide\n\n## Questions\n\n### choice\n\nChoose it.\n"
        )

    async def check():
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            pane = app.query_one(BriefPane)
            for index in range(60):
                pane.set_view(state["targets"][index % 2])
                app._refresh_notifications()
                app.set_timer(0.0001, lambda: pane.run_action("question(1)"))
                await pilot.pause(0.001)
                pane.set_view(None)

    asyncio.run(check())


def test_select_before_mount_preserves_the_title(tmp_path):
    item = Item((tmp_path / "task.md", "need:choice"), "need", "Choose", "Choose one")
    widget = ItemView(item, item.body, Markdown, False)
    widget.select(True)

    async def check():
        app = BriefPopup(target.Target([], [], None, [], "Work"), Config())
        async with app.run_test() as pilot:
            await pilot.pause()
            await app.query_one(BriefView).mount(widget)
            assert widget.has_class("-selected")
            assert str(widget.query_one(".item-title", Static).render()) == "▶ Needs: Choose"
            widget.select(False)
            assert not widget.has_class("-selected")
            assert str(widget.query_one(".item-title", Static).render()) == "Needs: Choose"

    asyncio.run(check())
