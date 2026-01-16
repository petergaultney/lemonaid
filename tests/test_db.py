"""Tests for lemonaid.inbox.db module."""

import tempfile
from pathlib import Path

from lemonaid.inbox import db


def test_connect_creates_schema():
    """connect() should create the notifications table."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            # Check table exists
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='notifications'"
            ).fetchone()
            assert result is not None


def test_add_creates_notification():
    """add() should create a new notification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            notification = db.add(
                conn,
                channel="test:123",
                title="Test notification",
                message="Test message",
                metadata={"key": "value"},
            )

            assert notification.id > 0
            assert notification.channel == "test:123"
            assert notification.title == "Test notification"
            assert notification.message == "Test message"
            assert notification.metadata == {"key": "value"}
            assert notification.status == "unread"


def test_add_upsert_updates_existing():
    """add() with upsert=True should update existing unread notification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            # Create first notification
            n1 = db.add(conn, channel="test:123", title="First")
            first_id = n1.id

            # Create second with same channel - should update
            n2 = db.add(conn, channel="test:123", title="Second")

            assert n2.id == first_id  # Same ID
            assert n2.title == "Second"  # Updated title

            # Only one notification should exist
            unread = db.get_unread(conn)
            assert len(unread) == 1
            assert unread[0].title == "Second"


def test_add_upsert_creates_new_after_read():
    """add() should create new notification if previous was read."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            # Create and mark as read
            n1 = db.add(conn, channel="test:123", title="First")
            db.mark_read(conn, n1.id)

            # Create second - should be new since first is read
            n2 = db.add(conn, channel="test:123", title="Second")

            assert n2.id != n1.id  # Different ID


def test_get_unread_returns_only_unread():
    """get_unread() should only return unread notifications."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            n1 = db.add(conn, channel="test:1", title="Unread")
            n2 = db.add(conn, channel="test:2", title="Will be read")
            db.mark_read(conn, n2.id)

            unread = db.get_unread(conn)
            assert len(unread) == 1
            assert unread[0].id == n1.id


def test_mark_read():
    """mark_read() should update status and read_at."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            n = db.add(conn, channel="test:123", title="Test")
            assert not n.is_read

            db.mark_read(conn, n.id)

            updated = db.get(conn, n.id)
            assert updated is not None
            assert updated.is_read
            assert updated.read_at is not None


def test_mark_all_read_for_channel():
    """mark_all_read_for_channel() should mark all matching as read."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            db.add(conn, channel="test:aaa", title="A1", upsert=False)
            db.add(conn, channel="test:aaa", title="A2", upsert=False)
            db.add(conn, channel="test:bbb", title="B1")

            count = db.mark_all_read_for_channel(conn, "test:aaa")
            assert count == 2

            unread = db.get_unread(conn)
            assert len(unread) == 1
            assert unread[0].channel == "test:bbb"


def test_notification_from_row():
    """Notification.from_row() should correctly parse database row."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            db.add(
                conn,
                channel="test:123",
                title="Test",
                metadata={"tty": "/dev/ttys001"},
            )

            row = conn.execute("SELECT * FROM notifications WHERE id = 1").fetchone()
            notification = db.Notification.from_row(row)

            assert notification.channel == "test:123"
            assert notification.metadata == {"tty": "/dev/ttys001"}
