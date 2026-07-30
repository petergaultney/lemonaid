"""Tests for snooze behavior in lemonaid.inbox.db."""

import tempfile
import time
from pathlib import Path

from lemonaid.inbox import db


def _conn(tmpdir: str):
    return db.connect(Path(tmpdir) / "test.db")


def test_snoozed_session_leaves_active_list():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="Waiting", switch_source="tmux")
        db.snooze(conn, n.id, time.time() + 3600)

        assert db.get_active(conn) == []
        snoozed = db.get_snoozed(conn)
        assert len(snoozed) == 1
        assert snoozed[0].channel == "claude:abc"
        assert snoozed[0].is_snoozed


def test_snoozed_session_absent_from_history():
    """A snoozed session belongs to the snoozed view, not history."""
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="Waiting", switch_source="tmux")
        db.snooze(conn, n.id, time.time() + 3600)

        assert db.get_history(conn) == []


def test_wake_expired_restores_previous_status():
    """An unread session comes back unread; a read one comes back read."""
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        unread = db.add(conn, channel="claude:unread", message="x", switch_source="tmux")
        read = db.add(conn, channel="claude:read", message="y", switch_source="tmux")
        db.mark_read(conn, read.id)

        past = time.time() - 1
        db.snooze(conn, unread.id, past)
        db.snooze(conn, read.id, past)

        woken = db.wake_expired(conn)
        assert set(woken) == {"claude:unread", "claude:read"}

        statuses = {n.channel: n.status for n in db.get_active(conn)}
        assert statuses == {"claude:unread": "unread", "claude:read": "read"}


def test_wake_expired_leaves_future_snoozes_alone():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", switch_source="tmux")
        db.snooze(conn, n.id, time.time() + 3600)

        assert db.wake_expired(conn) == []
        assert len(db.get_snoozed(conn)) == 1


def test_wake_expired_clears_snooze_columns():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", switch_source="tmux")
        db.snooze(conn, n.id, time.time() - 1)
        db.wake_expired(conn)

        woken = db.get(conn, n.id)
        assert woken is not None
        assert woken.snooze_until is None
        assert woken.snooze_prev_status is None


def test_new_attention_cancels_snooze():
    """Fresh agent output overrides an active snooze."""
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", switch_source="tmux")
        db.mark_read(conn, n.id)
        db.snooze(conn, n.id, time.time() + 3600)

        assert db.mark_unread_for_channel(conn, "claude:abc") == 1

        assert db.get_snoozed(conn) == []
        active = db.get_active(conn)
        assert len(active) == 1
        assert active[0].is_unread
        assert active[0].snooze_until is None


def test_new_notification_cancels_snooze():
    """An upsert from a notify hook also clears the snooze."""
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", switch_source="tmux")
        db.snooze(conn, n.id, time.time() + 3600)

        db.add(conn, channel="claude:abc", message="Waiting again", switch_source="tmux")

        assert db.get_snoozed(conn) == []
        refreshed = db.get(conn, n.id)
        assert refreshed is not None
        assert refreshed.is_unread
        assert refreshed.snooze_until is None


def test_unsnooze_is_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", switch_source="tmux")
        db.snooze(conn, n.id, time.time() + 3600)

        assert db.unsnooze(conn, "claude:abc") == 1
        assert db.unsnooze(conn, "claude:abc") == 0
        assert len(db.get_active(conn)) == 1


def test_snooze_covers_whole_channel():
    """Snooze applies to every row on the channel, like archive does."""
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        first = db.add(
            conn, channel="claude:abc", message="one", switch_source="tmux", upsert=False
        )
        db.add(conn, channel="claude:abc", message="two", switch_source="tmux", upsert=False)

        db.snooze(conn, first.id, time.time() + 3600)

        rows = conn.execute(
            "SELECT status FROM notifications WHERE channel = 'claude:abc'"
        ).fetchall()
        assert [r["status"] for r in rows] == ["snoozed", "snoozed"]
