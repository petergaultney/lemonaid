"""`C` in `lma` saves a group's color, drawn at once, and `z` undoes it."""

import pytest
from textual.widgets import DataTable

from lemonaid import groups
from lemonaid.inbox import db

from .shared import channels, keep_sessions, run, session  # noqa: F401


@pytest.fixture
def work() -> str:
    with db.connect() as conn:
        loose = session(conn, "loose", "done")
        groups.store.add(conn, groups.store.create(conn, "Work"), [loose])
    return "claude:loose"


def _drawn(app) -> str:
    [header] = app._content.inbox.headers.values()
    return header.group.color


def _saved() -> str:
    with db.connect() as conn:
        return groups.store.find(conn, "Work").saved_color


def test_c_on_a_header_saves_and_draws_the_color_and_z_undoes_it(work):
    async def steps(app, pilot):
        await pilot.pause()
        app.query_one("#main_table", DataTable).move_cursor(row=channels(app).index(""))
        await pilot.press("C")
        await pilot.pause()
        await pilot.press("ctrl+u", *"teal", "enter")
        await pilot.pause()
        drawn, saved = _drawn(app), _saved()
        await pilot.press("z")
        await pilot.pause()
        return drawn, saved, _drawn(app)

    drawn, saved, undone = run(steps)

    assert (drawn, saved) == ("#008080", "#008080")
    assert undone != "#008080"
    assert _saved() == ""


def test_c_on_a_lemon_colors_the_group_it_is_drawn_in(work):
    async def steps(app, pilot):
        await pilot.pause()
        app.query_one("#main_table", DataTable).move_cursor(row=channels(app).index(work))
        await pilot.press("C")
        await pilot.pause()
        await pilot.press("ctrl+u", *"#112233", "enter")
        await pilot.pause()

    run(steps)

    assert _saved() == "#112233"


def test_a_color_saved_from_the_cli_is_drawn_without_a_restart(work):
    async def steps(app, pilot):
        await pilot.pause()
        with db.connect() as conn:
            groups.color.save(conn, groups.store.find(conn, "Work"), "#112233")
        await pilot.pause(1)
        return _drawn(app)

    assert run(steps) == "#112233"


def test_a_color_that_isnt_one_is_refused_and_nothing_is_saved(work):
    async def steps(app, pilot):
        await pilot.pause()
        app.query_one("#main_table", DataTable).move_cursor(row=channels(app).index(""))
        await pilot.press("C")
        await pilot.pause()
        await pilot.press("ctrl+u", *"nope", "enter")
        await pilot.pause()

    run(steps)

    assert _saved() == ""


def test_the_saved_color_by_another_name_changes_nothing_to_undo(work):
    with db.connect() as conn:
        groups.color.save(conn, groups.store.find(conn, "Work"), "#008080")

    async def steps(app, pilot):
        await pilot.pause()
        app.query_one("#main_table", DataTable).move_cursor(row=channels(app).index(""))
        await pilot.press("C")
        await pilot.pause()
        await pilot.press("ctrl+u", *"teal", "enter")
        await pilot.pause()
        return len(app._content.inbox.undo_stack)

    assert run(steps) == 0
