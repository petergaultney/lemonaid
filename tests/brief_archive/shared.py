import datetime
import os
import time
from pathlib import Path

from lemonaid.brief import attached, identity, store
from lemonaid.inbox import db
from lemonaid.messages import store as messages

DAY = 24 * 60 * 60
LONG_AGO = time.time() - 60 * DAY


def brief(name: str, at: float = LONG_AGO) -> tuple[Path, str]:
    """A brief with a Lemon-ID, created *at*; its file is new whenever *at* is."""
    created = datetime.datetime.fromtimestamp(at).astimezone().isoformat(timespec="seconds")
    path = store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ncreated: {{ at: {created} }}\n---\n# {name}\n\nStatus: done\n\n## Now\n- Finished.\n"
    )
    with db.connect() as conn:
        lemon_id = identity.ensure(conn, path)
    return path.resolve(), lemon_id


def session(path: Path, channel: str, at: float = LONG_AGO, live: bool = False) -> None:
    with db.connect() as conn:
        row = db.add(conn, channel, "", metadata={}, created_at=at)
        attached.attach(conn, channel, path)
        conn.execute("UPDATE session_briefs SET attached_at = ? WHERE channel = ?", (at, channel))
        conn.commit()
        if not live:
            db.archive(conn, row.id)


def message(lemon_id: str, at: float, name: str = "message") -> Path:
    inbox = messages.inbox_for_id(lemon_id)
    inbox.mkdir(parents=True, exist_ok=True)
    sent = inbox / f"20261001T000000000000Z-{name}.md"
    sent.write_text("Hello.")
    for touched in (sent, inbox):
        os.utime(touched, (at, at))
    return sent
