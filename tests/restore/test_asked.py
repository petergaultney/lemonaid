"""Showing a lemon a running restore has yet to bring back asks the restore for it next,
and never resumes it beside the restore."""

import asyncio

from lemonaid import front_end, handlers
from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.switching.resume_error import ResumeErrorScreen
from lemonaid.restore import asked, auto


def _lost(channel: str) -> db.Notification:
    with db.connect() as conn:
        db.add(
            conn,
            channel,
            "waiting",
            "lost one",
            {"cwd": "/work/feat", "tty": "/dev/ttys1", "session_id": "abc"},
            switch_source="tmux",
        )
        db.mark_lost(conn, channel, "test", "")
        row = db.get_by_channel(conn, channel, unread_only=False)
    assert row is not None
    return row


def test_a_lemon_restore_will_bring_back_is_asked_for_only_while_a_restore_runs():
    row = _lost("claude:lost")
    assert asked.ask(row.channel, row.metadata, "lost one") == ""

    with auto.lock() as held:
        assert held
        assert asked.ask("claude:live", {}, "live one") == ""
        told = asked.ask(row.channel, row.metadata, "lost one")

    assert told == "lost one is still lost; the restore running now starts it next"
    assert asked.channels() == {"claude:lost"}


def test_showing_it_while_a_restore_runs_never_resumes_it(monkeypatch):
    row = _lost("claude:lost")
    calls: list[str] = []
    monkeypatch.setattr(handlers.tmux.recorded_pane, "locate", lambda m: (None, None))
    monkeypatch.setattr(handlers.tmux.recorded_pane, "has_identity", lambda m: True)
    monkeypatch.setattr(
        handlers.tmux.recreate, "recreate", lambda m, c: calls.append("recreate") or True
    )
    monkeypatch.setattr(handlers.tmux.recreate, "resume", lambda m, c: calls.append("resume"))
    metadata = {**row.metadata, "channel": row.channel, "name": "lost one"}

    assert front_end.tmux.show(metadata, Config()) is True  # no restore runs: it resumes
    with auto.lock():
        assert front_end.tmux.show(metadata, Config()) is False
        assert front_end.tmux.show(metadata, Config(), on_resume=calls.append) is False

    assert calls == ["recreate"]
    assert asked.channels() == {"claude:lost"}


def test_the_inbox_says_restore_starts_it_next_instead_of_offering_a_resume(monkeypatch):
    row = _lost("claude:lost")
    monkeypatch.setattr(
        "lemonaid.inbox.tui.switching.inbox_switch.handle_notification", lambda *a, **k: False
    )

    async def run() -> tuple[type, list[str]]:
        app = LemonaidApp()
        told: list[str] = []
        monkeypatch.setattr(app, "notify", lambda message, **kwargs: told.append(message))
        async with app.run_test(size=(120, 20)) as pilot:
            await pilot.pause()
            assert app._switch_to_notification(row)
            await pilot.pause()
            return type(app.screen), told

    with auto.lock():
        shown, told = asyncio.run(run())

    assert shown is not ResumeErrorScreen
    assert told == ["lost one is still lost; the restore running now starts it next"]
