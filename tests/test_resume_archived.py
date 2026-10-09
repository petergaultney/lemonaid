"""Resuming an archived session from the scratch pane starts it, and it stays in the inbox.

The scratch pane once only copied the resume command and marked the row unread,
so the watcher archived it again within a second: its recorded pane was long
gone, and a resumed Codex reports its new tty only when a turn ends.
"""

import asyncio

import pytest

from lemonaid.config import Config
from lemonaid.inbox import db, resume_archived
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.resume_error import ResumeErrorScreen
from lemonaid.lemon_watchers import watcher


def _archived(tmp_path) -> db.Notification:
    metadata = {
        "tty": "/dev/ttys935",
        "cwd": str(tmp_path),
        "session_id": "01a10d5a-0000-7000-8000-000000000000",
        "tmux_session": "gone",
        "tmux_session_order": [10, 20, 3],
    }
    with db.connect() as conn:
        n = db.add(conn, "codex:01a10d5a-0000-7000-8000-000000000000", "done", "cost", metadata)
        conn.execute(
            "UPDATE notifications SET status = 'archived', switch_source = 'tmux' WHERE id = ?",
            (n.id,),
        )
        conn.commit()
        return db.get(conn, n.id)


_NEW_PANE = {"/dev/ttys977": watcher.tmux.navigation.PaneLocation("cost", "1", (30, 20, 9))}


def _row(nid: int) -> db.Notification:
    with db.connect() as conn:
        return db.get(conn, nid)


def _no_session_to_reuse(monkeypatch) -> list[tuple]:
    spawned: list[tuple] = []
    monkeypatch.setattr(resume_archived.tmux.recreate, "resume", lambda *a: None)
    monkeypatch.setattr(
        resume_archived.tmux.session,
        "spawn_resumed",
        lambda *a: spawned.append(a) or (None, "/dev/ttys977"),
    )
    return spawned


@pytest.fixture(autouse=True)
def _new_pane(monkeypatch):
    monkeypatch.setattr(resume_archived.tmux.navigation, "locations_by_tty", lambda *a: _NEW_PANE)


def test_resumed_row_is_restored_on_its_new_pane(monkeypatch, tmp_path):
    n = _archived(tmp_path)
    monkeypatch.setattr(resume_archived.tmux.recreate, "resume", lambda *a: "/dev/ttys977")

    assert resume_archived.in_tmux(n, Config()) is None

    row = _row(n.id)
    assert row.status == "unread"
    assert row.metadata["tty"] == "/dev/ttys977"
    assert row.metadata["tmux_session"] == "cost"
    assert row.metadata["tmux_session_order"] == [30, 20, 9]
    assert row.metadata["tmux_socket"] == "/nonexistent/lemonaid-tests"


def test_without_a_session_to_reuse_one_is_started(monkeypatch, tmp_path):
    n = _archived(tmp_path)
    spawned = _no_session_to_reuse(monkeypatch)

    assert resume_archived.in_tmux(n, Config()) is None

    assert spawned[0][0] == str(tmp_path)
    assert spawned[0][2][:2] == ["codex", "resume"]
    assert _row(n.id).metadata["tty"] == "/dev/ttys977"


def test_a_failed_start_says_why_and_leaves_the_row_archived(monkeypatch, tmp_path):
    n = _archived(tmp_path)
    monkeypatch.setattr(resume_archived.tmux.recreate, "resume", lambda *a: None)
    monkeypatch.setattr(
        resume_archived.tmux.session,
        "spawn_resumed",
        lambda *a: ("session 'cost' exists", None),
    )

    assert resume_archived.in_tmux(n, Config()) == "session 'cost' exists"
    assert _row(n.id).status == "archived"


def test_the_watcher_keeps_the_resumed_row(monkeypatch, tmp_path):
    """Judged on the new pane rather than the dead one it was archived from."""
    n = _archived(tmp_path)
    _no_session_to_reuse(monkeypatch)
    resume_archived.in_tmux(n, Config())
    row = _row(n.id)
    archived: list[str] = []
    item = (
        row.channel,
        row.metadata["session_id"],
        row.metadata["cwd"],
        row.created_at,
        True,
        row.metadata["tty"],
        row.message,
        row.switch_source,
    )
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda *a: True)

    watcher._archive_stale_sessions(
        [item],
        archived.append,
        sockets={},
        pane_locations={None: _NEW_PANE},
        session_orders={row.channel: tuple(row.metadata["tmux_session_order"])},
    )

    assert archived == []


def test_scratch_pane_enter_starts_the_session(monkeypatch, tmp_path):
    n = _archived(tmp_path)
    _no_session_to_reuse(monkeypatch)
    copied: list = []
    monkeypatch.setattr(LemonaidApp, "_copy_resume_command", lambda self, c: copied.append(c))
    monkeypatch.setattr(LemonaidApp, "_hide_scratch_pane", lambda self: None)
    monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 20)) as pilot:
            app._scratch_mode = True
            app._set_history_mode(True)
            await pilot.pause()
            app._resume_session()
            await pilot.pause()

    asyncio.run(run())
    assert _row(n.id).status == "unread"
    assert _row(n.id).metadata["tty"] == "/dev/ttys977"
    assert copied == []


def test_scratch_pane_failure_is_shown(monkeypatch, tmp_path):
    _archived(tmp_path)
    monkeypatch.setattr(resume_archived.tmux.recreate, "resume", lambda *a: None)
    monkeypatch.setattr(resume_archived.tmux.session, "spawn_resumed", lambda *a: ("no tmux", None))
    monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 20)) as pilot:
            app._scratch_mode = True
            app._set_history_mode(True)
            await pilot.pause()
            app._resume_session()
            await pilot.pause()
            return app.screen

    assert isinstance(asyncio.run(run()), ResumeErrorScreen)


def test_resuming_in_this_terminal_records_it(monkeypatch, tmp_path):
    """Outside the scratch pane the session replaces lma in its own tmux pane."""
    n = _archived(tmp_path)
    monkeypatch.setattr("lemonaid.inbox.tui.app.navigation.is_inside_tmux", lambda: True)
    monkeypatch.setattr("lemonaid.inbox.tui.app.navigation.locations_by_tty", lambda *a: _NEW_PANE)
    monkeypatch.setattr("lemonaid.inbox.tui.app.os.isatty", lambda fd: True)
    monkeypatch.setattr("lemonaid.inbox.tui.app.os.ttyname", lambda fd: "/dev/ttys977")
    monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 20)) as pilot:
            app._scratch_mode = False
            app._set_history_mode(True)
            await pilot.pause()
            app._resume_session()
            await pilot.pause()
        return app._exec_on_exit

    assert asyncio.run(run())[1][:2] == ["codex", "resume"]
    assert _row(n.id).metadata["tty"] == "/dev/ttys977"
    assert _row(n.id).metadata["tmux_session"] == "cost"


def test_a_session_on_another_server_moves_to_this_one(monkeypatch, tmp_path):
    """The watcher looks a row's tty up on its recorded server."""
    n = _archived(tmp_path)
    with db.connect() as conn:
        conn.execute(
            "UPDATE notifications SET metadata = json_set(metadata, '$.tmux_socket', ?) "
            "WHERE id = ?",
            ("/tmp/tmux-old/default", n.id),
        )
        conn.commit()
        n = db.get(conn, n.id)
    _no_session_to_reuse(monkeypatch)

    resume_archived.in_tmux(n, Config())

    assert _row(n.id).metadata["tmux_socket"] == "/nonexistent/lemonaid-tests"
