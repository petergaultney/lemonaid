"""Telling a still-running archived session from an exited one, and restoring it."""

import time

from lemonaid.inbox import db, unarchive
from lemonaid.lemon_watchers import watcher

TTY = "/dev/ttys950"


def _session(channel: str, *, archived: bool, created_at: float, **metadata) -> db.Notification:
    with db.connect() as conn:
        n = db.add(
            conn, channel, "waiting", metadata={"tty": TTY, "cwd": "/tmp", **metadata}, upsert=False
        )
        conn.execute(
            "UPDATE notifications SET status = ?, switch_source = 'tmux', created_at = ? "
            "WHERE id = ?",
            ("archived" if archived else "unread", created_at, n.id),
        )
        conn.commit()
        found = db.get(conn, n.id)
    assert found
    return found


def _live(monkeypatch, pane: bool | None = True, process: bool = True) -> list[tuple]:
    asked: list[tuple] = []
    monkeypatch.setattr(
        unarchive,
        "check_pane_exists_by_tty",
        lambda *a: asked.append(("pane", *a)) or pane,
    )
    monkeypatch.setattr(
        watcher,
        "is_process_running_on_tty",
        lambda *a: asked.append(("process", *a)) or process,
    )
    return asked


def test_a_restored_session_comes_back_unread_and_newest():
    n = _session("codex:hq", archived=True, created_at=100.0)
    before = time.time()

    with db.connect() as conn:
        unarchive.restore(conn, n.channel)
        restored = db.get(conn, n.id)

    assert restored and restored.status == "unread"
    assert restored.created_at >= before


def test_every_archived_row_on_the_channel_comes_back():
    """archive() retires the whole channel; history would otherwise show an older row."""
    older = _session("codex:hq", archived=True, created_at=50.0)
    newer = _session("codex:hq", archived=True, created_at=100.0)

    with db.connect() as conn:
        unarchive.restore(conn, newer.channel)
        assert db.get(conn, older.id).status == "unread"
        assert db.get_history(conn) == []


def test_the_next_notification_updates_the_row_the_inbox_shows():
    """Tied timestamps would send the next hook's upsert to the older row."""
    older = _session("codex:hq", archived=True, created_at=50.0)
    newer = _session("codex:hq", archived=True, created_at=100.0)

    with db.connect() as conn:
        unarchive.restore(conn, newer.channel)
        assert db.get(conn, older.id).created_at == 50.0
        updated = db.add(conn, "codex:hq", "next turn", metadata={"tty": TTY})
        shown = db.get_active(conn)

    assert updated.id == newer.id
    assert [(n.id, n.message) for n in shown] == [(newer.id, "next turn")]


def test_a_session_whose_harness_exited_is_not_running(monkeypatch):
    _live(monkeypatch, process=False)
    assert not unarchive.running(_session("codex:gone", archived=True, created_at=100.0))


def test_a_missing_pane_or_an_unanswering_tmux_is_not_running(monkeypatch):
    for pane in (False, None):
        _live(monkeypatch, pane=pane)
        n = _session(f"codex:{pane}", archived=True, created_at=100.0)
        assert not unarchive.running(n)


def test_rows_that_are_not_archived_are_left_alone():
    n = _session("claude:here", archived=False, created_at=100.0)

    with db.connect() as conn:
        assert unarchive.restore(conn, n.channel) == 0
        assert db.get(conn, n.id).created_at == 100.0


def test_the_recorded_server_and_harness_are_the_ones_asked(monkeypatch):
    asked = _live(monkeypatch)
    n = _session("codex:hq", archived=True, created_at=100.0, tmux_socket="/tmp/tmux-1/other")

    assert unarchive.running(n)
    assert asked == [
        ("pane", TTY, "tmux", "/tmp/tmux-1/other", 100.0),
        ("process", TTY, "codex"),
    ]


def test_the_watcher_keeps_both_rows_when_a_restored_session_shares_the_tty(monkeypatch):
    """A restored session sharing a live TTY does not prove another row ended."""
    _live(monkeypatch)
    hq = _session("codex:hq", archived=True, created_at=100.0)
    _session("codex:subagent", archived=False, created_at=200.0)

    with db.connect() as conn:
        unarchive.restore(conn, hq.channel)
        active = [
            (
                n.channel,
                n.metadata.get("session_id", ""),
                "/tmp",
                n.created_at,
                True,
                TTY,
                "",
                "tmux",
            )
            for n in db.get_active(conn)
        ]

    archived = watcher._archive_stale_sessions(
        active, lambda channel: None, {}, {None: {TTY: ("work", "2")}}
    )

    assert archived == set()


def test_a_focused_tty_brings_its_archived_running_session_back_read(monkeypatch):
    _live(monkeypatch)
    n = _session("claude:old", archived=True, created_at=100.0)

    with db.connect() as conn:
        assert unarchive.restore_focused(conn, [TTY]) == ["claude:old"]
        assert db.get(conn, n.id).status == "read"


def test_a_focused_tty_whose_newest_row_is_live_restores_nothing(monkeypatch):
    _live(monkeypatch)
    old = _session("claude:old", archived=True, created_at=100.0)
    _session("claude:new", archived=False, created_at=200.0)

    with db.connect() as conn:
        assert unarchive.restore_focused(conn, [TTY]) == []
        assert db.get(conn, old.id).status == "archived"


def test_a_focused_tty_whose_harness_exited_restores_nothing(monkeypatch):
    _live(monkeypatch, process=False)
    n = _session("claude:gone", archived=True, created_at=100.0)

    with db.connect() as conn:
        assert unarchive.restore_focused(conn, [TTY]) == []
        assert db.get(conn, n.id).status == "archived"
