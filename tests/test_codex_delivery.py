"""`inbox watch --codex-thread` moves a message to done/ only once Codex has queued it."""

import argparse
import os
import stat
import threading
import time
from pathlib import Path

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db
from lemonaid.messages import cli, store

_FAKE_CODEX = """#!/bin/sh
printf '%s\\n' "$@" > "$FAKE_CODEX_ARGS"
echo queued >> "$FAKE_CODEX_ARGS.calls"
sleep "${FAKE_CODEX_SLEEP:-0}"
echo "queue refused" >&2
exit "${FAKE_CODEX_EXIT:-0}"
"""


@pytest.fixture(autouse=True)
def _no_inherited_session_identity(monkeypatch):
    for name in ("LEMONAID_CHANNEL", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX_PANE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_codex(tmp_path, monkeypatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    codex = bin_dir / "codex"
    codex.write_text(_FAKE_CODEX)
    codex.chmod(codex.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    args_file = tmp_path / "codex-args"
    monkeypatch.setenv("FAKE_CODEX_ARGS", str(args_file))
    return args_file


def _inbox_with_message(body: str, channel: str = "codex:recipient") -> Path:
    path = brief_store.briefs_dir() / "recipient.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# recipient\n")
    with db.connect() as conn:
        db.add(conn, channel, "", metadata={})
        attached.attach(conn, channel, path)
        inbox = store.inbox_for_id(identity.ensure(conn, path))

    store.send(inbox, body, "claude:sender")
    return inbox


def _watch(*extra: str, channel: str = "codex:recipient") -> None:
    parser = argparse.ArgumentParser()
    inbox = parser.add_subparsers().add_parser("inbox")
    cli.add_inbox_parsers(inbox.add_subparsers())
    args = parser.parse_args(
        ["inbox", "watch", "--self", "--channel", channel, "--timeout", "1", *extra]
    )
    args.func(args)


def test_queued_message_moves_to_done(capsys, fake_codex):
    inbox = _inbox_with_message("Please review.")

    _watch("--codex-thread", "thread-1")

    queued = fake_codex.read_text().splitlines()
    assert queued[:4] == ["queue", "--thread", "thread-1", "--message"]
    assert queued[4] == "lemonaid message: From: claude:sender"
    assert queued[-1] == "Please review."
    assert not list(inbox.glob("*.md"))
    assert len(list((inbox / "done").glob("*.md"))) == 1
    assert capsys.readouterr().out.endswith("Please review.\n")


def test_failed_queue_leaves_message_pending_for_the_next_watch(capsys, fake_codex, monkeypatch):
    inbox = _inbox_with_message("Please review.")
    monkeypatch.setenv("FAKE_CODEX_EXIT", "3")

    with pytest.raises(SystemExit, match="1"):
        _watch("--codex-thread", "thread-1")

    error = capsys.readouterr().err
    assert "codex queue exited 3" in error
    assert "queue refused" in error
    assert len(list(inbox.glob("*.md"))) == 1
    assert not list((inbox / "done").glob("*.md"))

    monkeypatch.setenv("FAKE_CODEX_EXIT", "0")
    _watch("--codex-thread", "thread-1")

    assert not list(inbox.glob("*.md"))
    assert len(list((inbox / "done").glob("*.md"))) == 1


def test_missing_codex_leaves_message_pending(capsys, tmp_path, monkeypatch):
    inbox = _inbox_with_message("Please review.")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))

    with pytest.raises(SystemExit, match="1"):
        _watch("--codex-thread", "thread-1")

    assert "Could not run codex queue" in capsys.readouterr().err
    assert len(list(inbox.glob("*.md"))) == 1


def test_watch_without_codex_thread_claims_as_before(capsys, fake_codex):
    inbox = _inbox_with_message("Please review.")

    _watch()

    assert not fake_codex.exists()
    assert len(list((inbox / "done").glob("*.md"))) == 1


def test_watch_inside_codex_queues_into_its_own_thread(capsys, fake_codex, monkeypatch):
    monkeypatch.setenv("CODEX_THREAD_ID", "01a0d8ce-long-thread-id")
    inbox = _inbox_with_message("Please review.", channel="codex:01a0d8ce")

    _watch(channel="codex:01a0d8ce")

    assert fake_codex.read_text().splitlines()[:3] == [
        "queue",
        "--thread",
        "01a0d8ce-long-thread-id",
    ]
    assert len(list((inbox / "done").glob("*.md"))) == 1


def test_watching_another_channel_from_codex_does_not_queue(capsys, fake_codex, monkeypatch):
    monkeypatch.setenv("CODEX_THREAD_ID", "01a0d8ce-long-thread-id")
    inbox = _inbox_with_message("Please review.")

    _watch()

    assert not fake_codex.exists()
    assert len(list((inbox / "done").glob("*.md"))) == 1


def test_concurrent_watches_queue_a_message_once(capsys, fake_codex, monkeypatch):
    inbox = _inbox_with_message("Please review.")
    monkeypatch.setenv("FAKE_CODEX_SLEEP", "0.3")
    exits = []

    def watch() -> None:
        try:
            _watch("--codex-thread", "thread-1")
            exits.append(0)
        except SystemExit as error:
            exits.append(error.code)

    watches = [threading.Thread(target=watch) for _ in range(2)]
    for thread in watches:
        thread.start()
    for thread in watches:
        thread.join(timeout=5)

    assert sorted(exits) == [0, 1]
    assert Path(f"{fake_codex}.calls").read_text() == "queued\n"
    assert len(list((inbox / "done").glob("*.md"))) == 1
    assert "No message before the watch timeout" in capsys.readouterr().err


def test_plain_receiver_waits_while_codex_queues(capsys, fake_codex, monkeypatch):
    inbox = _inbox_with_message("Please review.")
    monkeypatch.setenv("FAKE_CODEX_SLEEP", "0.5")
    codex_watch = threading.Thread(target=lambda: _watch("--codex-thread", "thread-1"))
    codex_watch.start()
    calls = Path(f"{fake_codex}.calls")
    deadline = time.monotonic() + 5
    while not calls.exists() and time.monotonic() < deadline:
        time.sleep(0.01)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers().add_parser("inbox").add_subparsers()
    cli.add_inbox_parsers(subparsers)
    args = parser.parse_args(["inbox", "next", "--self", "--channel", "codex:recipient"])
    with pytest.raises(SystemExit, match="1"):
        args.func(args)
    codex_watch.join(timeout=5)

    assert calls.read_text() == "queued\n"
    assert len(list((inbox / "done").glob("*.md"))) == 1
    assert capsys.readouterr().out.endswith("Please review.\n")
