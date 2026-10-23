"""A session with no brief is grouped by its channel and drawn in its group."""

from lemonaid import groups
from lemonaid.inbox import db, view


def test_a_briefless_session_joins_a_group_by_channel():
    with db.connect() as conn:
        db.add(conn, "claude:6dd09c59", "hi", name="experiment")
        edit = groups.editing.add(conn, "experiments", "claude:6dd09c59", "experiment")

        assert edit.group and edit.group.members == ("claude:6dd09c59",)
        assert view._memberships(conn) == {"claude:6dd09c59": ("experiments",)}
