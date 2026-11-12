"""A harness that stops unasked while its pane and server run is kept for restore."""

import argparse
import json

import pytest

from lemonaid import tmux
from lemonaid.brief import attached
from lemonaid.config import Config
from lemonaid.hooks import end_reports
from lemonaid.inbox import db, ended
from lemonaid.inbox.tui.watchers import watcher_hooks
from lemonaid.restore import auto, cli, dismiss

_SOCKET = "/tmp/recorded/default"
_EXITED = "process-exited tty=/dev/ttys900"


@pytest.fixture(autouse=True)
def running_server(monkeypatch):
    monkeypatch.setattr(tmux.server, "started", lambda socket: 100)
    monkeypatch.setattr(end_reports, "reported", lambda harness, cwd: harness == "claude")


def _row(channel: str, **metadata: object) -> None:
    with db.connect() as conn:
        db.add(
            conn,
            channel,
            "waiting",
            metadata={
                "tty": "/dev/ttys900",
                "cwd": "/tmp",
                "session_id": channel.partition(":")[2],
                "tmux_socket": _SOCKET,
                "tmux_session_order": [5, 100, 1],
                **metadata,
            },
            upsert=False,
            switch_source="tmux",
        )


def _cause(channel: str) -> tuple[str, str]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, metadata FROM notifications WHERE channel = ?", (channel,)
        ).fetchone()
    return row["status"], ended.cause(json.loads(row["metadata"]))


@pytest.mark.parametrize(
    ("channel", "report", "why", "expected"),
    [
        pytest.param("claude:a", {}, _EXITED, ("unread", ended.CRASHED), id="no-report"),
        pytest.param(
            "claude:a",
            {"exit_reason": "other", "exit_deliberate": False},
            _EXITED,
            ("unread", ended.CRASHED),
            id="signal",
        ),
        pytest.param(
            "claude:a",
            {"exit_reason": "other"},
            _EXITED,
            ("unread", ended.CRASHED),
            id="signal-recorded-before-upgrade",
        ),
        pytest.param(
            "claude:a",
            {"exit_reason": "prompt_input_exit"},
            _EXITED,
            ("archived", ended.USER_EXIT),
            id="quit-recorded-before-upgrade",
        ),
        pytest.param(
            "claude:a",
            {"exit_reason": "prompt_input_exit", "exit_deliberate": True},
            _EXITED,
            ("archived", ended.USER_EXIT),
            id="quit",
        ),
        pytest.param(
            "claude:a",
            {},
            "pane-gone tty=/dev/ttys900",
            ("archived", ended.PANE_CLOSED),
            id="pane-closed",
        ),
        pytest.param(
            "codex:a", {}, _EXITED, ("archived", ended.PROCESS_EXITED), id="harness-not-reporting"
        ),
    ],
)
def test_a_stop_without_a_quit_report_is_a_crash(channel, report, why, expected):
    _row(channel, **report)

    watcher_hooks.archive_channel(channel, why)

    assert _cause(channel) == expected


def test_only_the_newest_lemon_on_a_tty_crashed():
    _row("claude:old")
    _row("claude:new")

    watcher_hooks.archive_channel("claude:old", _EXITED)
    watcher_hooks.archive_channel("claude:new", _EXITED)

    assert _cause("claude:old") == ("archived", ended.PROCESS_EXITED)
    assert _cause("claude:new") == ("unread", ended.CRASHED)


def test_a_crashed_lemon_is_restored_and_can_be_dismissed(capsys):
    _row("claude:a")
    watcher_hooks.archive_channel("claude:a", _EXITED)

    assert [row.channel for row in cli._lost(dry_run=False)] == ["claude:a"]
    assert "claude:a" not in [row[0] for row in watcher_hooks.active_sessions()]

    dismiss.cmd_dismiss(argparse.Namespace(all=True, lemons=[]))

    assert _cause("claude:a") == ("archived", ended.DISMISSED)


def test_a_lemon_whose_brief_is_done_is_archived_rather_than_crashed(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("# Work\n\nStatus: done\n")
    _row("claude:a")
    with db.connect() as conn:
        attached.attach(conn, "claude:a", brief)

    watcher_hooks.archive_channel("claude:a", _EXITED)

    assert _cause("claude:a") == ("archived", ended.PROCESS_EXITED)


def test_a_lemon_killed_with_its_server_stays_lost(monkeypatch):
    monkeypatch.setattr(tmux.server, "started", lambda socket: tmux.server.GONE)
    _row("claude:a", exit_reason="other", exit_deliberate=False)

    assert [row.channel for row in cli._lost(dry_run=False)] == ["claude:a"]
    assert _cause("claude:a") == ("unread", ended.SERVER_LOST)


def test_a_trigger_leaves_a_crash_alone(monkeypatch):
    monkeypatch.setattr(cli, "load_config", Config)
    _row("claude:a")
    watcher_hooks.archive_channel("claude:a", _EXITED)

    cli.cmd_restore(argparse.Namespace(dry_run=False, auto=True, into_running=False))

    with db.connect() as conn:
        assert db.get_by_channel(conn, auto.ASK_CHANNEL, unread_only=False) is None
    assert _cause("claude:a") == ("unread", ended.CRASHED)
