"""`tell` says whether its recipient will read the message, and fails when it won't."""

import argparse
import subprocess
import time

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db
from lemonaid.messages import cli, recipient, store, waiter


@pytest.fixture(autouse=True)
def _sender(monkeypatch):
    for name in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX_PANE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:sender")
    monkeypatch.setattr(cli.service, "ensure_running", lambda: None)


def _attach(channel: str, metadata: dict, turn_at: float | None = None) -> str:
    path = brief_store.briefs_dir() / "recipient.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# recipient\n")
    with db.connect() as conn:
        db.add(conn, channel, "", metadata=metadata)
        if turn_at is not None:
            conn.execute(
                "UPDATE notifications SET turn_at = ?, status = 'read' WHERE channel = ?",
                (turn_at, channel),
            )
            conn.commit()
        attached.attach(conn, channel, path)
        return identity.ensure(conn, path)


def _tell(target: str) -> int:
    parser = argparse.ArgumentParser()
    cli.add_tell_parser(parser.add_subparsers())
    args = parser.parse_args(["tell", target, "hello"])
    try:
        args.func(args)
    except SystemExit as exit:
        return int(exit.code or 0)

    return 0


def test_claude_with_an_armed_waiter_is_listening(capsys):
    lemon_id = _attach("claude:listener", {})
    with waiter.armed(store.inbox_for_id(lemon_id)):
        assert _tell("claude:listener") == 0

    assert "listening" in capsys.readouterr().err


def test_idle_claude_without_a_waiter_is_deaf_and_tell_fails(capsys):
    _attach("claude:deaf", {})

    assert _tell("claude:deaf") == 1
    assert "deaf, it is idle" in capsys.readouterr().err


def test_claude_mid_turn_is_fine(capsys):
    _attach("claude:busy", {}, turn_at=time.time())

    assert _tell("claude:busy") == 0
    assert "mid-turn" in capsys.readouterr().err


def test_no_harness_on_the_recorded_tty_is_dead(capsys, monkeypatch):
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["-fish"])
    _attach("codex:gone", {"tty": "/dev/ttys999"})

    assert _tell("codex:gone") == 1
    assert "dead, its harness" in capsys.readouterr().err


def test_codex_with_a_live_harness_is_listening(capsys, monkeypatch):
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["-fish", "codex"])
    _attach("codex:live", {"tty": "/dev/ttys998"})

    assert _tell("codex:live") == 0
    assert "listening" in capsys.readouterr().err


def test_message_is_queued_even_when_it_will_not_be_read(capsys):
    lemon_id = _attach("claude:deaf", {})

    _tell("claude:deaf")

    assert store.peek_next(store.inbox_for_id(lemon_id)) is not None


@pytest.mark.parametrize(
    ("command", "expected"),
    [("claude", True), ("2.1.295", True), ("/opt/bin/codex", True), ("-fish", False), ("1", False)],
)
def test_harness_names(command, expected):
    assert recipient._is_harness(command) is expected


def test_dead_harness_outranks_an_armed_waiter():
    row = db.Notification(id=1, channel="claude:x", message="")

    assert recipient.classify("claude:x", row, False, True, time.time()).state == recipient.DEAD


def test_unattached_recipient_has_not_started():
    assert recipient.classify("", None, None, False, time.time()).state == recipient.NOT_STARTED


def _ps_fails(monkeypatch, returncode: int, stderr: str) -> None:
    monkeypatch.setattr(
        recipient.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, returncode, "", stderr),
    )


def test_ps_that_errors_on_a_present_tty_is_unknown(monkeypatch, tmp_path):
    _ps_fails(monkeypatch, 1, "ps: illegal argument")
    monkeypatch.setattr(recipient.Path, "exists", lambda path: True)

    assert recipient._tty_commands("/dev/ttys001") is None


def test_ps_that_errors_on_a_missing_tty_means_nothing_runs_there(monkeypatch):
    _ps_fails(monkeypatch, 1, "ps: illegal argument")
    monkeypatch.setattr(recipient.Path, "exists", lambda path: False)

    assert recipient._tty_commands("/dev/ttys001") == []


def test_ps_with_no_match_means_nothing_runs_there(monkeypatch):
    _ps_fails(monkeypatch, 1, "")

    assert recipient._tty_commands("/dev/ttys001") == []


def test_other_harnesses_are_unknown_even_without_a_process():
    row = db.Notification(id=1, channel="opencode:x", message="")

    assert (
        recipient.classify("opencode:x", row, False, False, time.time()).state == recipient.UNKNOWN
    )
