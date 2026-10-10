"""Editing groups in `lma`: G groups a lemon's tree, + and - add and remove, r renames, z undoes."""

import pytest
from textual.widgets import DataTable

from lemonaid import groups, lineage
from lemonaid.inbox import db
from tests.test_inbox_groups_tui import _channels, _keep_sessions, _run, _session  # noqa: F401


@pytest.fixture
def inbox() -> dict[str, str]:
    with db.connect() as conn:
        ids = {
            name: _session(conn, name, status)
            for name, status in (("lead", "working"), ("child", "working"), ("loose", "done"))
        }
        lineage.links.set_parent(conn, ids["child"], ids["lead"])
        groups.store.add(conn, groups.store.create(conn, "Work"), [ids["loose"]])
    return ids


def _cursor_on(app, channel: str) -> None:
    app.query_one("#main_table", DataTable).move_cursor(row=_channels(app).index(channel))


def _under_cursor(app) -> str:
    return _channels(app)[app.query_one("#main_table", DataTable).cursor_coordinate.row]


def _group_id(name: str) -> int:
    with db.connect() as conn:
        return groups.store.find(conn, name).group_id


def _groups() -> dict[str, tuple[str, ...]]:
    with db.connect() as conn:
        return {g.name: g.members for g in groups.store.all_groups(conn)}


def test_g_asks_for_a_name_then_groups_a_lemon_with_its_children(inbox):
    async def steps(app, pilot):
        await pilot.pause()
        _cursor_on(app, "claude:lead")
        await pilot.press("G")
        await pilot.pause()
        asked = _groups()
        await pilot.press("ctrl+u", *"Inbox", "enter")
        await pilot.pause()
        return asked, _channels(app)[-3:], _under_cursor(app)

    asked, drawn, cursor = _run(steps)

    assert asked == {"Work": (inbox["loose"],)}
    assert _groups()["Inbox"] == (inbox["lead"], inbox["child"])
    assert drawn[0] == "" and sorted(drawn[1:]) == ["claude:child", "claude:lead"]
    assert cursor == "claude:lead"


def test_escape_at_gs_name_makes_no_group(inbox):
    async def steps(app, pilot):
        await pilot.pause()
        _cursor_on(app, "claude:lead")
        await pilot.press("G")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    _run(steps)

    assert _groups() == {"Work": (inbox["loose"],)}


def test_plus_puts_a_lemon_in_a_picked_group_and_z_takes_it_out(inbox):
    async def steps(app, pilot):
        await pilot.pause()
        _cursor_on(app, "claude:lead")
        await pilot.press("plus")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        added = _groups(), _under_cursor(app)
        await pilot.press("z")
        await pilot.pause()
        return added

    added, cursor = _run(steps)

    assert added["Work"] == (inbox["loose"], inbox["lead"])
    assert cursor == "claude:lead"
    assert _groups()["Work"] == (inbox["loose"],)


def test_plus_with_a_new_name_makes_the_group(inbox):
    async def steps(app, pilot):
        await pilot.pause()
        _cursor_on(app, "claude:child")
        await pilot.press("plus")
        await pilot.pause()
        await pilot.press(*"Review", "down", "enter")
        await pilot.pause()

    _run(steps)

    assert _groups()["Review"] == (inbox["child"],)


def test_minus_takes_a_lemon_out_of_its_group_and_on_a_header_deletes_it(inbox):
    async def steps(app, pilot):
        await pilot.pause()
        _cursor_on(app, "claude:loose")
        await pilot.press("minus")
        await pilot.pause()
        removed = _groups()
        assert _under_cursor(app) == "claude:loose"
        app.query_one("#main_table", DataTable).move_cursor(row=_channels(app).index(""))
        await pilot.press("minus")
        await pilot.pause()
        deleted = _groups()
        await pilot.press("z")
        await pilot.pause()
        return removed, deleted

    removed, deleted = _run(steps)

    assert removed == {"Work": ()}
    assert deleted == {}
    assert _groups() == {"Work": ()}


def test_r_on_a_header_renames_the_group(inbox):
    async def steps(app, pilot):
        await pilot.pause()
        app.query_one("#main_table", DataTable).move_cursor(row=_channels(app).index(""))
        await pilot.press("r")
        await pilot.pause()
        await pilot.press("ctrl+u", *"Done work", "enter")
        await pilot.pause()

    _run(steps)

    assert _groups() == {"Done work": (inbox["loose"],)}


def test_an_undo_refused_for_a_taken_name_can_be_tried_again(inbox):
    async def steps(app, pilot):
        with db.connect() as conn:
            groups.store.create(conn, "Other")  # so a new group can't reuse Work's ID
        app._refresh_notifications()
        await pilot.pause()
        app.query_one("#main_table", DataTable).move_cursor(row=_channels(app).index(""))
        await pilot.press("minus")
        await pilot.pause()
        with db.connect() as conn:
            groups.store.create(conn, "Work")
        await pilot.press("z")
        await pilot.pause()
        refused = _groups()
        with db.connect() as conn:
            groups.store.delete(conn, groups.store.find(conn, "Work"))
        await pilot.press("z")
        await pilot.pause()
        return refused

    refused = _run(steps)

    assert refused == {"Other": (), "Work": ()}
    assert _groups() == {"Other": (), "Work": (inbox["loose"],)}


def test_the_cursor_follows_a_lemon_into_a_collapsed_group_and_out_to_another(inbox):
    async def steps(app, pilot):
        with db.connect() as conn:
            groups.store.add(conn, groups.store.create(conn, "Other"), [inbox["lead"]])
            groups.arrangement.set_collapsed(conn, groups.store.find(conn, "Work"), True)
        app._refresh_notifications()
        await pilot.pause()
        _cursor_on(app, "claude:lead")
        await pilot.press("plus")
        await pilot.pause()
        await pilot.press(*"Work", "enter")
        await pilot.pause()
        into = _under_cursor(app), app._raw_row_key(app.query_one("#main_table", DataTable))
        await pilot.press("minus")
        await pilot.pause()
        return into, _under_cursor(app)

    (into, key), out = _run(steps)

    assert into == "claude:lead" and key.endswith(f"@{_group_id('Work')}")
    assert out == "claude:lead"
    assert _groups()["Other"] == (inbox["lead"],)
