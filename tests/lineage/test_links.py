from lemonaid import brief
from lemonaid.brief import archive
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
        assert links.live_children_of(conn, parent, archive.attic_dir()) == [read, pending]
        assert links.children_of(conn, parent) == [gone, read, pending]

        db.add(conn, "codex:gone", "back", metadata={})
        assert links.live_children_of(conn, parent, archive.attic_dir()) == [gone, read, pending]


def test_a_child_archived_from_the_attic_is_not_live_but_one_waiting_to_start_is():
    parent = lemon("parent")
    archived = lemon("archived")
    waiting = lemon("waiting")
    with db.connect() as conn:
        for child in (archived, waiting):
            links.set_parent(conn, child, parent)
        archive.archive(conn, brief.lemon.brief_of(conn, archived), 0.0)

        assert links.live_children_of(conn, parent, archive.attic_dir()) == [waiting]
        assert links.children_of(conn, parent) == [archived, waiting]
