"""The delivery service queues each Codex lemon's messages into its thread, once."""

import argparse
import os
import stat
import threading
from pathlib import Path

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.codex import notify as codex_notify
from lemonaid.inbox import db
from lemonaid.messages import cli, service, store
from lemonaid.messages.service import ensure_running as real_ensure_running

_FAKE_CODEX = """#!/bin/sh
printf '%s\\n' "$@" >> "$FAKE_CODEX_ARGS"
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


def _lemon(name: str, channel: str, thread: str = "") -> Path:
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n")
    with db.connect() as conn:
        db.add(conn, channel, "", metadata={"session_id": thread} if thread else {})
        attached.attach(conn, channel, path)
        return store.inbox_for_id(identity.ensure(conn, path))


def _queued_threads(args_file: Path) -> list[str]:
    lines = args_file.read_text().splitlines() if args_file.exists() else []
    return [lines[i + 1] for i, line in enumerate(lines) if line == "--thread"]


def _serve() -> bool:
    return service.serve(interval=0.01, idle_exit=0.05, retry=0.0)


def test_pending_messages_are_queued_into_the_full_thread_and_moved_to_done(fake_codex):
    inbox = _lemon("recipient", "codex:01a0d8ce", "01a0d8ce-long-thread-id")
    store.send(inbox, "First.", "claude:sender")
    store.send(inbox, "Second.", "claude:sender")

    assert _serve()

    assert _queued_threads(fake_codex) == ["01a0d8ce-long-thread-id"] * 2
    assert not list(inbox.glob("*.md"))
    assert len(list((inbox / "done").glob("*.md"))) == 2


def test_restarting_the_service_delivers_nothing_twice(fake_codex):
    inbox = _lemon("recipient", "codex:01a0d8ce", "01a0d8ce-long-thread-id")
    store.send(inbox, "Once.", "claude:sender")

    assert _serve()
    assert _serve()

    assert len(_queued_threads(fake_codex)) == 1


def test_a_second_service_exits_while_one_holds_the_lock(fake_codex):
    held = service._try_lock()
    try:
        assert not _serve()
    finally:
        held.close()


def test_failed_queue_leaves_the_message_pending_and_is_retried(fake_codex, monkeypatch):
    inbox = _lemon("recipient", "codex:01a0d8ce", "01a0d8ce-long-thread-id")
    store.send(inbox, "Please review.", "claude:sender")
    monkeypatch.setenv("FAKE_CODEX_EXIT", "1")
    retry_at: dict[Path, float] = {}

    assert service._pass(retry_at, retry=0.0)
    assert len(list(inbox.glob("*.md"))) == 1

    monkeypatch.setenv("FAKE_CODEX_EXIT", "0")
    assert not service._pass(retry_at, retry=0.0)
    assert len(list((inbox / "done").glob("*.md"))) == 1


def test_claude_and_archived_codex_lemons_are_left_alone(fake_codex):
    claude_inbox = _lemon("claude-lemon", "claude:abcd1234", "abcd1234-session")
    archived_inbox = _lemon("gone", "codex:deadbeef", "deadbeef-thread")
    with db.connect() as conn:
        db.archive(conn, db.get_by_channel(conn, "codex:deadbeef", unread_only=False).id)
    store.send(claude_inbox, "For Claude.", "claude:sender")
    store.send(archived_inbox, "For later.", "claude:sender")

    assert _serve()

    assert not fake_codex.exists()
    assert len(list(claude_inbox.glob("*.md"))) == 1
    assert len(list(archived_inbox.glob("*.md"))) == 1


def _tell(target: str, message: str) -> None:
    parser = argparse.ArgumentParser()
    cli.add_tell_parser(parser.add_subparsers())
    args = parser.parse_args(["tell", "--channel", "claude:sender", target, message])
    args.func(args)


def test_telling_a_codex_lemon_starts_the_service(capsys, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(service, "ensure_running", lambda: started.append(True))
    _lemon("codex-lemon", "codex:01a0d8ce", "01a0d8ce-long-thread-id")
    _lemon("claude-lemon", "claude:abcd1234", "abcd1234-session")

    _tell("claude:abcd1234", "No service for Claude.")
    assert not started

    _tell("codex:01a0d8ce", "Please review.")
    assert started == [True]


def test_a_codex_turn_with_mail_waiting_starts_the_service(monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(service, "ensure_running", lambda: started.append(True))
    inbox = _lemon("codex-lemon", "codex:01a0d8ce", "01a0d8ce-long-thread-id")
    payload = '{"type": "agent-turn-complete", "thread-id": "01a0d8ce-long-thread-id"}'

    codex_notify.handle_notification(payload, session_id="01a0d8ce-long-thread-id", cwd="/tmp")
    assert not started

    store.send(inbox, "Waited while archived.", "claude:sender")
    codex_notify.handle_notification(payload, session_id="01a0d8ce-long-thread-id", cwd="/tmp")
    assert started == [True]


def test_ensure_running_spawns_one_detached_service_only_when_none_holds_the_lock(monkeypatch):
    spawned: list[list[str]] = []
    monkeypatch.setattr(
        service.subprocess, "Popen", lambda argv, **kwargs: spawned.append(argv) or None
    )

    real_ensure_running()
    held = service._try_lock()
    try:
        real_ensure_running()
    finally:
        held.close()

    assert len(spawned) == 1
    assert spawned[0][1:] == ["-m", "lemonaid", "inbox", "deliver"]


def _after_first_delivery(monkeypatch, change) -> None:
    real = service.codex_delivery.deliver_next

    def deliver_then_change(*args):
        delivered = real(*args)
        change()
        return delivered

    monkeypatch.setattr(service.codex_delivery, "deliver_next", deliver_then_change)


def test_archiving_mid_pass_leaves_the_rest_pending(fake_codex, monkeypatch):
    inbox = _lemon("recipient", "codex:01a0d8ce", "01a0d8ce-long-thread-id")
    store.send(inbox, "First.", "claude:sender")
    store.send(inbox, "Second.", "claude:sender")

    def archive() -> None:
        with db.connect() as conn:
            db.archive(conn, db.get_by_channel(conn, "codex:01a0d8ce", unread_only=False).id)

    _after_first_delivery(monkeypatch, archive)
    service._pass({}, retry=0.0)

    assert len(_queued_threads(fake_codex)) == 1
    assert len(list(inbox.glob("*.md"))) == 1


def test_a_brief_moved_mid_pass_sends_the_rest_to_its_new_thread(fake_codex, monkeypatch):
    real = service.codex_delivery.deliver_next
    inbox = _lemon("recipient", "codex:01a0d8ce", "01a0d8ce-long-thread-id")
    store.send(inbox, "First.", "claude:sender")
    store.send(inbox, "Second.", "claude:sender")

    def reattach() -> None:
        with db.connect() as conn:
            db.add(conn, "codex:02b1e9df", "", metadata={"session_id": "02b1e9df-new-thread"})
            attached.attach(conn, "codex:02b1e9df", brief_store.briefs_dir() / "recipient.md")

    _after_first_delivery(monkeypatch, reattach)
    service._pass({}, retry=0.0)

    assert _queued_threads(fake_codex) == ["01a0d8ce-long-thread-id"]
    assert len(list(inbox.glob("*.md"))) == 1

    monkeypatch.setattr(service.codex_delivery, "deliver_next", real)
    service._pass({}, retry=0.0)
    assert _queued_threads(fake_codex) == ["01a0d8ce-long-thread-id", "02b1e9df-new-thread"]


def test_a_brief_moved_while_the_queue_runs_stays_pending_for_the_new_thread(
    fake_codex, monkeypatch
):
    inbox = _lemon("recipient", "codex:01a0d8ce", "01a0d8ce-long-thread-id")
    store.send(inbox, "In flight.", "claude:sender")
    real_queue = service.codex_delivery._queue

    def queue_then_reattach(thread: str, path: Path, message: str) -> None:
        real_queue(thread, path, message)
        with db.connect() as conn:
            db.add(conn, "codex:02b1e9df", "", metadata={"session_id": "02b1e9df-new-thread"})
            attached.attach(conn, "codex:02b1e9df", brief_store.briefs_dir() / "recipient.md")

    monkeypatch.setattr(service.codex_delivery, "_queue", queue_then_reattach)
    service._pass({}, retry=0.0)

    assert len(list(inbox.glob("*.md"))) == 1

    monkeypatch.setattr(service.codex_delivery, "_queue", real_queue)
    service._pass({}, retry=0.0)

    assert _queued_threads(fake_codex) == ["01a0d8ce-long-thread-id", "02b1e9df-new-thread"]
    assert len(list((inbox / "done").glob("*.md"))) == 1


def test_a_reattach_waits_for_the_final_check_and_move(fake_codex, monkeypatch):
    inbox = _lemon("recipient", "codex:01a0d8ce", "01a0d8ce-long-thread-id")
    store.send(inbox, "At the boundary.", "claude:sender")
    real_mark_done = store.mark_done
    reattach: list[threading.Thread] = []

    def attach_new_session() -> None:
        with db.connect() as conn:
            db.add(conn, "codex:02b1e9df", "", metadata={"session_id": "02b1e9df-new-thread"})
            attached.attach(conn, "codex:02b1e9df", brief_store.briefs_dir() / "recipient.md")

    def mark_done_during_reattach(path: Path) -> Path:
        thread = threading.Thread(target=attach_new_session)
        thread.start()
        reattach.append(thread)
        thread.join(0.3)
        assert thread.is_alive(), "the reattach did not wait for the move"
        return real_mark_done(path)

    monkeypatch.setattr(store, "mark_done", mark_done_during_reattach)
    service._pass({}, retry=0.0)
    reattach[0].join(5)

    assert not reattach[0].is_alive()
    assert _queued_threads(fake_codex) == ["01a0d8ce-long-thread-id"]
    assert len(list((inbox / "done").glob("*.md"))) == 1
    with db.connect() as conn:
        assert attached.by_channel(conn, ["codex:02b1e9df"])
