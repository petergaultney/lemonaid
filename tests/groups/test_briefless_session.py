"""A session with no brief is grouped by its channel and drawn in its group."""

from lemonaid import groups
from lemonaid.inbox import db, view


def test_a_briefless_session_joins_a_group_by_channel():
    with db.connect() as conn:
        db.add(conn, "claude:6dd09c59", "hi", name="experiment")
        edit = groups.editing.add(conn, "experiments", "claude:6dd09c59", "experiment")

        assert edit.group and edit.group.members == ("claude:6dd09c59",)
        assert view._memberships(conn) == {"claude:6dd09c59": ("experiments",)}


def test_a_channel_membership_moves_to_the_brief_id_once_it_has_one():
    with db.connect() as conn:
        db.add(conn, "claude:6dd09c59", "hi")
        groups.editing.add(conn, "experiments", "claude:6dd09c59", "experiment")
        group = groups.store.find(conn, "experiments")
        groups.store.rekey(conn, "claude:6dd09c59", "Foo.bar")

        assert groups.store.find(conn, "experiments").members == ("Foo.bar",)
        assert view._memberships(conn) == {}
        assert group.members == ("claude:6dd09c59",)
