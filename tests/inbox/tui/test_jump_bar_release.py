"""The jump bar never holds the inbox: keys and the mouse it has no use for pass through."""

from textual import events
from textual.widgets import DataTable

from lemonaid.inbox.tui.app import LemonaidApp

from .test_jump_by_number import _active, _run


def _three_lemons(count: int = 3) -> None:
    for i in range(count):
        _active(f"bar-release-{i}")


def _is_open(app) -> bool:
    return app._jump_bar is not None


def test_one_escape_closes_the_bar_with_a_tree_typed():
    _three_lemons()

    async def steps(app, pilot):
        letter = app._content.inbox.grove.arrangement.trees[("", "/tmp")].letter
        await pilot.press("0", letter.upper())
        await pilot.pause()
        typed = _is_open(app)
        await pilot.press("escape")
        await pilot.pause()
        return typed, _is_open(app)

    assert _run(steps) == (True, False)


def test_a_navigation_key_closes_the_bar_and_moves_the_list():
    _three_lemons()

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        before = table.cursor_row
        await pilot.press("0")
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        return _is_open(app), before, table.cursor_row

    is_open, before, after = _run(steps)
    assert not is_open
    assert after == before + 1


def test_keys_typed_faster_than_the_bar_closes_all_reach_the_list():
    _three_lemons(6)

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        before = table.cursor_row
        await pilot.press("0")
        await pilot.pause()
        for _ in range(3):  # queued together, as a fast typist's keys arrive
            app.post_message(events.Key("down", None))
        await pilot.pause()
        await pilot.pause()
        return _is_open(app), len(app.screen_stack), before, table.cursor_row

    is_open, depth, before, after = _run(steps)
    assert (is_open, depth) == (False, 1)
    assert after == before + 3


def test_the_click_that_closes_the_bar_acts_on_its_row(monkeypatch):
    _three_lemons(4)
    chosen: list[str] = []
    monkeypatch.setattr(LemonaidApp, "_activate_lemon", lambda self, n: chosen.append(n.channel))

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        await pilot.press("0")
        await pilot.pause()
        x, y = table.region.x + 15, table.region.y + 3
        for kind in (events.MouseDown, events.MouseUp):  # as the terminal's click arrives
            app.post_message(kind(None, x, y, 0, 0, 1, False, False, False, screen_x=x, screen_y=y))
        await pilot.pause()
        await pilot.pause()
        return _is_open(app), table.cursor_row

    assert _run(steps, monkeypatch=monkeypatch) == (False, 2)
    assert len(chosen) == 1


def test_the_mouse_wheel_closes_the_bar_and_reaches_the_list(monkeypatch):
    _three_lemons()
    seen: list[events.MouseScrollDown] = []
    monkeypatch.setattr(DataTable, "_on_mouse_scroll_down", lambda self, event: seen.append(event))

    async def steps(app, pilot):
        region = app.query_one("#main_table", DataTable).region
        await pilot.press("0")
        await pilot.pause()
        wheel = events.MouseScrollDown(
            None, 2, 2, 0, 0, 1, False, False, False,
            screen_x=region.x + 2, screen_y=region.y + 2,
        )  # fmt: skip
        app.post_message(wheel)  # as the terminal's wheel arrives
        await pilot.pause()
        await pilot.pause()
        return _is_open(app)

    assert not _run(steps)
    assert seen
