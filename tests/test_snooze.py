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


def test_snooze_through_turns_holds_through_a_turn_end():
    """A turn ending unread leaves it snoozed, and it wakes unread."""
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", switch_source="tmux")
        db.mark_read(conn, n.id)
        until = time.time() + 3600
        db.snooze(conn, n.id, until, through_turns=True)

        db.add(conn, channel="claude:abc", message="Turn ended", ends_turn=True)
        db.add(conn, channel="claude:abc", message="(quiet)", status="read", ends_turn=True)

        held = db.get(conn, n.id)
        assert held is not None
        assert (held.status, held.snooze_until, held.message) == ("snoozed", until, "(quiet)")

        db.wake_expired(conn, now=until + 1)
        woken = db.get(conn, n.id)
        assert woken is not None
        assert (woken.status, woken.snooze_through_turns) == ("unread", False)


def test_snooze_through_turns_wakes_read_when_every_turn_was_read():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", status="read")
        db.snooze(conn, n.id, time.time() - 1, through_turns=True)
        db.add(conn, channel="claude:abc", message="(quiet)", status="read", ends_turn=True)

        db.wake_expired(conn)
        woken = db.get(conn, n.id)
        assert woken is not None
        assert woken.status == "read"


def test_a_prompt_wakes_a_snooze_through_turns():
    """A notification that is not a turn end, such as a permission prompt, wakes it."""
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", status="read")
        db.snooze(conn, n.id, time.time() + 3600, through_turns=True)

        db.add(conn, channel="claude:abc", message="Needs permission")

        woken = db.get(conn, n.id)
        assert woken is not None
        assert (woken.status, woken.snooze_until, woken.snooze_through_turns) == (
            "unread",
            None,
            False,
        )


def test_a_turn_end_still_wakes_a_tui_snooze():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", status="read")
        db.snooze(conn, n.id, time.time() + 3600)

        db.add(conn, channel="claude:abc", message="Turn ended", ends_turn=True)

        woken = db.get(conn, n.id)
        assert woken is not None
        assert woken.is_unread


def test_snoozing_again_moves_the_wake_time_and_keeps_the_prior_status():
    with tempfile.TemporaryDirectory() as tmpdir, _conn(tmpdir) as conn:
        n = db.add(conn, channel="claude:abc", message="x", status="read")
        db.snooze(conn, n.id, time.time() + 60)
        later = time.time() + 7200
        db.snooze(conn, n.id, later, through_turns=True)

        snoozed = db.get(conn, n.id)
        assert snoozed is not None
        assert (snoozed.snooze_until, snoozed.snooze_prev_status) == (later, "read")
        assert snoozed.snooze_through_turns
