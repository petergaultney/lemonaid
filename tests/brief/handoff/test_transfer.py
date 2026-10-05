"""Brief and manual state transfer between backend channels."""

import time

from lemonaid.brief import attached, handoff_state, handoff_transfer
from lemonaid.inbox import db, pins

from .shared import requested


def test_transfer_and_resume_keep_each_backend_session(setup):
    conn, path = setup
    row = requested(conn, path)
    assert (
        handoff_state.request(
            conn, path, "claude:old", "codex", "work", "2", "@2", "%2", "claude", time.time() + 600
        )["token"]
        == row["token"]
    )
    assert handoff_state.typed_message(conn, "claude:old", f"lemonaid handoff ready {row['token']}")

    conn.execute(
        "UPDATE brief_handoffs SET target = ?, phase = 'launched' WHERE token = ?",
        ("codex:new", row["token"]),
    )
    conn.commit()
    assert handoff_state.typed_message(conn, "codex:new", f"lemonaid handoff accept {row['token']}")
    db.snooze(conn, db.get_by_channel(conn, "claude:old", unread_only=False).id, time.time() + 300)
    handoff_transfer.transfer(conn, row["token"])
    handoff_transfer.transfer(conn, row["token"])

    old = db.get_by_channel(conn, "claude:old", unread_only=False)
    new = db.get_by_channel(conn, "codex:new", unread_only=False)
    assert old.metadata["session_id"] == "old"
    assert new.metadata["session_id"] == "new"
    assert new.message == "New text"
    assert new.name == "Manual name"
    assert new.status == "snoozed"
    assert old.status == "archived"
    assert attached.by_channel(conn, ["codex:new"])["codex:new"] == path
    assert pins.pinned_positions(conn) == {"codex:new": 10.0}

    db.register_working(
        conn, channel="claude:old", message="Resumed", metadata={"session_id": "old"}
    )
    assert handoff_transfer.reclaim(conn, "claude:old")
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path
    assert pins.pinned_positions(conn) == {"claude:old": 10.0}
    assert db.get_by_channel(conn, "codex:new", unread_only=False).status != "archived"
    assert (
        conn.execute("SELECT lemon_id FROM lemon_aliases").fetchone()[0]
        == conn.execute(
            "SELECT lemon_id FROM lemon_identities WHERE path = ?", (str(path),)
        ).fetchone()[0]
    )
    assert conn.execute("SELECT parent_id FROM lemon_parents").fetchone()[0] == "parent.Other"


def test_codex_to_claude_transfer(setup):
    conn, path = setup
    attached.attach(conn, "codex:new", path)
    row = handoff_state.request(
        conn, path, "codex:new", "claude", "work", "3", "@3", "%3", "codex", time.time() + 600
    )
    path.write_text(
        path.read_text().replace("Old notes.", f"For Claude.\nHandoff-Ready: {row['token']}")
    )
    assert handoff_state.typed_message(conn, "codex:new", f"lemonaid handoff ready {row['token']}")
    conn.execute(
        "UPDATE brief_handoffs SET target = ?, phase = 'launched' WHERE token = ?",
        ("claude:old", row["token"]),
    )
    conn.commit()
    assert handoff_state.typed_message(
        conn, "claude:old", f"lemonaid handoff accept {row['token']}"
    )
    handoff_transfer.transfer(conn, row["token"])
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path
    assert db.get_by_channel(conn, "claude:old", unread_only=False).metadata["session_id"] == "old"
    assert db.get_by_channel(conn, "codex:new", unread_only=False).status == "archived"
