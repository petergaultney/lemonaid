"""`U` swaps the inbox for the usage view; the header shows the overall pace."""

import asyncio
import time

from textual.widgets import DataTable
from textual.widgets._header import HeaderTitle

from lemonaid import config as config_mod
from lemonaid.inbox.tui import app as app_mod
from lemonaid.inbox.tui import usage_view
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.usage import samples

from .test_brief_navigation import _until


def _half_used(monkeypatch) -> None:
    cfg = config_mod.load_config()
    monkeypatch.setattr(app_mod, "load_config", lambda: cfg)
    now = int(time.time())
    week_minutes = 10080
    half_over = now + week_minutes * 30  # half of the window's seconds
    current = {
        "claude seven_day": samples.Sample(60, half_over, week_minutes),
        "codex primary": samples.Sample(10, half_over, week_minutes),
    }
    monkeypatch.setattr(usage_view, "read_samples", lambda: current)


def test_header_shows_pace_after_the_subtitle(monkeypatch):
    _half_used(monkeypatch)

    async def check() -> None:
        app = LemonaidApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await _until(pilot, lambda: "usage" in str(app.query_one(HeaderTitle).render()))
            assert str(app.query_one(HeaderTitle).render()).rstrip().endswith("usage 0.70x")

    asyncio.run(check())


def test_u_opens_the_usage_table_and_back(monkeypatch):
    _half_used(monkeypatch)

    async def check() -> None:
        app = LemonaidApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.press("U")
            table = app.query_one("#usage_table", DataTable)
            await _until(pilot, lambda: table.row_count == 2)
            assert table.display and not app.query_one("#main_table").display

            await pilot.press("q")
            await _until(pilot, lambda: not table.display and app.query_one("#main_table").display)

    asyncio.run(check())
