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
                message="Test notification",
                name="test-session",
                metadata={"key": "value"},
            )

            assert notification.id > 0
            assert notification.channel == "test:123"
            assert notification.message == "Test notification"
            assert notification.name == "test-session"
            assert notification.metadata == {"key": "value"}
            assert notification.status == "unread"

            # you can add already-archived notifications, too
            t = 42
            notification = db.add(
                conn,
                channel="test:456",
                message="Test notification",
                created_at=t,
                status="archived",
            )

            assert notification.created_at == t
            assert notification.status == "archived"


def test_add_upsert_updates_existing():
    """add() with upsert=True should update existing unread notification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            # Create first notification
            n1 = db.add(conn, channel="test:123", message="First")
            first_id = n1.id

            # Create second with same channel - should update
            n2 = db.add(conn, channel="test:123", message="Second")

            assert n2.id == first_id  # Same ID
            assert n2.message == "Second"  # Updated message

            # Only one notification should exist
            unread = db.get_unread(conn)
            assert len(unread) == 1
            assert unread[0].message == "Second"


def test_add_upsert_updates_read_notification():
    """add() with upsert=True should update and reset read notification to unread."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            # Create and mark as read
            n1 = db.add(conn, channel="test:123", message="First")
            db.mark_read(conn, n1.id)

            # Verify it's read
            read_n1 = db.get(conn, n1.id)
            assert read_n1 is not None
            assert read_n1.is_read

            # Create second with upsert - should update and reset to unread
            n2 = db.add(conn, channel="test:123", message="Second")

            assert n2.id == n1.id  # Same ID (updated)
            assert n2.message == "Second"
            assert n2.status == "unread"  # Reset to unread


def test_get_unread_returns_only_unread():
    """get_unread() should only return unread notifications."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            n1 = db.add(conn, channel="test:1", message="Unread")
            n2 = db.add(conn, channel="test:2", message="Will be read")
            db.mark_read(conn, n2.id)

            unread = db.get_unread(conn)
            assert len(unread) == 1
            assert unread[0].id == n1.id


def test_mark_read():
    """mark_read() should update status and read_at."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            n = db.add(conn, channel="test:123", message="Test")
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
            db.add(conn, channel="test:aaa", message="A1", upsert=False)
            db.add(conn, channel="test:aaa", message="A2", upsert=False)
            db.add(conn, channel="test:bbb", message="B1")

            count = db.mark_all_read_for_channel(conn, "test:aaa")
            assert count == 2

            unread = db.get_unread(conn)
            assert len(unread) == 1
            assert unread[0].channel == "test:bbb"


def test_mark_all_read_for_channel_with_message():
    """mark_all_read_for_channel() should update message when provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            n = db.add(conn, channel="test:123", message="Waiting...")

            count = db.mark_all_read_for_channel(conn, "test:123", message="Reading file.py")
            assert count == 1

            updated = db.get(conn, n.id)
            assert updated is not None
            assert updated.is_read
            assert updated.message == "Reading file.py"


def test_notification_from_row():
    """Notification.from_row() should correctly parse database row."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with db.connect(db_path) as conn:
            db.add(
                conn,
                channel="test:123",
                message="Test",
                name="my-session",
                metadata={"tty": "/dev/ttys001"},
            )

            row = conn.execute("SELECT * FROM notifications WHERE id = 1").fetchone()
            notification = db.Notification.from_row(row)

            assert notification.channel == "test:123"
            assert notification.message == "Test"
            assert notification.name == "my-session"
            assert notification.metadata == {"tty": "/dev/ttys001"}


def test_register_working_new_session_is_read():
    """register_working() inserts a brand-new session as read/working."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "test.db") as conn:
        n = db.register_working(
            conn,
            channel="claude:abc",
            message="Working in ~/proj",
            name="proj",
            switch_source="tmux",
        )
        assert n.id > 0
        assert n.status == "read"
        assert n.switch_source == "tmux"


def test_register_working_preserves_unread_status():
    """A session already unread (from a Stop hook) is not dismissed by a submit."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "test.db") as conn:
        db.add(conn, channel="claude:abc", message="Waiting")  # unread
        n = db.register_working(conn, channel="claude:abc", message="Working")
        assert n.status == "unread"
        assert n.message == "Working"


def test_register_working_does_not_bump_created_at():
    """Updating an existing session must not reorder it (created_at unchanged)."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "test.db") as conn:
        first = db.register_working(conn, channel="claude:abc", message="Working")
        second = db.register_working(conn, channel="claude:abc", message="Still working")
        assert second.created_at == first.created_at


def test_register_working_unarchives_to_read():
    """A submit to an archived session brings it back as read, keeping created_at."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "test.db") as conn:
        created = db.add(
            conn, channel="claude:abc", message="old", created_at=42, status="archived"
        )
        n = db.register_working(conn, channel="claude:abc", message="Working")
        assert n.status == "read"
        assert n.created_at == created.created_at == 42


def test_register_working_preserves_user_name():
    """A user-renamed session keeps its name through a working update."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "test.db") as conn:
        db.add(
            conn,
            channel="claude:abc",
            message="x",
            name="my-name",
            metadata={"auto_name": "auto"},
        )
        n = db.register_working(conn, channel="claude:abc", message="Working", name="ignored")
        assert n.name == "my-name"
        assert n.metadata["auto_name"] == "auto"


def test_tmux_location_survives_an_update_that_cannot_see_it():
    """A hook can fire from a subprocess with no TMUX_PANE.

    metadata is replaced wholesale on update, so without carrying these forward
    one such observation erases the only record of where the session was - which
    is exactly what `tmux restore` needs after a crash.
    """
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "test.db") as conn:
        db.add(
            conn,
            channel="claude:abc",
            message="first",
            metadata={"cwd": "/tmp", "tmux_session": "relay", "tmux_window": "4"},
        )
        updated = db.add(conn, channel="claude:abc", message="second", metadata={"cwd": "/tmp"})

    assert updated.metadata["tmux_session"] == "relay"
    assert updated.metadata["tmux_window"] == "4"


def test_a_newly_observed_tmux_location_wins():
    """Moving a session to another window must not be papered over by the old one."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "test.db") as conn:
        db.add(
            conn,
            channel="claude:abc",
            message="first",
            metadata={"tmux_session": "relay", "tmux_window": "4"},
        )
        updated = db.add(
            conn,
            channel="claude:abc",
            message="second",
            metadata={"tmux_session": "main", "tmux_window": "2"},
        )

    assert updated.metadata["tmux_session"] == "main"
    assert updated.metadata["tmux_window"] == "2"


def test_record_location_only_touches_the_location():
    """It runs on the watcher's poll for idle sessions; anything else would lie."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "t.db") as conn:
        added = db.add(conn, channel="claude:abc", message="hello", metadata={"cwd": "/tmp"})
        db.mark_read(conn, added.id)

        assert db.record_location(conn, "claude:abc", "relay", "4") is True

        after = db.get_by_channel(conn, "claude:abc", unread_only=False)

    assert after.metadata["tmux_session"] == "relay"
    assert after.metadata["cwd"] == "/tmp"
    assert after.message == "hello"
    assert after.status == "read"


def test_record_location_is_a_no_op_when_unchanged():
    """Every poll would otherwise be a write for every session."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "t.db") as conn:
        db.add(
            conn,
            channel="claude:abc",
            message="hello",
            metadata={"tmux_session": "relay", "tmux_window": "4"},
        )

        assert db.record_location(conn, "claude:abc", "relay", "4") is False


def test_record_location_follows_a_moved_window():
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "t.db") as conn:
        db.add(
            conn,
            channel="claude:abc",
            message="hello",
            metadata={"tmux_session": "relay", "tmux_window": "4"},
        )
        db.record_location(conn, "claude:abc", "relay", "7")

        assert db.get_by_channel(conn, "claude:abc").metadata["tmux_window"] == "7"


def test_record_location_ignores_an_unknown_channel():
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "t.db") as conn:
        assert db.record_location(conn, "claude:nope", "relay", "1") is False
