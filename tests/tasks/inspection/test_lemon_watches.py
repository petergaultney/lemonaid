from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.tasks.inspection import lemon_watches


def test_lineage_lists_a_lemon_and_its_ancestors_with_whether_each_is_live():
    with db.connect() as conn:
        links.set_parent(conn, "Kid.one", "Lead.one")
        links.set_parent(conn, "Lead.one", "Top.hq")

        found = lemon_watches.lineage(conn, "Kid.one", {}, 0.0)

    assert [(f["kind"], f["key"], f["field"], f["value"]) for f in found] == [
        ("lineage", "Kid.one", "chain", "Kid.one Lead.one Top.hq"),
        ("lemon", "Kid.one", "live", "false"),
        ("lemon", "Lead.one", "live", "false"),
        ("lemon", "Top.hq", "live", "false"),
    ]
