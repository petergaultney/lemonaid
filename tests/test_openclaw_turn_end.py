import re

import pytest

from lemonaid.inbox import db
from lemonaid.openclaw import sessions, turn_end

KEY = "agent:main:signal:direct:uuid:abc"
QUIET = (re.compile(r"\(quiet\)"),)


def _row(status: str, created_at: float = 1.0) -> db.Notification:
    with db.connect() as conn:
        n = db.add(conn, channel=sessions.channel(KEY), message="hi")
        conn.execute(
            "UPDATE notifications SET status = ?, created_at = ? WHERE id = ?",
            (status, created_at, n.id),
        )
        conn.commit()
        return db.get(conn, n.id)


def _now(n: db.Notification) -> db.Notification:
    with db.connect() as conn:
        return db.get(conn, n.id)


def _says(monkeypatch, text: str) -> None:
    monkeypatch.setattr(turn_end.conversation, "final_message", lambda *a: text)


@pytest.mark.parametrize("before", ["read", "unread"])
def test_a_finished_turn_leaves_its_row_unread_as_of_now(monkeypatch, before):
    n = _row(before)
    _says(monkeypatch, "Done, PR is up")

    turn_end.settle(KEY, "openclaw", QUIET, 0.0, failed=False)

    assert (_now(n).status, _now(n).created_at > 1.0) == ("unread", True)


@pytest.mark.parametrize("before", ["read", "unread"])
def test_a_turn_ending_with_an_auto_read_message_leaves_it_read_as_of_now(monkeypatch, before):
    n = _row(before)
    _says(monkeypatch, "(quiet) rearmed")

    turn_end.settle(KEY, "openclaw", QUIET, 0.0, failed=False)

    assert (_now(n).status, _now(n).created_at > 1.0) == ("read", True)


def test_a_failed_turn_is_unread_whatever_the_lemon_said_last(monkeypatch):
    n = _row("read")
    _says(monkeypatch, "(quiet) from the turn before")

    turn_end.settle(KEY, "openclaw", QUIET, 0.0, failed=True)

    assert _now(n).status == "unread"


def test_a_final_message_the_gateway_cant_give_leaves_the_row_unread(monkeypatch):
    n = _row("read")

    def down(*args):
        raise OSError("gateway down")

    monkeypatch.setattr(turn_end.conversation, "final_message", down)

    turn_end.settle(KEY, "openclaw", QUIET, 0.0, failed=False)

    assert _now(n).is_unread


def test_an_archived_row_stays_archived(monkeypatch):
    n = _row("archived")
    _says(monkeypatch, "Done")

    turn_end.settle(KEY, "openclaw", QUIET, 0.0, failed=False)

    assert (_now(n).status, _now(n).created_at) == ("archived", 1.0)


def test_a_snooze_held_through_turns_stays_and_wakes_unread(monkeypatch):
    n = _row("read")
    with db.connect() as conn:
        db.snooze(conn, n.id, 9e12)
        db.hold_snooze_through_turns(conn, n.id)
    _says(monkeypatch, "Done")

    turn_end.settle(KEY, "openclaw", QUIET, 0.0, failed=False)

    assert (_now(n).status, _now(n).snooze_prev_status) == ("snoozed", "unread")
