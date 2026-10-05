"""Shared isolated inbox and brief for handoff tests."""

import time

import pytest

from lemonaid.brief import attached, handoff_state, store
from lemonaid.inbox import db, pins


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "handoff.md"
    lemon_id = store.new_lemon_id(path)
    path.write_text(
        f"# Handoff\n\nStatus: working\n\nLemon-ID: {lemon_id}\n\n"
        "## Now\n\n### Next\n\n- Continue.\n\n## Handoff\n\nOld notes.\n"
    )
    with db.connect(tmp_path / "inbox.db") as conn:
        conn.execute("INSERT INTO lemon_identities VALUES (?, ?)", (str(path), lemon_id))
        conn.execute("INSERT INTO lemon_aliases VALUES (?, ?)", ("old-id.Alias", lemon_id))
        conn.execute(
            "INSERT INTO lemon_parents VALUES (?, ?, ?)", (lemon_id, "parent.Other", time.time())
        )
        db.add(
            conn,
            channel="claude:old",
            message="Old text",
            name="Old backend",
            metadata={"session_id": "old", "cwd": str(tmp_path)},
            status="read",
        )
        db.add(
            conn,
            channel="codex:new",
            message="New text",
            name="New backend",
            metadata={"session_id": "new", "cwd": str(tmp_path)},
            status="read",
        )
        attached.attach(conn, "claude:old", path)
        db.update_name(
            conn, db.get_by_channel(conn, "claude:old", unread_only=False).id, "Manual name"
        )
        pins.pin(conn, "claude:old")
        conn.execute(
            "INSERT INTO session_emoji VALUES (?, ?, ?)", ("claude:old", "🍋", time.time())
        )
        conn.commit()
        yield conn, path


def requested(conn, path):
    row = handoff_state.request(
        conn, path, "claude:old", "codex", "work", "2", "@2", "%2", "claude", time.time() + 600
    )
    path.write_text(
        path.read_text().replace("Old notes.", f"New notes.\nHandoff-Ready: {row['token']}")
    )
    return row
