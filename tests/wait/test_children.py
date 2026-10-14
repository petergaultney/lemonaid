from lemonaid.brief import identity
from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.watch import briefs_events

from . import shared


def test_children_keep_the_default_legacy_cursor_between_waiters(tmp_path):
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    parent = briefs / "brief.md"
    parent.write_text(shared.BRIEF)
    child = briefs / "child.md"
    child.write_text("# child\n")
    with db.connect() as conn:
        owner = identity.ensure(conn, parent)
        child_id = identity.ensure(conn, child)
        links.set_parent(conn, child_id, owner)
    briefs_events.open_watch(tmp_path / "cursors" / "briefs", owner, "", 0)
    child.write_text(child.read_text() + "\nStatus: merge\n")
    text = shared.BRIEF + "- `lemonaid watch briefs --children --self --interval .01 --quiet 0`\n"
    sent = []
    _path, _inbox, _root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    try:
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1 and child_id in sent[0] and "merge" in sent[0]
    finally:
        stop.set()
        thread.join(5)
