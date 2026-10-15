"""Hide feedback remains readable when a hidden done lemon stays in the inbox."""

import pytest
from textual.widgets import Footer, Static

from lemonaid.brief import hidden, store

from .test_inbox_hidden import _run, _session


@pytest.mark.parametrize("size", [(40, 30), (120, 20)])
def test_hidden_done_lemon_reports_each_toggle_in_status_line(size):
    row, path = _session("review-example", status="done")
    store.edit(path, lambda text: hidden.with_hidden(text, True))

    async def steps(app, pilot):
        app._select_channel(row.channel)
        await pilot.press("H")
        assert not hidden.is_hidden(path.read_text())
        status = app.query_one("#status", Static)
        assert status.display
        assert not app.query_one(Footer).display
        assert app._hint_timer is None
        assert "Shown" in str(status.render())
        await pilot.press("H")
        assert hidden.is_hidden(path.read_text())
        assert row.channel in app._row_channels()
        app._refresh_notifications()
        message = str(app.query_one("#status", Static).render())
        assert "Hidden" in message
        assert "still visible: done" in message

    _run(steps, size)


@pytest.mark.parametrize("view_key", ["h", "S"])
def test_alternate_view_reports_hide_is_unavailable(view_key):
    _session("worker")

    async def steps(app, pilot):
        await pilot.press(view_key, "H")
        assert app.query_one("#status", Static).display
        assert "exit this view first" in str(app.query_one("#status", Static).render())

    _run(steps)


def test_no_brief_reports_in_status_line():
    _session("bare", has_brief=False)

    async def steps(app, pilot):
        await pilot.press("H")
        app._refresh_notifications()
        assert app.query_one("#status", Static).display
        assert "No attached brief" in str(app.query_one("#status", Static).render())

    _run(steps)


def test_search_input_keeps_uppercase_h_as_text():
    row, path = _session("hello")

    async def steps(app, pilot):
        await pilot.press("/", "H")
        assert not hidden.is_hidden(path.read_text())
        assert app._content.filter_text == "H"

    _run(steps)
