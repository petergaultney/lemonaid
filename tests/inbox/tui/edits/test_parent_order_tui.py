import pytest

from lemonaid import groups
from lemonaid.inbox import db
from lemonaid.lineage import links

from .shared import channels, keep_sessions, run, session  # noqa: F401


@pytest.mark.parametrize("parent_in_group", [True, False])
def test_inbox_draws_visible_parent_before_children_in_the_same_group(parent_in_group):
    with db.connect() as conn:
        group = groups.store.create(conn, "Work")
        parent = session(conn, "parent", "")
        second = session(conn, "second", "blocked")
        unrelated = session(conn, "unrelated", "running")
        first = session(conn, "first", "alert")
        links.set_parent(conn, first, parent)
        links.set_parent(conn, second, parent)
        groups.store.add(conn, group, [first, unrelated, second])
        groups.store.add(
            conn, group if parent_in_group else groups.store.create(conn, "Other"), [parent]
        )

    async def steps(app, pilot):
        return channels(app)

    drawn = run(steps)
    assert drawn == (
        ["", "claude:parent", "claude:first", "claude:second", "claude:unrelated"]
        if parent_in_group
        else ["", "claude:first", "claude:second", "claude:unrelated", "", "claude:parent"]
    )
