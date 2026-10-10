"""`lemon resume` brings back one lemon on request, whatever its brief says."""

import argparse
import time

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.messages import autoresume, autoresume_tmux, recipient, resume_cli, store
from lemonaid.messages_config import MessagesConfig


@pytest.fixture(autouse=True)
def _caller(monkeypatch):
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:caller")
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["-fish"])  # nothing runs there


@pytest.fixture
def started(monkeypatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        autoresume_tmux, "start", lambda row, config, text: calls.append(("start", text)) or ""
    )
    monkeypatch.setattr(
        autoresume_tmux, "prompt", lambda row, config, text: calls.append(("prompt", text)) or ""
    )
    return calls


def _attach(channel: str, brief: str) -> str:
    path = brief_store.briefs_dir() / "recipient.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(brief)
    with db.connect() as conn:
        db.add(conn, channel, "", metadata={"tty": "/dev/ttys900"}, switch_source="tmux")
        attached.attach(conn, channel, path)
        return identity.ensure(conn, path)


def _resume(*argv: str) -> int:
    parser = argparse.ArgumentParser()
    resume_cli.add_parser(parser.add_subparsers())
    args = parser.parse_args(["resume", *argv])
    try:
        args.func(args)
    except SystemExit as exit:
        return int(exit.code or 0)

    return 0


def _posted() -> str:
    with db.connect() as conn:
        row = db.get_by_channel(conn, autoresume.CHANNEL, unread_only=False)
    return row.message if row else ""


def test_a_dead_done_lemon_is_resumed_on_a_prompt_naming_the_caller(capsys, started):
    _attach("claude:gone", "# t\n\nStatus: done\n")

    assert _resume("claude:gone") == 0
    assert started == [("start", resume_cli._PROMPT.format(who="claude:caller"))]
    assert "claude:caller resumed" in capsys.readouterr().out
    assert "claude:caller resumed" in _posted()


def test_a_deaf_lemon_is_prompted_with_the_given_text(started, monkeypatch):
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["claude"])
    _attach("claude:idle", "# t\n\nStatus: waiting\n")

    assert _resume("claude:idle", "--prompt", "check CI") == 0
    assert started == [("prompt", "check CI")]


def test_a_listening_lemon_is_left_alone(capsys, started, monkeypatch):
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["codex"])
    _attach("codex:live", "# t\n\nStatus: working\n")

    assert _resume("codex:live") == 0
    assert started == []
    assert "Nothing to resume" in capsys.readouterr().out


def test_a_lemon_asking_its_user_is_not_typed_into(capsys, started, monkeypatch):
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["claude"])
    _attach("claude:asking", "# t\n\nStatus: working\n")
    with db.connect() as conn:
        db.record_turn(conn, "claude:asking", time.time() - 3600)

    assert _resume("claude:asking") == 1
    assert started == []
    assert "won't resume it" in capsys.readouterr().err


def test_the_start_limit_applies(capsys, started, monkeypatch):
    monkeypatch.setattr(
        resume_cli, "load_config", lambda: Config(messages=MessagesConfig(autoresume_max=1))
    )
    lemon_id = _attach("claude:looping", "# t\n\nStatus: working\n")
    inbox = store.inbox_for_id(lemon_id)
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / ".autoresumed").write_text(f"{time.time() - 600} start\n")

    assert _resume("claude:looping") == 1
    assert started == []
    assert "started too often recently" in capsys.readouterr().err
    assert _posted() == ""  # a caller retrying in a loop doesn't fill the inbox
