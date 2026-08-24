"""Returning a session you have already looked at to the unread group.

The distinction that matters here is against mark_unread_for_channel(), which
watchers call when an agent produces new output and which deliberately bumps
created_at. A manual mark-unread means "I have not dealt with this", so the
session keeps its age and sorts accordingly.
"""

import tempfile
import time
from pathlib import Path

from lemonaid.inbox import db


def _conn(tmpdir: str):
    return db.connect(Path(tmpdir) / "test.db")


def test_a_read_session_becomes_unread_again():
    with tempfile.TemporaryDirectory() as tmpdir:
        with _conn(tmpdir) as conn:
            n = db.add(conn, channel="test:1", message="hi")
            db.mark_read(conn, n.id)

            db.mark_unread(conn, n.id)

            assert db.get(conn, n.id).is_unread


def test_the_read_timestamp_is_cleared():
    """A session with both status unread and a read_at would be self-contradictory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with _conn(tmpdir) as conn:
            n = db.add(conn, channel="test:1", message="hi")
            db.mark_read(conn, n.id)
            assert db.get(conn, n.id).read_at is not None

            db.mark_unread(conn, n.id)

            assert db.get(conn, n.id).read_at is None


def test_the_session_keeps_its_age():
    """Bumping created_at would jump it to the top, which is what snooze is for."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with _conn(tmpdir) as conn:
            n = db.add(conn, channel="test:1", message="hi")
            db.mark_read(conn, n.id)
            before = db.get(conn, n.id).created_at

            db.mark_unread(conn, n.id)

            assert db.get(conn, n.id).created_at == before


def test_it_sorts_among_the_unreads_by_age_not_at_the_top():
    """The whole point: an old session marked unread stays below newer unreads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with _conn(tmpdir) as conn:
            now = time.time()
            old = db.add(conn, channel="test:old", message="old", created_at=now - 900)
            db.add(conn, channel="test:new", message="new", created_at=now - 60)
            db.mark_read(conn, old.id)

            db.mark_unread(conn, old.id)

            assert [n.channel for n in db.get_active(conn)] == ["test:new", "test:old"]


def test_only_the_named_session_changes():
    with tempfile.TemporaryDirectory() as tmpdir:
        with _conn(tmpdir) as conn:
            one = db.add(conn, channel="test:1", message="one")
            two = db.add(conn, channel="test:2", message="two")
            db.mark_read(conn, one.id)
            db.mark_read(conn, two.id)

            db.mark_unread(conn, one.id)

            assert db.get(conn, two.id).is_read
