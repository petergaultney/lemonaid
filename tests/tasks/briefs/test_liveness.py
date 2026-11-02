from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.tasks.briefs import liveness


def test_a_brief_with_no_lemon_attached_isnt_live():
    with db.connect() as conn:
        assert not liveness.live(conn, "Nobody.here")


def test_nearest_walks_up_to_the_first_live_ancestor(dead):
    with db.connect() as conn:
        links.set_parent(conn, "Kid.one", "Lead.one")
        links.set_parent(conn, "Lead.one", "Top.hq")
        dead.update({"Kid.one", "Lead.one"})

        assert liveness.nearest(conn, "Kid.one") == "Top.hq"
        dead.add("Top.hq")
        assert liveness.nearest(conn, "Kid.one") == ""
