"""Groups in `lma`: a header line per group, collapsed with Enter or Tab, moved with the pin-move keys."""

import os
from pathlib import Path

import pytest
from textual.widgets import DataTable

from lemonaid import groups
from lemonaid.grove.source import inbox_keys
from lemonaid.inbox import db, pins
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.tables import row_keys

from .shared import channels, keep_sessions, run, session  # noqa: F401


@pytest.fixture
def inbox():
    Path(os.environ["LEMONAID_CONFIG"]).write_text("[inbox]\nungrouped_first = false\n")
    with db.connect() as conn:
        session(conn, "loose", "working")
        work = groups.store.create(conn, "Work")
        groups.store.add(
            conn,
            work,
            [session(conn, "lead", "working"), session(conn, "stuck", "blocked", unread=True)],
        )
        groups.store.create(conn, "Later")  # empty, so not drawn


def _keys(app) -> list[str]:
    table = app.query_one("#main_table", DataTable)
    return [str(key.value) for key in table.rows]


@pytest.mark.usefixtures("inbox")
def test_groups_follow_manual_order_before_ungrouped_rows():
    async def steps(app, pilot):
        return channels(app), _keys(app)

    drawn, keys = run(steps)

    assert drawn == ["", "claude:stuck", "claude:lead", "claude:loose"]
    assert keys[0].startswith("group:")


@pytest.mark.usefixtures("inbox")
def test_groups_stay_in_manual_order_even_when_a_later_group_has_more_urgent_rows():
    with db.connect() as conn:
        groups.store.add(conn, groups.store.find(conn, "Later"), [session(conn, "urgent", "alert")])

    async def steps(app, pilot):
        with db.connect() as conn:
            names = [group.name for group in groups.store.all_groups(conn)]
        return names, [key for key in _keys(app) if key.startswith("group:")]

    names, headers = run(steps)

    assert names == ["Work", "Later"]
    assert len(headers) == 2


@pytest.mark.usefixtures("inbox")
def test_enter_on_a_header_collapses_the_group_and_keeps_the_cursor_there():
    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        table.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        collapsed = channels(app), table.cursor_coordinate.row
        await pilot.press("enter")
        await pilot.pause()
        return collapsed, channels(app)

    (collapsed, cursor), reopened = run(steps)

    assert collapsed == ["", "claude:loose"]
    assert cursor == 0
    assert reopened == ["", "claude:stuck", "claude:lead", "claude:loose"]
    with db.connect() as conn:
        assert not groups.store.find(conn, "Work").collapsed


@pytest.mark.usefixtures("inbox")
def test_tab_on_a_lemon_collapses_its_group_around_it_until_the_cursor_leaves():
    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        table.move_cursor(row=2)
        await pilot.press("tab")
        await pilot.pause()
        kept = channels(app), table.cursor_coordinate.row
        table.move_cursor(row=2)
        await pilot.pause()
        app._refresh_notifications()
        await pilot.pause()
        return kept, channels(app)

    (kept, cursor), left = run(steps)

    assert kept == ["", "claude:lead", "claude:loose"]
    assert cursor == 1
    assert left == ["", "claude:loose"]
    with db.connect() as conn:
        assert groups.store.find(conn, "Work").collapsed


@pytest.mark.usefixtures("inbox")
def test_tab_on_a_kept_lemon_opens_its_group_again_and_does_nothing_outside_one():
    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        table.move_cursor(row=2)
        await pilot.press("tab")
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()
        reopened = channels(app), app._row_channels()[table.cursor_coordinate.row]
        table.move_cursor(row=3)
        await pilot.press("tab")
        await pilot.pause()
        return reopened, channels(app)

    (reopened, on), outside = run(steps)

    assert reopened == ["", "claude:stuck", "claude:lead", "claude:loose"]
    assert on == "claude:lead"
    assert outside == reopened


@pytest.mark.usefixtures("inbox")
def test_the_pin_move_keys_reorder_groups_from_a_header():
    with db.connect() as conn:
        groups.store.add(conn, groups.store.find(conn, "Later"), [session(conn, "also", "alert")])

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        table.move_cursor(row=0)
        await pilot.press(app.config.tui.keybindings.move_pin_down)
        await pilot.pause()
        return channels(app)

    assert run(steps) == ["", "claude:also", "", "claude:stuck", "claude:lead", "claude:loose"]
    with db.connect() as conn:
        assert [g.name for g in groups.store.all_groups(conn)] == ["Later", "Work"]


@pytest.mark.usefixtures("inbox")
def test_row_actions_on_a_header_do_nothing():
    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        table.move_cursor(row=0)
        await pilot.press(app.config.tui.keybindings.mark_read[0])
        await pilot.pause()
        return channels(app)

    assert run(steps) == ["", "claude:stuck", "claude:lead", "claude:loose"]


@pytest.mark.usefixtures("inbox")
def test_a_grove_key_names_a_lemon_by_its_group_not_its_row(monkeypatch):
    switched: list[str] = []
    monkeypatch.setattr(
        LemonaidApp, "_switch_to_notification", lambda self, n: switched.append(n.channel)
    )

    async def steps(app, pilot):
        key = inbox_keys.names(app._content.inbox.grove)["claude:lead"]
        assert key.startswith("1")  # Work, the first group drawn
        for character in key:
            await pilot.press(character)
            await pilot.pause()

    run(steps)

    assert switched == ["claude:lead"]


def _cursor_key(app) -> str:
    return row_keys.at_cursor(app.query_one("#main_table", DataTable))


def _add_row_above(app):
    with db.connect() as conn:
        session(conn, "newcomer", "working")
        pins.pin(conn, "claude:newcomer")  # pins in no group come first
    app._refresh_notifications()


@pytest.mark.usefixtures("inbox")
def test_the_cursor_stays_on_a_grouped_lemon_when_rows_above_it_change():
    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        table.move_cursor(row=2)
        before = _cursor_key(app)
        _add_row_above(app)
        await pilot.pause()
        return before, _cursor_key(app)

    before, after = run(steps)

    assert "@" in before and after == before


@pytest.mark.usefixtures("inbox")
def test_the_cursor_stays_on_a_header_when_rows_above_it_change():
    async def steps(app, pilot):
        app.query_one("#main_table", DataTable).move_cursor(row=0)
        before = _cursor_key(app)
        _add_row_above(app)
        await pilot.pause()
        return before, _cursor_key(app)

    before, after = run(steps)

    assert before.startswith("group:") and after == before


@pytest.mark.usefixtures("inbox")
def test_staying_on_unread_lands_on_the_unread_lemon_below_a_header():
    async def steps(app, pilot):
        app.query_one("#main_table", DataTable).move_cursor(row=0)
        with db.connect() as conn:
            session(conn, "quiet", "working")
        app._refresh_notifications(stay_on_unread=True)
        await pilot.pause()
        return app._row_channels()[app.query_one("#main_table", DataTable).cursor_coordinate.row]

    assert run(steps) == "claude:stuck"


@pytest.mark.usefixtures("inbox")
def test_moving_the_last_visible_group_down_does_nothing():
    async def steps(app, pilot):
        app.query_one("#main_table", DataTable).move_cursor(row=0)
        await pilot.press(app.config.tui.keybindings.move_pin_down)
        await pilot.pause()
        return channels(app)

    assert run(steps) == ["", "claude:stuck", "claude:lead", "claude:loose"]
    with db.connect() as conn:
        assert [g.name for g in groups.store.all_groups(conn)] == ["Work", "Later"]


@pytest.mark.usefixtures("inbox")
def test_the_header_under_the_cursor_carries_a_marker_and_loses_it_when_the_cursor_leaves():
    def arrow_is_filled(app) -> bool:
        cell = next(c for c in app.query_one("#main_table", DataTable).get_row_at(0) if c.plain)
        return any(span.start == 0 and " on #" in str(span.style) for span in cell.spans)

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        table.move_cursor(row=0)
        await pilot.pause()
        on = arrow_is_filled(app)
        table.move_cursor(row=1)
        await pilot.pause()
        return on, arrow_is_filled(app)

    assert run(steps) == (True, False)


@pytest.mark.usefixtures("inbox")
def test_cards_in_an_open_group_carry_its_rail_and_others_do_not():
    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        return {
            str(key.value): table.get_row_at(row)[0].plain for row, key in enumerate(table.rows)
        }

    cards = run(steps, size=(44, 60))

    grouped = [text for key, text in cards.items() if "@" in key]
    loose = [text for key, text in cards.items() if key.isdigit()]
    assert grouped and all(
        line.startswith("▌") for text in grouped for line in text.split("\n")[:-1]
    )
    assert grouped[0].split("\n")[-1].startswith("▌")
    assert not grouped[-1].split("\n")[-1].strip()
    assert loose and not any(line.startswith("▌") for text in loose for line in text.split("\n"))
