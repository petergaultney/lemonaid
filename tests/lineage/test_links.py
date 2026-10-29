from lemonaid.inbox import db
from lemonaid.lineage import links

from .shared import lemon


def test_live_children_leave_out_archived_sessions_but_keep_their_links():
    parent = lemon("parent")
    gone = lemon("gone", channel="codex:gone")
    read = lemon("read", channel="codex:read")
    pending = lemon("pending")
    with db.connect() as conn:
        for child in (gone, read, pending):
            links.set_parent(conn, child, parent)
        db.archive_channel(conn, "codex:gone", "test")
        conn.execute("UPDATE notifications SET status = 'read' WHERE channel = 'codex:read'")
        assert links.live_children_of(conn, parent) == [read, pending]
        assert links.children_of(conn, parent) == [gone, read, pending]

        db.add(conn, "codex:gone", "back", metadata={})
        assert links.live_children_of(conn, parent) == [gone, read, pending]
