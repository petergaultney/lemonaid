"""Action checks stay independent of the number of blocks in an open brief."""

import asyncio

from textual.css import match

from lemonaid.brief import target
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.briefs.brief_pane import BriefPane
from lemonaid.inbox.tui.watchers import watcher_hooks


def test_action_checks_do_not_scan_the_brief_body(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher_hooks, "start", lambda *args: None)
    path = tmp_path / "brief.md"
    path.write_text("# Task\n\n## Now\n\n" + "A paragraph.\n\n" * 300)
    found = target.Target([path], [], None, [], "Task")
    checks = 0
    original = match._check_selectors

    def counted(*args, **kwargs):
        nonlocal checks
        checks += 1
        return original(*args, **kwargs)

    async def run():
        nonlocal checks
        app = LemonaidApp()
        assert app._brief_target is None
        async with app.run_test(size=(68, 40)) as pilot:
            app._set_brief_view(found)
            await pilot.pause()
            assert len(app.query_one(BriefPane).walk_children()) > 300
            monkeypatch.setattr(match, "_check_selectors", counted)
            checks = 0
            assert app.check_action("quit", ()) is True
            assert app.check_action("archive", ()) is False
            assert checks < 100
            monkeypatch.setattr(match, "_check_selectors", original)
            app._set_brief_view(None)
            assert app._brief_target is None
            assert app.check_action("archive", ()) is True

    asyncio.run(run())
