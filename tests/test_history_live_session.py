"""Enter on a history row whose session never actually stopped.

Archiving is a guess made from outside: a watcher that could not find the pane.
It is wrong often enough that history fills with sessions still running, and
resuming one of those started a second copy beside the first. A live session
wants returning to the inbox and switching to, not resuming.
"""

import asyncio

from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp


def _archived(tty: str = "/dev/ttys001", socket: str | None = None) -> int:
    metadata = {"tty": tty, "cwd": "/tmp", "session_id": "abc123"}
    if socket:
        metadata["tmux_socket"] = socket

    with db.connect() as conn:
        n = db.add(conn, "claude:live", "a message", "a-session", metadata)
        conn.execute(
            "UPDATE notifications SET status = 'archived', switch_source = 'tmux' WHERE id = ?",
            (n.id,),
        )
        conn.commit()
        return n.id


def _run(steps, size=(120, 20)):
    async def run():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def _status(nid: int) -> str:
    with db.connect() as conn:
        return db.get(conn, nid).status


def test_a_live_session_goes_back_to_the_inbox(monkeypatch):
    nid = _archived()
    monkeypatch.setattr("lemonaid.inbox.tui.app.check_pane_exists_by_tty", lambda *a: True)
    monkeypatch.setattr("lemonaid.inbox.tui.app.handle_notification", lambda *a, **k: True)

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        app._resume_session()
        await pilot.pause()

    _run(steps)
    assert _status(nid) == "unread"


def test_a_live_session_is_switched_to_not_resumed(monkeypatch):
    """The whole point: it is already running, so starting it again is a duplicate."""
    _archived()
    switched: list = []
    resumed: list = []
    monkeypatch.setattr("lemonaid.inbox.tui.app.check_pane_exists_by_tty", lambda *a: True)
    monkeypatch.setattr(
        "lemonaid.inbox.tui.app.handle_notification", lambda *a, **k: switched.append(a) or True
    )
    monkeypatch.setattr(
        "lemonaid.inbox.tui.app.resume_mod.build_resume_command",
        lambda *a: resumed.append(a) or None,
    )

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        app._resume_session()
        await pilot.pause()

    _run(steps)
    assert switched
    assert not resumed


def test_a_dead_session_still_resumes(monkeypatch):
    """The existing behaviour has to survive: this one really is gone."""
    _archived()
    resumed: list = []
    monkeypatch.setattr("lemonaid.inbox.tui.app.check_pane_exists_by_tty", lambda *a: False)
    monkeypatch.setattr(
        "lemonaid.inbox.tui.app.resume_mod.build_resume_command",
        lambda *a: resumed.append(a) or None,
    )

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        app._resume_session()
        await pilot.pause()

    _run(steps)
    assert resumed


def test_the_recorded_server_is_the_one_asked(monkeypatch):
    """A pane on another tmux server is absent from this one's listing, which is
    exactly the misreading that archived it in the first place."""
    _archived(socket="/tmp/tmux-1/other")
    asked: list = []
    monkeypatch.setattr(
        "lemonaid.inbox.tui.app.check_pane_exists_by_tty",
        lambda tty, src, socket=None: asked.append(socket) or True,
    )
    monkeypatch.setattr("lemonaid.inbox.tui.app.handle_notification", lambda *a, **k: True)

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        app._resume_session()
        await pilot.pause()

    _run(steps)
    assert asked == ["/tmp/tmux-1/other"]


def test_copying_a_command_never_switches(monkeypatch):
    """`copy` asks for the text of a resume command, whatever the session is doing."""
    _archived()
    switched: list = []
    monkeypatch.setattr("lemonaid.inbox.tui.app.check_pane_exists_by_tty", lambda *a: True)
    monkeypatch.setattr(
        "lemonaid.inbox.tui.app.handle_notification", lambda *a, **k: switched.append(a) or True
    )
    monkeypatch.setattr("lemonaid.inbox.tui.app.resume_mod.build_resume_command", lambda *a: None)

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        app._resume_session(copy_only=True)
        await pilot.pause()

    _run(steps)
    assert not switched
