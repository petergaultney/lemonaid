"""After `/clear`, the new Claude session takes over the lemon: its brief, inbox name and pins."""

import json
import time

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.brief.handoff import state as handoff_state
from lemonaid.claude import notify, session_end
from lemonaid.hooks import session_start
from lemonaid.inbox import db, pins

_OLD = "6f3198c7-1111-4222-8333-444444444444"
_NEW = "fb0730c2-5555-4666-8777-888888888888"
_NEXT = "0c1d2e3f-9999-4aaa-8bbb-cccccccccccc"
_TTY = "/dev/ttys031"


@pytest.fixture
def lemon(monkeypatch, tmp_path):
    """A named, pinned Claude lemon with a brief, on a terminal."""
    for module in (notify, session_start):
        monkeypatch.setattr(module, "get_tty", lambda: _TTY)
    monkeypatch.setattr(session_start, "_pushed", lambda path, session_id: True)
    path = brief_store.briefs_dir() / "helpdesk.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Helpdesk\n\n## Now\n\nAnswering.\n")
    _start(_OLD, "startup", tmp_path)
    with db.connect() as conn:
        attached.attach(conn, "claude:6f3198c7", path)
        identity.ensure(conn, path)
        db.update_name(
            conn, db.get_by_channel(conn, "claude:6f3198c7", unread_only=False).id, "Helpdesk"
        )
        pins.pin(conn, "claude:6f3198c7")
    return path


def _start(session_id: str, source: str, cwd) -> None:
    notify.handle_session_start(
        json.dumps({"session_id": session_id, "cwd": str(cwd), "source": source})
    )


def _clear(tmp_path, register: bool = True) -> str:
    """What Claude runs on `/clear`: SessionEnd for the old session, then both SessionStart hooks."""
    session_end.handle_session_end(json.dumps({"session_id": _OLD, "reason": "clear"}))
    if register:
        _start(_NEW, "clear", tmp_path)
    return session_start.context({"session_id": _NEW, "source": "clear"}, "claude")


def _row(channel: str) -> db.Notification:
    with db.connect() as conn:
        found = db.get_by_channel(conn, channel, unread_only=False)
    assert found is not None
    return found


def _rows(channel: str) -> int:
    with db.connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE channel = ?", (channel,)
        ).fetchone()[0]


def _holder(path) -> str:
    with db.connect() as conn:
        return {item.path: item.channel for item in attached.everything(conn)}[path]


def test_clear_moves_the_lemon_to_the_new_session(lemon, tmp_path):
    text = _clear(tmp_path)

    assert _holder(lemon) == "claude:fb0730c2"
    assert "from claude:6f3198c7, the session before /clear" in text
    assert f"Your brief is {lemon}" in text
    assert _row("claude:fb0730c2").name == "Helpdesk"
    assert _row("claude:6f3198c7").status == "archived"
    with db.connect() as conn:
        assert pins.pinned_positions(conn) == {"claude:fb0730c2": 10.0}
        live = conn.execute("SELECT channel FROM notifications WHERE status != 'archived'")
        assert [row["channel"] for row in live] == ["claude:fb0730c2"]


def test_the_new_name_survives_the_new_sessions_next_hooks(lemon, tmp_path):
    _clear(tmp_path)
    _start(_NEW, "clear", tmp_path)

    assert _row("claude:fb0730c2").name == "Helpdesk"


def test_a_late_row_is_waited_for(lemon, tmp_path, monkeypatch):
    sleep = time.sleep

    def register_then_sleep(seconds: float) -> None:
        if not _rows("claude:fb0730c2"):
            _start(_NEW, "clear", tmp_path)
        sleep(seconds)

    monkeypatch.setattr(session_start.time, "sleep", register_then_sleep)

    _clear(tmp_path, register=False)

    assert _holder(lemon) == "claude:fb0730c2"
    assert _row("claude:fb0730c2").name == "Helpdesk"


def test_without_a_new_row_the_old_session_keeps_the_brief(lemon, tmp_path, monkeypatch):
    monkeypatch.setattr(session_start, "_ROW_WAIT_SECONDS", 0.2)

    assert _clear(tmp_path, register=False) == ""

    assert _holder(lemon) == "claude:6f3198c7"
    assert _row("claude:6f3198c7").status != "archived"


def test_a_session_end_for_another_reason_moves_nothing(lemon, tmp_path):
    session_end.handle_session_end(json.dumps({"session_id": _OLD, "reason": "logout"}))
    _start(_NEW, "clear", tmp_path)

    assert session_start.context({"session_id": _NEW, "source": "clear"}, "claude") == ""
    assert _holder(lemon) == "claude:6f3198c7"


def test_a_clear_on_another_terminal_moves_nothing(lemon, tmp_path, monkeypatch):
    monkeypatch.setattr(session_start, "get_tty", lambda: "/dev/ttys099")

    assert _clear(tmp_path) == ""
    assert _holder(lemon) == "claude:6f3198c7"


def test_a_pending_handoff_keeps_the_brief(lemon, tmp_path):
    with db.connect() as conn:
        handoff_state.request(
            conn, lemon, "claude:6f3198c7", "codex", "", "", "", "", str(tmp_path), time.time() + 60
        )

    assert _clear(tmp_path) == ""
    assert _holder(lemon) == "claude:6f3198c7"


def test_an_archived_last_clear_hides_an_older_clear_on_the_terminal(lemon, tmp_path, monkeypatch):
    monkeypatch.setattr(session_start, "_ROW_WAIT_SECONDS", 0.2)
    _clear(tmp_path, register=False)
    _start(_NEW, "clear", tmp_path)
    with db.connect() as conn:
        db.archive_channel(conn, "claude:fb0730c2", "dismissed")
    session_end.handle_session_end(json.dumps({"session_id": _NEW, "reason": "clear"}))
    _start(_NEXT, "clear", tmp_path)

    assert session_start.context({"session_id": _NEXT, "source": "clear"}, "claude") == ""
    assert _holder(lemon) == "claude:6f3198c7"


def test_a_brief_waiting_on_the_window_claims_the_new_session_first(lemon, tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "get_tmux_session_name", lambda: "work")
    monkeypatch.setattr(notify, "get_tmux_window_index", lambda: "1")
    waiting = lemon.with_name("replacement.md")
    waiting.write_text("# Replacement\n\n## Now\n\nStarting.\n")
    with db.connect() as conn:
        attached.attach_pending(conn, "work", "1", waiting, attached.live_channels(conn))

    _clear(tmp_path)

    assert _holder(waiting) == "claude:fb0730c2"
    assert _holder(lemon) == "claude:6f3198c7"


def test_a_clear_in_another_pane_on_a_reused_tty_moves_nothing(lemon, tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "get_tmux_session_order", lambda: (1, 100, 3))
    monkeypatch.setenv("TMUX_PANE", "%2")
    with db.connect() as conn:
        old = db.get_by_channel(conn, "claude:6f3198c7", unread_only=False)
        conn.execute(
            "UPDATE notifications SET metadata = ? WHERE id = ?",
            (json.dumps({**old.metadata, "tmux_pane_identity": ["%1", 100]}), old.id),
        )
        conn.commit()

    assert _clear(tmp_path) == ""
    assert _holder(lemon) == "claude:6f3198c7"
