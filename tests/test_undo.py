"""Tests for the inbox undo stack."""

import tempfile
import time
from pathlib import Path

from lemonaid.inbox import db, undo


def _conn(tmpdir: str):
    return db.connect(Path(tmpdir) / "test.db")


def test_undo_archive_restores_per_row_status():
    """Archive collapses mixed statuses; undo must restore each row's own."""
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        first = db.add(
            conn, channel="claude:abc", message="one", switch_source="tmux", upsert=False
        )
        second = db.add(
            conn, channel="claude:abc", message="two", switch_source="tmux", upsert=False
        )
        db.mark_read(conn, second.id)

        entry = undo.capture(conn, "archive", "Archived x", undo.channel_row_ids(conn, first.id))
        db.archive(conn, first.id)
        assert db.get_active(conn) == []

        undo.restore(conn, entry)

        restored = {
            r["id"]: r["status"]
            for r in conn.execute("SELECT id, status FROM notifications").fetchall()
        }
        assert restored == {first.id: "unread", second.id: "read"}


def test_undo_mark_read_restores_unread():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", switch_source="tmux")

        entry = undo.capture(conn, "mark_read", "Marked read x", [n.id])
        db.mark_read(conn, n.id)
        assert db.get(conn, n.id).status == "read"  # type: ignore[union-attr]

        undo.restore(conn, entry)
        after = db.get(conn, n.id)
        assert after is not None
        assert after.is_unread
        assert after.read_at is None


def test_undo_snooze_returns_session_to_inbox():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", switch_source="tmux")

        entry = undo.capture(conn, "snooze", "Snoozed x", undo.channel_row_ids(conn, n.id))
        db.snooze(conn, n.id, time.time() + 3600)
        assert len(db.get_snoozed(conn)) == 1

        undo.restore(conn, entry)
        assert db.get_snoozed(conn) == []
        after = db.get(conn, n.id)
        assert after is not None
        assert after.snooze_until is None


def test_undo_rename_restores_name_and_metadata():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", name="original")

        entry = undo.capture(conn, "rename", "Renamed x", [n.id])
        db.update_name(conn, n.id, "changed")
        assert db.get(conn, n.id).name == "changed"  # type: ignore[union-attr]

        undo.restore(conn, entry)
        after = db.get(conn, n.id)
        assert after is not None
        assert after.name == "original"
        assert "auto_name" not in after.metadata


def test_stack_is_lifo():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", switch_source="tmux")
        stack = undo.Stack()

        stack.push(undo.capture(conn, "first", "first", [n.id]))
        stack.push(undo.capture(conn, "second", "second", [n.id]))

        assert len(stack) == 2
        assert stack.pop().action == "second"  # type: ignore[union-attr]
        assert stack.pop().action == "first"  # type: ignore[union-attr]
        assert stack.pop() is None


def test_stack_is_bounded():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", switch_source="tmux")
        stack = undo.Stack(max_depth=3)

        for i in range(5):
            stack.push(undo.capture(conn, f"a{i}", f"a{i}", [n.id]))

        assert len(stack) == 3
        assert stack.peek().action == "a4"  # type: ignore[union-attr]


def test_stack_ignores_empty_entries():
    """Capturing a nonexistent row yields nothing to undo."""
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        stack = undo.Stack()
        stack.push(undo.capture(conn, "archive", "gone", [9999]))

        assert len(stack) == 0
        assert stack.pop() is None


def test_multi_level_undo_unwinds_in_order():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", switch_source="tmux")
        stack = undo.Stack()

        stack.push(undo.capture(conn, "mark_read", "read", [n.id]))
        db.mark_read(conn, n.id)

        stack.push(undo.capture(conn, "archive", "archived", undo.channel_row_ids(conn, n.id)))
        db.archive(conn, n.id)

        undo.restore(conn, stack.pop())  # type: ignore[arg-type]
        assert db.get(conn, n.id).status == "read"  # type: ignore[union-attr]

        undo.restore(conn, stack.pop())  # type: ignore[arg-type]
        assert db.get(conn, n.id).status == "unread"  # type: ignore[union-attr]
