"""`tell` starts a recipient that won't read its message, unless it finished its work."""

import argparse
import json

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.messages import (
    autoresume,
    autoresume_cmux,
    autoresume_tmux,
    cli,
    dead_letters,
    recipient,
)
from lemonaid.messages_config import MessagesConfig


@pytest.fixture(autouse=True)
def _sender(monkeypatch):
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:sender")
    monkeypatch.setattr(cli.service, "ensure_running", lambda: None)
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["-fish"])  # nothing runs there


@pytest.fixture
def started(monkeypatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(autoresume_tmux, "start", lambda row, config: calls.append("start") or "")
    monkeypatch.setattr(autoresume_tmux, "prompt", lambda row, config: calls.append("prompt") or "")
    return calls


def _attach(channel: str, brief: str, **metadata) -> None:
    path = brief_store.briefs_dir() / "recipient.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(brief)
    with db.connect() as conn:
        db.add(
            conn, channel, "", metadata={"tty": "/dev/ttys900", **metadata}, switch_source="tmux"
        )
        attached.attach(conn, channel, path)
        identity.ensure(conn, path)


def _tell(target: str) -> int:
    parser = argparse.ArgumentParser()
    cli.add_tell_parser(parser.add_subparsers())
    args = parser.parse_args(["tell", target, "hello"])
    try:
        args.func(args)
    except SystemExit as exit:
        return int(exit.code or 0)

    return 0


def _posted() -> str:
    with db.connect() as conn:
        row = db.get_by_channel(conn, autoresume.CHANNEL, unread_only=False)
    return row.message if row else ""


def test_a_dead_working_lemon_is_started_and_tell_succeeds(capsys, started):
    _attach("claude:gone", "# t\n\nStatus: working\n\n## Now\n\n- fixing\n")

    assert _tell("claude:gone") == 0
    assert started == ["start"]
    err = capsys.readouterr().err
    assert "last status was working; lemonaid started a resume for you" in err
    assert "started a resume for you" in _posted()


def test_a_deaf_lemon_is_prompted(capsys, started, monkeypatch):
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["claude"])
    _attach("claude:idle", "# t\n\nStatus: waiting\n")

    assert _tell("claude:idle") == 0
    assert started == ["prompt"]
    assert "prompted it to read the message" in capsys.readouterr().err


def test_a_done_lemon_is_left_alone_with_its_status_and_resume_command(capsys, started):
    _attach(
        "claude:finished",
        "# t\n\nStatus: done\n\n## Now\n\n### Done\n\n- PR merged\n",
        cwd="/tmp",
        session_id="abc",
    )

    assert _tell("claude:finished") == 1
    assert started == []
    err = capsys.readouterr().err
    assert "was marked done (Status: done; Now: PR merged)" in err
    assert "run: cd /tmp && lemonaid claude resume abc" in err


def test_a_failed_start_tells_the_sender_whom_to_inform(capsys, monkeypatch):
    monkeypatch.setattr(
        autoresume_tmux, "start", lambda row, config: "no tmux session is recorded for it"
    )
    _attach("codex:gone", "# t\n\nStatus: working\n")

    assert _tell("codex:gone") == 1
    err = capsys.readouterr().err
    assert "could not start it: no tmux session is recorded for it" in err
    assert "tell your user, your parent if you have one, or both" in err
    assert "could not start it" in _posted()


def test_autoresume_off_names_the_recovery_step(capsys, started, monkeypatch):
    monkeypatch.setattr(
        cli, "load_config", lambda: Config(messages=MessagesConfig(autoresume=frozenset()))
    )
    _attach("claude:gone", "# t\n\nStatus: working\n")

    assert _tell("claude:gone") == 1
    assert started == []
    assert "ask your user to resume it" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("state", "harness", "status", "archived", "harnesses", "expected"),
    [
        (recipient.DEAD, "claude", "working", False, frozenset({"claude"}), autoresume.START),
        (recipient.DEAF, "claude", "waiting", False, frozenset({"claude"}), autoresume.PROMPT),
        (recipient.DEAD, "codex", "working", False, frozenset({"claude"}), autoresume.OFF),
        (recipient.DEAD, "claude", "done", False, frozenset({"claude"}), autoresume.FINISHED),
        (recipient.DEAD, "claude", "working", True, frozenset({"claude"}), autoresume.FINISHED),
        (recipient.ASKING, "claude", "working", False, frozenset({"claude"}), autoresume.ASKING),
    ],
)
def test_plan(state, harness, status, archived, harnesses, expected):
    assert autoresume.plan(state, harness, status, archived, harnesses) == expected


def test_a_second_tell_while_it_starts_does_not_start_it_again(capsys, started):
    _attach("claude:gone", "# t\n\nStatus: working\n")

    assert _tell("claude:gone") == 0
    assert _tell("claude:gone") == 0
    assert started == ["start"]
    assert "already being started" in capsys.readouterr().err


def test_a_lemon_at_a_question_is_not_typed_into(capsys, started, monkeypatch):
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["claude"])
    _attach("claude:asking", "# t\n\nStatus: working\n")
    with db.connect() as conn:
        db.record_turn(conn, "claude:asking", 1.0)  # a turn left open long ago

    assert _tell("claude:asking") == 1
    assert started == []
    assert "stopped mid-turn to ask its user" in capsys.readouterr().err


def test_a_snoozed_lemon_stays_snoozed_through_its_resume(started):
    _attach("claude:gone", "# t\n\nStatus: working\n")
    with db.connect() as conn:
        row = db.get_by_channel(conn, "claude:gone", unread_only=False)
        conn.execute(
            "UPDATE notifications SET status = 'snoozed', snooze_until = 9e9 WHERE id = ?",
            (row.id,),
        )
        conn.commit()

    assert _tell("claude:gone") == 0
    with db.connect() as conn:
        assert db.get_by_channel(conn, "claude:gone", unread_only=False).snooze_through_turns


def test_a_recipient_with_no_session_record_fails(capsys, monkeypatch):
    _attach("claude:gone", "# t\n\nStatus: working\n")
    with db.connect() as conn:
        conn.execute("DELETE FROM notifications WHERE channel = 'claude:gone'")
        conn.commit()

    assert _tell("claude:gone") == 1
    assert "ask your user to resume it" in capsys.readouterr().err


def test_a_message_that_will_not_be_read_is_logged_as_a_dead_letter(started):
    _attach("claude:finished", "# t\n\nStatus: done\n", cwd="/tmp", session_id="abc")

    assert _tell("claude:finished") == 1
    entries = [json.loads(line) for line in dead_letters.path().read_text().splitlines()]
    assert [(e["to"].split(".")[0], e["state"]) for e in entries] == [("recipient", "dead")]
    assert entries[0]["from"].startswith("claude:sender")
    assert "was marked done" in entries[0]["said"]


def test_a_started_lemon_leaves_no_dead_letter(started):
    _attach("claude:gone", "# t\n\nStatus: working\n")

    assert _tell("claude:gone") == 0
    assert not dead_letters.path().exists()


def test_an_unwritable_dead_letter_log_still_exits_1(started, monkeypatch):
    _attach("claude:finished", "# t\n\nStatus: done\n", cwd="/tmp", session_id="abc")
    dead_letters.path().parent.mkdir(parents=True, exist_ok=True)
    dead_letters.path().mkdir()  # a directory where the log file should be

    assert _tell("claude:finished") == 1


def test_a_dead_cmux_lemon_is_started_through_cmux(capsys, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(autoresume_cmux, "start", lambda row, config: calls.append("cmux") or "")
    monkeypatch.setattr(
        recipient.handlers, "where_sessions_are", lambda sessions, fresh: {"claude:incmux": False}
    )
    path = brief_store.briefs_dir() / "recipient.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# t\n\nStatus: working\n")
    with db.connect() as conn:
        db.add(conn, "claude:incmux", "", metadata={"cwd": "/tmp"}, switch_source="cmux")
        attached.attach(conn, "claude:incmux", path)

    assert _tell("claude:incmux") == 0
    assert calls == ["cmux"]
