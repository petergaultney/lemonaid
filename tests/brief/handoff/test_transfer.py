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


def test_handoff_keeps_snooze_set_before_outgoing_turn(setup):
    conn, path = setup
    old = db.get_by_channel(conn, "claude:old", unread_only=False)
    until = time.time() + 300
    db.snooze(conn, old.id, until)
    row = requested(conn, path)
    db.add(
        conn,
        "claude:old",
        "Turn complete",
        metadata={"session_id": "old"},
        ends_turn=True,
    )
    still_old = db.get_by_channel(conn, "claude:old", unread_only=False)
    assert still_old.status == "snoozed"
    assert still_old.snooze_until == until
    assert still_old.snooze_prev_status == "unread"
    assert not still_old.snooze_through_turns

    handoff_state.acknowledge(conn, row["token"], "claude:old", "ready")
    conn.execute(
        "UPDATE brief_handoffs SET target = ?, phase = 'launched' WHERE token = ?",
        ("codex:new", row["token"]),
    )
    conn.commit()
    handoff_state.acknowledge(conn, row["token"], "codex:new", "accept")
    handoff_transfer.transfer(conn, row["token"])
    new = db.get_by_channel(conn, "codex:new", unread_only=False)
    assert (new.status, new.snooze_until, new.snooze_prev_status, new.snooze_through_turns) == (
        "snoozed",
        until,
        "unread",
        False,
    )


def test_removed_and_expired_snoozes_are_not_transferred(setup):
    conn, path = setup
    old = db.get_by_channel(conn, "claude:old", unread_only=False)
    db.snooze(conn, old.id, time.time() + 300)
    row = requested(conn, path)
    db.unsnooze(conn, "claude:old")
    db.add(conn, "claude:old", "Turn complete", ends_turn=True)
    assert db.get_by_channel(conn, "claude:old", unread_only=False).status != "snoozed"

    db.snooze(conn, old.id, time.time() - 1)
    handoff_state.acknowledge(conn, row["token"], "claude:old", "ready")
    conn.execute(
        "UPDATE brief_handoffs SET target = ?, phase = 'launched' WHERE token = ?",
        ("codex:new", row["token"]),
    )
    conn.commit()
    handoff_state.acknowledge(conn, row["token"], "codex:new", "accept")
    handoff_transfer.transfer(conn, row["token"])
    assert db.get_by_channel(conn, "codex:new", unread_only=False).status != "snoozed"


def test_transfer_carries_backend_title_until_target_has_one(setup):
    conn, path = setup
    old = db.get_by_channel(conn, "claude:old", unread_only=False)
    db.update_name(conn, old.id, None)
    db.refresh_auto_name(conn, old.id, "Protostellar sandboxing architecture", "claude_index")
    new = db.get_by_channel(conn, "codex:new", unread_only=False)
    db.refresh_auto_name(conn, new.id, "sandboxing", "environment")
    row = requested(conn, path)
    handoff_state.acknowledge(conn, row["token"], "claude:old", "ready")
    conn.execute(
        "UPDATE brief_handoffs SET target = ?, phase = 'launched' WHERE token = ?",
        ("codex:new", row["token"]),
    )
    conn.commit()
    handoff_state.acknowledge(conn, row["token"], "codex:new", "accept")
    handoff_transfer.transfer(conn, row["token"])

    inherited = db.get_by_channel(conn, "codex:new", unread_only=False)
    assert inherited.name == "Protostellar sandboxing architecture"
    db.add(conn, "codex:new", "Later", name="sandboxing", metadata={"name_source": "environment"})
    assert db.get_by_channel(conn, "codex:new", unread_only=False).name == inherited.name
    db.add(
        conn,
        "codex:new",
        "Later",
        name="New backend title",
        metadata={"name_source": "codex_title"},
    )
    assert db.get_by_channel(conn, "codex:new", unread_only=False).name == "New backend title"


def test_transfer_keeps_meaningful_target_title(setup):
    conn, path = setup
    old = db.get_by_channel(conn, "claude:old", unread_only=False)
    db.update_name(conn, old.id, None)
    db.refresh_auto_name(conn, old.id, "Old backend title", "claude_index")
    new = db.get_by_channel(conn, "codex:new", unread_only=False)
    db.refresh_auto_name(conn, new.id, "New backend title", "codex_title")
    row = requested(conn, path)
    handoff_state.acknowledge(conn, row["token"], "claude:old", "ready")
    conn.execute(
        "UPDATE brief_handoffs SET target = ?, phase = 'launched' WHERE token = ?",
        ("codex:new", row["token"]),
    )
    conn.commit()
    handoff_state.acknowledge(conn, row["token"], "codex:new", "accept")
    handoff_transfer.transfer(conn, row["token"])
    assert db.get_by_channel(conn, "codex:new", unread_only=False).name == "New backend title"
