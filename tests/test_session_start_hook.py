"""The hook that fires without a turn.

Every other Claude hook needs the user to say something, so a session that has
just started - or been resumed after a crash - is invisible until spoken to.
That is exactly the session a restore has to find, which is what this one is for.
"""

import json

from lemonaid.claude import notify
from lemonaid.inbox import db


def _fire(source: str = "startup", session_id: str = "s-1", cwd: str = "/tmp") -> None:
    notify.handle_session_start(
        json.dumps(
            {
                "session_id": session_id,
                "cwd": cwd,
                "source": source,
                "hook_event_name": "SessionStart",
            }
        )
    )


def _only():
    with db.connect() as conn:
        rows = db.get_active(conn, switch_source=None)
    assert len(rows) == 1, rows
    return rows[0]


def test_a_started_session_is_registered():
    _fire()

    assert _only().metadata["session_id"] == "s-1"


def test_a_started_session_does_not_ask_for_attention():
    """It has not said anything yet. A restore that flagged everything it
    started would be its own kind of noise."""
    _fire()

    assert _only().status == "read"


def test_a_resume_is_recorded_as_such(monkeypatch):
    _fire(source="resume")

    assert _only().metadata["session_start_source"] == "resume"


def test_the_location_is_recorded(monkeypatch):
    """The point of firing on resume: the session is somewhere new, and nothing
    else would notice until the user typed."""
    monkeypatch.setattr(notify, "get_tmux_session_name", lambda: "relay")
    monkeypatch.setattr(notify, "get_tmux_window_index", lambda: "3")
    monkeypatch.setattr(notify, "get_tmux_socket", lambda: "/tmp/tmux-1/default")
    _fire(source="resume")

    m = _only().metadata
    assert (m["tmux_session"], m["tmux_window"], m["tmux_socket"]) == (
        "relay",
        "3",
        "/tmp/tmux-1/default",
    )


def test_resuming_reuses_the_session_row():
    """Same session_id, so this is the same inbox entry moving, not a new one.

    Counted by channel rather than by listing active rows: a watcher thread from
    another test's app can archive a row between the two calls, which changes
    what is active without changing whether a second row was created.
    """
    _fire(source="startup")
    _fire(source="resume")

    with db.connect() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE channel = ?", ("claude:s-1",)
        ).fetchone()
    assert rows[0] == 1


def test_an_unread_session_stays_unread():
    """A session that asked for attention before being resumed still wants it."""
    _fire()
    with db.connect() as conn:
        conn.execute("UPDATE notifications SET status = 'unread'")
        conn.commit()

    _fire(source="resume")

    assert _only().status == "unread"


def test_a_resumed_session_returns_from_the_archive():
    """This is what a restore does: the row was archived when the pane died."""
    _fire()
    with db.connect() as conn:
        conn.execute("UPDATE notifications SET status = 'archived'")
        conn.commit()

    _fire(source="resume")

    assert _only().status == "read"


def test_malformed_input_does_not_raise():
    """A hook that crashes on bad stdin blocks the session from starting."""
    notify.handle_session_start("not json at all")
