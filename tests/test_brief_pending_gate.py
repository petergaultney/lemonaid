"""A waiting brief asks tmux where its window is only when a claim could have changed."""

import time

from lemonaid.brief import attached, pending_gate, session
from lemonaid.inbox import db

from .test_brief_pending import _attached_to, _brief, _lemon


def _lookups(monkeypatch) -> list[str]:
    asked: list[str] = []
    monkeypatch.setattr(
        session, "window_location", lambda window_id: (asked.append(window_id), ("", ""))[1]
    )
    return asked


def _waiting_on(window: str) -> None:
    with db.connect() as conn:
        attached.attach_pending(
            conn, "fresh", window, _brief("task"), attached.live_channels(conn), tmux_window_id="@7"
        )


def test_a_tick_that_changes_nothing_skips_the_lookup(monkeypatch):
    asked = _lookups(monkeypatch)
    _waiting_on("4")
    with db.connect() as conn:
        attached.claim_pending(conn)
        attached.claim_pending(conn)

    assert asked == ["@7"]


def test_a_lemon_starting_in_the_window_is_checked_at_once(monkeypatch):
    asked = _lookups(monkeypatch)
    _waiting_on("4")
    with db.connect() as conn:
        attached.claim_pending(conn)
    _lemon("claude:new", "fresh", "4")

    assert _attached_to("claude:new") == _brief("task")
    assert asked == ["@7", "@7"]


def test_what_only_tmux_knows_is_rechecked_after_a_while(monkeypatch):
    asked = _lookups(monkeypatch)
    _waiting_on("4")
    with db.connect() as conn:
        assert pending_gate.due(conn, 1000.0)
        assert not pending_gate.due(conn, 1001.0)
        assert pending_gate.due(conn, 1000.0 + pending_gate._RECHECK_SECONDS)
    assert asked == []


def test_a_brief_waiting_over_two_weeks_stops_waiting():
    _waiting_on("4")
    with db.connect() as conn:
        conn.execute("UPDATE pending_briefs SET requested_at = ?", (time.time() - 16 * 86400,))
        conn.commit()
        attached.claim_pending(conn)

        assert conn.execute("SELECT COUNT(*) FROM pending_briefs").fetchone()[0] == 0
