"""Which running lemons a restore would miss, known before a crash."""

from lemonaid.config import Config
from lemonaid.inbox import db, doctor, ended
from lemonaid.restore import auto, readiness
from lemonaid.tmux import readiness as tmux_readiness


def _row(channel: str, **metadata: object) -> db.Notification:
    return db.Notification(
        0,
        channel,
        "",
        name=channel,
        metadata={"session_id": "s", "cwd": "/tmp", **metadata},
        switch_source="tmux",
    )


def test_a_lemon_with_no_recorded_window_or_transcript_would_not_come_back(monkeypatch):
    monkeypatch.setattr(
        readiness.plan, "transcript_missing", lambda row: row.channel.endswith("gone")
    )
    placed = {
        "tmux_session": "work",
        "tmux_window": "1",
        "tmux_socket": "/tmp/tmux-1/default",
        "tmux_session_order": [5, 100, 1],
    }
    rows = [
        _row("claude:ready", **placed),
        _row("claude:nowhere"),
        _row("claude:adopted", tmux_session="work", tmux_window="2"),
        _row("claude:gone", **placed),
        _row("claude:lost", **{**placed, "ended": ended.record(ended.SERVER_LOST, "test")}),
    ]

    assert [(row.channel, why) for row, why in readiness.unready(rows, Config())] == [
        ("claude:nowhere", "no recorded tmux window"),
        ("claude:adopted", "no recorded tmux server, so its loss can't be told"),
        ("claude:gone", "its transcript is gone"),
    ]


def test_a_running_lemon_pane_the_inbox_doesnt_know_is_reported_and_not_adopted(monkeypatch):
    pane = doctor.Pane("work", "3", "/dev/ttys9", "codex")
    monkeypatch.setattr(tmux_readiness.doctor, "unknown_panes", lambda: [pane])

    with db.connect() as conn:
        readiness.check(conn, Config())
        row = db.get_by_channel(conn, readiness.CHANNEL, unread_only=False)
        others = [r.channel for r in db.get_active(conn) if r.channel != readiness.CHANNEL]

    assert row is not None and "work:3: a running codex the inbox doesn't know" in row.message
    assert others == []


def test_the_row_goes_away_once_nothing_is_missing(monkeypatch):
    monkeypatch.setattr(
        tmux_readiness.doctor, "unknown_panes", lambda: [doctor.Pane("w", "1", "t", "claude")]
    )
    with db.connect() as conn:
        readiness.check(conn, Config())
        monkeypatch.setattr(tmux_readiness.doctor, "unknown_panes", list)
        readiness.check(conn, Config())
        row = db.get_by_channel(conn, readiness.CHANNEL, unread_only=False)

    assert row is not None and row.is_archived


def test_a_restore_is_due_only_when_asked_to_look_and_a_lemon_is_lost():
    with db.connect() as conn:
        db.add(conn, "claude:x", "w", metadata={"tty": "/dev/x"}, switch_source="tmux")
        assert not auto.due(conn, "on", True)
        db.mark_lost(conn, "claude:x", "test", "")
        assert auto.due(conn, "on", True)
        assert auto.due(conn, "ask", True)
        assert not auto.due(conn, "on", False)
        assert not auto.due(conn, "off", True)


def test_the_lock_admits_one_holder_at_a_time():
    with auto.lock() as first, auto.lock() as second:
        assert (first, second) == (True, False)
    with auto.lock() as again:
        assert again
