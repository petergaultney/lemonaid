"""A lemon mid-turn shows as working, whatever its brief's Status says, until the turn ends."""

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from lemonaid import claude, codex
from lemonaid.brief import attached, render, target
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db, turns
from lemonaid.inbox.tui import brief_questions, brief_view
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.lemon_watchers import watcher


def _newest_first(*entries: dict) -> list[dict]:
    return list(reversed(entries))


_PROMPT = {"type": "user", "message": {"content": "go on"}}
_REPLY = {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}
_TURN_END = {"type": "system", "subtype": "turn_duration"}


def test_a_claude_turn_ends_with_its_turn_duration():
    assert claude.watcher.turn_open(_newest_first(_PROMPT, _REPLY, _TURN_END)) is False


def test_a_claude_turn_is_open_from_its_prompt():
    assert claude.watcher.turn_open(_newest_first(_TURN_END, _PROMPT)) is True


def test_a_background_task_wake_opens_a_claude_turn():
    wake = {"type": "user", "message": {"content": "<task-notification>\n<task-id>b1</task-id>"}}

    assert claude.watcher.turn_open(_newest_first(_TURN_END, wake)) is True


@pytest.mark.parametrize(
    "content",
    ["<command-name>/model</command-name>", "<local-command-stdout>x</local-command-stdout>"],
)
def test_a_slash_command_after_a_turn_opens_none(content):
    command = {"type": "user", "message": {"content": content}}

    assert claude.watcher.turn_open(_newest_first(_TURN_END, command)) is False


def test_a_claude_tail_with_no_turn_entries_says_nothing():
    assert claude.watcher.turn_open([{"type": "attachment"}]) is None


def _event(kind: str) -> dict:
    return {"type": "event_msg", "payload": {"type": kind}}


_TOOL_CALL = {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec"}}


def test_a_codex_turn_runs_from_task_started_to_task_complete():
    assert codex.watcher.turn_open(_newest_first(_event("task_started"), _TOOL_CALL)) is True
    assert (
        codex.watcher.turn_open(
            _newest_first(_event("task_started"), _TOOL_CALL, _event("task_complete"))
        )
        is False
    )


def test_an_aborted_codex_turn_is_over():
    assert codex.watcher.turn_open(_newest_first(_TOOL_CALL, _event("turn_aborted"))) is False


def test_a_codex_turn_longer_than_the_tail_is_open():
    assert codex.watcher.turn_open([_TOOL_CALL] * 50) is True


def test_a_codex_tail_with_only_bookkeeping_says_nothing():
    assert codex.watcher.turn_open([_event("token_count")]) is None


def _row(turn_at: float | None, status: str = "read") -> db.Notification:
    return db.Notification(1, "claude:a", "", status=status, turn_at=turn_at)


def test_a_row_is_mid_turn_while_its_transcript_is_fresh():
    now = time.time()

    assert turns.mid_turn(_row(now - 5), now)
    assert not turns.mid_turn(_row(None), now)
    assert not turns.mid_turn(_row(now - turns.STALE_SECONDS - 1), now)


def test_an_unread_row_is_not_mid_turn():
    """Its lemon stopped to ask for something, a permission prompt say, inside the turn."""
    now = time.time()

    assert not turns.mid_turn(_row(now, status="unread"), now)


@pytest.mark.parametrize(
    ("status", "shown"),
    [
        ("blocked", "working"),
        ("alert", "working"),
        ("merge", "working"),
        ("waiting", "working"),
        ("running", "running"),
        ("", ""),
    ],
)
def test_a_mid_turn_lemon_shows_working_unless_running(status, shown):
    assert turns.shown(status) == shown


def test_the_watch_loop_records_a_turn_and_its_end(tmp_path, monkeypatch):
    session = tmp_path / "session.jsonl"
    session.write_text(
        "\n".join(
            json.dumps({**entry, "timestamp": ts})
            for entry, ts in (
                (_PROMPT, "2026-10-01T18:00:00Z"),
                (_REPLY, "2026-10-01T18:00:05Z"),
            )
        )
    )

    class Backend:
        CHANNEL_PREFIX = "claude:"
        get_session_path = staticmethod(lambda _session_id, _cwd: session)
        describe_activity = staticmethod(lambda _entry: None)
        should_dismiss = staticmethod(lambda _entry: False)
        turn_open = staticmethod(claude.watcher.turn_open)

    recorded: list[float | None] = []
    polls = 0

    def finish_poll(_seconds: float) -> None:
        nonlocal polls
        polls += 1
        if polls == 1:
            with session.open("a") as f:
                f.write("\n" + json.dumps({**_TURN_END, "timestamp": "2026-10-01T18:00:06Z"}))
            return

        if polls == 2:
            return

        raise StopIteration

    monkeypatch.setattr(watcher.time, "sleep", finish_poll)

    with pytest.raises(StopIteration):
        watcher.unified_watch_loop(
            [Backend],
            lambda: [("claude:abc", "abc", "/tmp", 0.0, False, None, "", None)],
            lambda _channel: 0,
            lambda _channel, _message: 0,
            record_turn=lambda _channel, at: recorded.append(at),
            poll_interval=0,
        )

    assert recorded == [watcher.parse_timestamp("2026-10-01T18:00:05Z"), None]


@pytest.fixture(autouse=True)
def _keep_sessions(monkeypatch):
    """The test tmux has none of these ttys, so the watcher would archive every row."""
    monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)


def _session(conn, name: str, status: str, created_at: float) -> str:
    channel = f"claude:{name}"
    n = db.add(conn, channel, "a message", name, {"tty": f"/dev/ttys-{name}", "cwd": "/tmp"})
    conn.execute(
        "UPDATE notifications SET switch_source = 'tmux', status = 'read', created_at = ? WHERE id = ?",
        (created_at, n.id),
    )
    conn.commit()
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# work\n\nStatus: {status}\n\n## Now\n\n### Needs Peter\n\n- an answer\n")
    attached.attach(conn, channel, path)
    return channel


def _cards(mid_turn_working: bool = True) -> dict[str, tuple[int, str, str]]:
    """Each channel's drawn position, and the status and need on its card."""
    Path(os.environ["LEMONAID_CONFIG"]).write_text(
        f"[tui]\nmid_turn_working = {str(mid_turn_working).lower()}\n"
    )

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(60, 40)) as pilot:
            await pilot.pause()
            with db.connect() as conn:
                rows, cards = app._ordered_active(conn, None)
            return {
                n.channel: (i, cards[n.channel].status, cards[n.channel].needs)
                for i, n in enumerate(rows)
            }

    return asyncio.run(run())


def test_a_mid_turn_blocked_lemon_sorts_and_shows_as_working():
    with db.connect() as conn:
        idle = _session(conn, "idle", "blocked", time.time() - 100)
        busy = _session(conn, "busy", "blocked", time.time() - 50)
        newer = _session(conn, "newer", "working", time.time())
        db.record_turn(conn, busy, time.time())

    cards = _cards()

    assert cards[idle] == (0, "blocked", "an answer")
    assert cards[busy][1:] == ("working", "")
    assert cards[newer][0] < cards[busy][0]  # among the read working rows, newest first


def test_by_default_a_mid_turn_lemon_keeps_its_brief_status():
    with db.connect() as conn:
        idle = _session(conn, "idle", "blocked", time.time() - 100)
        busy = _session(conn, "busy", "blocked", time.time() - 50)
        newer = _session(conn, "newer", "working", time.time())
        db.record_turn(conn, busy, time.time())

    cards = _cards(mid_turn_working=False)

    assert cards[busy] == (0, "blocked", "an answer")
    assert cards[idle] == (1, "blocked", "an answer")
    assert cards[newer][1] == "working"


def test_the_brief_status_applies_again_once_the_turn_ends():
    with db.connect() as conn:
        busy = _session(conn, "busy", "blocked", time.time())
        db.record_turn(conn, busy, time.time())
        db.record_turn(conn, busy, None)

    assert _cards()[busy][1] == "blocked"


_ASKING = """# work

Status: blocked

## Now

### Needs Peter

- Pick a name: which one?

## Questions

### Pick a name

- **Context:** two candidates.
"""


def _view(path) -> render.View:
    return render.view(
        target.Target([path], [path.parent], None, [], "work"), time.time(), dict().get
    )


def test_the_brief_view_of_a_mid_turn_lemon_asks_for_nothing():
    with db.connect() as conn:
        busy = _session(conn, "busy", "blocked", time.time())
        db.record_turn(conn, busy, time.time())
    path = brief_store.briefs_dir() / "busy.md"
    path.write_text(_ASKING)
    assert brief_questions.choices(_view(path).sections)
    assert "Pick a name" in render.to_markdown(_view(path), time.time(), expanded=True)

    shown = brief_view._mid_turn(_view(path), time.time())

    assert [s.state for s in shown.sections] == ["working"]
    assert "Pick a name" not in render.to_markdown(shown, time.time(), expanded=True)
    assert not brief_questions.choices(shown.sections)

    with db.connect() as conn:
        db.record_turn(conn, busy, None)

    assert brief_questions.choices(brief_view._mid_turn(_view(path), time.time()).sections)
