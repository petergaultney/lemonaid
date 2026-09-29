from pathlib import Path

from lemonaid.brief import attached, identity
from lemonaid.home import layout
from lemonaid.inbox import db
from lemonaid.messages import store


def old_home_with_work() -> dict[str, Path]:
    """An old home with an attached brief, a pending one, an unread and a read message."""
    old = layout.legacy_dir()
    old.mkdir()
    work = old / "2026-09-01-work.md"
    work.write_text("# work\n\nStatus: working\n")
    waiting = old / "2026-09-02-waiting.md"
    waiting.write_text("# waiting\n\nStatus: working\n")
    with db.connect() as conn:
        db.add(conn, "claude:work", "", metadata={})
        attached.attach(conn, "claude:work", work.resolve())
        lemon_id = identity.ensure(conn, work.resolve())
        attached.attach_pending(conn, "fresh", "2", waiting.resolve(), [])
    inbox = store.inbox_for_id(lemon_id)
    unread = store.send(inbox, "Unread", "tester")
    (inbox / "done").mkdir()
    read = inbox / "done" / "read.md"
    read.write_text("From: tester\n\nRead\n")
    return {"work": work, "waiting": waiting, "unread": unread, "read": read, "inbox": inbox}


def db_paths() -> set[str]:
    with db.connect() as conn:
        return {
            row[0]
            for table in ("session_briefs", "pending_briefs", "lemon_identities")
            for row in conn.execute(f"SELECT path FROM {table}")
        }
