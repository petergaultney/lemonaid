from lemonaid import groups
from lemonaid.brief import reroll, store
from lemonaid.inbox import db
from tests.lineage.shared import lemon


def test_membership_follows_a_rerolled_lemon_id():
    old = lemon("one")
    with db.connect() as conn:
        group = groups.store.create(conn, "G")
        groups.store.add(conn, group, [old])

        new = reroll.reroll(conn, store.briefs_dir() / "one.md").new_id

        assert groups.store.find(conn, "G").members == (new,)
