"""Enter on a history row whose session never actually stopped.

Archiving is a guess made from outside: a watcher that could not find the pane.
It is wrong often enough that history fills with sessions still running, and
resuming one of those started a second copy beside the first. A live session
wants returning to the inbox and switching to, not resuming.
"""

import asyncio
import itertools

from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.error_screen import ErrorScreen
from lemonaid.lemon_watchers import watcher

_ttys = itertools.count(900)


def _archived(tty: str | None = None, socket: str | None = None) -> int:
    """An archived session on a tty no other test and no real pane will match.

    A tty shared with another test's row - or with a pane on the machine running
    this - makes the liveness check answer about something else, which is the
    exact thing these tests assert on.
    """
    tty = tty or f"/dev/ttys{next(_ttys)}"
    metadata = {"tty": tty, "cwd": "/tmp", "session_id": f"abc{next(_ttys)}"}
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


def _run(steps, size=(120, 20), monkeypatch=None):
    """Run the app with auto-archiving disabled for its invented TTYs.

    These tests assert on a row's status, and the watcher archives any row whose
    tty has no pane - which is every row here, since the ttys are invented.
    """
    if monkeypatch is not None:
        monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def _pane_and_process(monkeypatch, pane: bool, process: bool | None = None) -> None:
    monkeypatch.setattr("lemonaid.inbox.unarchive.check_pane_exists_by_tty", lambda *a: pane)
    monkeypatch.setattr(
        watcher, "is_process_running_on_tty", lambda *a: pane if process is None else process
    )


def _status(nid: int) -> str:
    with db.connect() as conn:
        return db.get(conn, nid).status


def test_a_live_session_goes_back_to_the_inbox(monkeypatch):
    """A still-running archived session is returned to the active inbox."""
    nid = _archived()
    _pane_and_process(monkeypatch, True)
    monkeypatch.setattr("lemonaid.inbox.tui.app.handle_notification", lambda *a, **k: True)

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        app._resume_session()
        await pilot.pause()

    _run(steps, monkeypatch=monkeypatch)
    assert _status(nid) == "unread"


def test_a_live_session_is_switched_to_not_resumed(monkeypatch):
    """The whole point: it is already running, so starting it again is a duplicate."""
    _archived()
    switched: list = []
    resumed: list = []
    _pane_and_process(monkeypatch, True)
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

    _run(steps, monkeypatch=monkeypatch)
    assert switched
    assert not resumed


def test_a_dead_session_still_resumes(monkeypatch):
    """The existing behaviour has to survive: this one really is gone."""
    _archived()
    resumed: list = []
    _pane_and_process(monkeypatch, False)
    monkeypatch.setattr(
        "lemonaid.inbox.tui.app.resume_mod.build_resume_command",
        lambda *a: resumed.append(a) or None,
    )

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        app._resume_session()
        await pilot.pause()

    _run(steps, monkeypatch=monkeypatch)
    assert resumed


def test_the_recorded_server_is_the_one_asked(monkeypatch):
    """A pane on another tmux server is absent from this one's listing, which is
    exactly the misreading that archived it in the first place."""
    _archived(socket="/tmp/tmux-1/other")
    asked: list = []
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda *a: True)
    monkeypatch.setattr(
        "lemonaid.inbox.unarchive.check_pane_exists_by_tty",
        lambda tty, src, socket=None, not_after=None: asked.append(socket) or True,
    )
    monkeypatch.setattr("lemonaid.inbox.tui.app.handle_notification", lambda *a, **k: True)

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        app._resume_session()
        await pilot.pause()

    _run(steps, monkeypatch=monkeypatch)
    assert asked == ["/tmp/tmux-1/other"]


def test_copying_a_command_never_switches(monkeypatch):
    """`copy` asks for the text of a resume command, whatever the session is doing."""
    _archived()
    switched: list = []
    _pane_and_process(monkeypatch, True)
    monkeypatch.setattr(
        "lemonaid.inbox.tui.app.handle_notification", lambda *a, **k: switched.append(a) or True
    )
    monkeypatch.setattr("lemonaid.inbox.tui.app.resume_mod.build_resume_command", lambda *a: None)

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        app._resume_session(copy_only=True)
        await pilot.pause()

    _run(steps, monkeypatch=monkeypatch)
    assert not switched


def test_a_pane_left_at_a_shell_prompt_resumes(monkeypatch):
    """The pane outliving its harness is a shell, not the session, to switch to."""
    _archived()
    switched: list = []
    resumed: list = []
    _pane_and_process(monkeypatch, True, process=False)
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

    _run(steps, monkeypatch=monkeypatch)
    assert resumed
    assert not switched


def test_a_session_with_nowhere_to_resume_says_so(monkeypatch):
    """Enter on a dead session with no recorded cwd pops up why, rather than doing nothing."""
    _archived()
    _pane_and_process(monkeypatch, False)
    monkeypatch.setattr("lemonaid.inbox.tui.app.resume_mod.build_resume_command", lambda *a: None)

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        app._resume_session()
        await pilot.pause()
        return type(app.screen)

    assert _run(steps, monkeypatch=monkeypatch) is ErrorScreen


def test_a_failed_switch_says_so_until_dismissed(monkeypatch):
    _archived()
    _pane_and_process(monkeypatch, True)
    monkeypatch.setattr("lemonaid.inbox.tui.app.handle_notification", lambda *a, **k: False)

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        app._resume_session()
        await pilot.pause()
        shown = type(app.screen)
        await pilot.press("x")
        await pilot.pause()
        return shown, type(app.screen)

    shown, after = _run(steps, monkeypatch=monkeypatch)
    assert shown is ErrorScreen
    assert after is not ErrorScreen
