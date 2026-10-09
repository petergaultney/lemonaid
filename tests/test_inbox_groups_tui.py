"""Groups in `lma`: a header line per group, collapsed with Enter or Tab, moved with the pin-move keys."""

import asyncio
import itertools
import time

import pytest
from textual.widgets import DataTable

from lemonaid import groups
from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db, pins
from lemonaid.inbox.tui.app import LemonaidApp

_ids = itertools.count(900)


def _session(conn, name: str, status: str, *, unread: bool = False) -> str:
    """A session with an attached brief at *status*. Returns its Lemon-ID."""
    channel = f"claude:{name}"
    n = db.add(
        conn,
        channel,
        "a message",
        name,
        {"tty": f"/dev/ttys{next(_ids)}", "cwd": "/tmp", "session_id": f"s{next(_ids)}"},
    )
    conn.execute(
        "UPDATE notifications SET switch_source = 'tmux', status = ?, created_at = ? WHERE id = ?",
        ("unread" if unread else "read", time.time(), n.id),
    )
    conn.commit()
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: {status}\n\n## Now\n")
    attached.attach(conn, channel, path)
    return identity.ensure(conn, path)


@pytest.fixture(autouse=True)
def _keep_sessions(monkeypatch):
    """The test tmux has none of these ttys, so the watcher would archive every row."""
    monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)


@pytest.fixture
def inbox():
    with db.connect() as conn:
        _session(conn, "loose", "working")
        work = groups.store.create(conn, "Work")
        groups.store.add(
            conn,
            work,
            [_session(conn, "lead", "working"), _session(conn, "stuck", "blocked", unread=True)],
        )
        groups.store.create(conn, "Later")


def _keys(app) -> list[str]:
    table = app.query_one("#main_table", DataTable)
    return [str(key.value) for key in table.rows]


def _run(steps, size=(120, 40)):
    async def run():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def _channels(app) -> list[str]:
    return app._row_channels()


@pytest.mark.usefixtures("inbox")
def test_groups_sit_at_the_top_of_their_most_pressing_rows_band():
    async def steps(app, pilot):
        return _channels(app), _keys(app)

    channels, keys = _run(steps)

    assert channels == ["", "claude:stuck", "claude:lead", "claude:loose", ""]
    assert keys[0].startswith("group:") and keys[4].startswith("group:")


@pytest.mark.usefixtures("inbox")
def test_enter_on_a_header_collapses_the_group_and_keeps_the_cursor_there():
    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        table.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        collapsed = _channels(app), table.cursor_coordinate.row
        await pilot.press("enter")
        await pilot.pause()
        return collapsed, _channels(app)

    (collapsed, cursor), reopened = _run(steps)

    assert collapsed == ["", "claude:loose", ""]
    assert cursor == 0
    assert reopened == ["", "claude:stuck", "claude:lead", "claude:loose", ""]
    with db.connect() as conn:
        assert not groups.store.find(conn, "Work").collapsed


@pytest.mark.usefixtures("inbox")
def test_tab_on_a_lemon_collapses_its_group_around_it_until_the_cursor_leaves():
    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        table.move_cursor(row=2)
        await pilot.press("tab")
        await pilot.pause()
        kept = _channels(app), table.cursor_coordinate.row
        table.move_cursor(row=2)
        await pilot.pause()
        app._refresh_notifications()
        await pilot.pause()
        return kept, _channels(app)

    (kept, cursor), left = _run(steps)

    assert kept == ["", "claude:lead", "claude:loose", ""]
    assert cursor == 1
    assert left == ["", "claude:loose", ""]
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
        reopened = _channels(app), app._row_channels()[table.cursor_coordinate.row]
        table.move_cursor(row=3)
        await pilot.press("tab")
        await pilot.pause()
        return reopened, _channels(app)

    (reopened, on), outside = _run(steps)

    assert reopened == ["", "claude:stuck", "claude:lead", "claude:loose", ""]
    assert on == "claude:lead"
    assert outside == reopened


@pytest.mark.usefixtures("inbox")
def test_the_pin_move_keys_reorder_groups_from_a_header():
    with db.connect() as conn:
        groups.store.add(
            conn, groups.store.find(conn, "Later"), [_session(conn, "also", "blocked")]
        )

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        table.move_cursor(row=0)
        await pilot.press(app.config.tui.keybindings.move_pin_down)
        await pilot.pause()
        return _channels(app)

    assert _run(steps) == ["", "claude:also", "", "claude:stuck", "claude:lead", "claude:loose"]
    with db.connect() as conn:
        assert [g.name for g in groups.store.all_groups(conn)] == ["Later", "Work"]


@pytest.mark.usefixtures("inbox")
def test_row_actions_on_a_header_do_nothing():
    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        table.move_cursor(row=0)
        await pilot.press(app.config.tui.keybindings.mark_read[0])
        await pilot.pause()
        return _channels(app)

    assert _run(steps) == ["", "claude:stuck", "claude:lead", "claude:loose", ""]


@pytest.mark.usefixtures("inbox")
def test_jump_digits_count_lemons_not_headers(monkeypatch):
    switched: list[str] = []
    monkeypatch.setattr(
        LemonaidApp, "_switch_to_notification", lambda self, n: switched.append(n.channel)
    )

    async def steps(app, pilot):
        await pilot.press("2")
        await pilot.pause()

    _run(steps)

    assert switched == ["claude:lead"]


def _cursor_key(app) -> str:
    return app._raw_row_key(app.query_one("#main_table", DataTable))


def _add_row_above(app):
    with db.connect() as conn:
        _session(conn, "newcomer", "working")
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

    before, after = _run(steps)

    assert "@" in before and after == before


@pytest.mark.usefixtures("inbox")
def test_the_cursor_stays_on_a_header_when_rows_above_it_change():
    async def steps(app, pilot):
        app.query_one("#main_table", DataTable).move_cursor(row=4)
        before = _cursor_key(app)
        _add_row_above(app)
        await pilot.pause()
        return before, _cursor_key(app)

    before, after = _run(steps)

    assert before.startswith("group:") and after == before


@pytest.mark.usefixtures("inbox")
def test_staying_on_unread_lands_on_the_unread_lemon_below_a_header():
    async def steps(app, pilot):
        app.query_one("#main_table", DataTable).move_cursor(row=0)
        with db.connect() as conn:
            _session(conn, "quiet", "working")
        app._refresh_notifications(stay_on_unread=True)
        await pilot.pause()
        return app._row_channels()[app.query_one("#main_table", DataTable).cursor_coordinate.row]

    assert _run(steps) == "claude:stuck"


@pytest.mark.usefixtures("inbox")
def test_a_group_does_not_move_past_a_group_in_another_band():
    async def steps(app, pilot):
        app.query_one("#main_table", DataTable).move_cursor(row=0)
        await pilot.press(app.config.tui.keybindings.move_pin_down)
        await pilot.pause()
        return _channels(app)

    assert _run(steps) == ["", "claude:stuck", "claude:lead", "claude:loose", ""]
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

    assert _run(steps) == (True, False)


@pytest.mark.usefixtures("inbox")
def test_cards_in_an_open_group_carry_its_rail_and_others_do_not():
    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        return {
            str(key.value): table.get_row_at(row)[0].plain for row, key in enumerate(table.rows)
        }

    cards = _run(steps, size=(44, 60))

    grouped = [text for key, text in cards.items() if "@" in key]
    loose = [text for key, text in cards.items() if key.isdigit()]
    assert grouped and all(line.startswith("▌") for text in grouped for line in text.split("\n"))
    assert loose and not any("▌" in text for text in loose)
