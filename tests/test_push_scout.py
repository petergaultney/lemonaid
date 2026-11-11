"""A Claude lemon's push scout delivers every batch through its session socket until the session ends."""

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import pytest

from lemonaid.brief import attached, store
from lemonaid.claude import inbound, session_socket
from lemonaid.hooks import stop_check
from lemonaid.inbox import db
from lemonaid.messages import store as messages
from lemonaid.watch import (
    hosted_scout,
    push_scout,
    registry,
    scout_roster,
    scout_start,
    stop_sender,
    wait_cli,
    wait_state,
    waiter_lock,
)
from tests.scout_host import shared as hosted

_SESSION = "abcd1234-1111-2222-3333-444455556666"
_LEMON = "task.IndexElf"
_CHANNEL = "claude:abcd1234"


@pytest.fixture(autouse=True)
def _hosting():
    with hosted.hosting():
        yield


def _registered(monkeypatch) -> list[str]:
    """The channels `ensure` registers a scout for."""
    channels: list[str] = []
    monkeypatch.setattr(
        scout_start, "host", lambda lemon_id, channel, thread, cwd: channels.append(channel)
    )
    return channels


def _briefed() -> Path:
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"# task\n\nBrief-ID: {_LEMON}\n\n## Watching\n")
    with db.connect() as conn:
        db.add(conn, "claude:abcd1234", "", metadata={"session_id": _SESSION})
        attached.attach(conn, "claude:abcd1234", path)
    return messages.mailbox_for_id(_LEMON)


def _session(sock: str, parked_job: str = "") -> Path:
    listing = session_socket.claude_dir() / "sessions" / f"{os.getpid()}.json"
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "sessionId": _SESSION,
                "cwd": os.getcwd(),
                "messagingSocketPath": sock,
                **({"parkedJobId": parked_job} if parked_job else {}),
            }
        )
    )
    return listing


def _listener() -> tuple[str, list[str]]:
    """A Unix socket that keeps every message content written to it, and ignores a
    connection closed with nothing written."""
    path = os.path.join(tempfile.mkdtemp(dir="/tmp"), "s.sock")  # AF_UNIX paths are short
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(4)
    received: list[str] = []

    def serve() -> None:
        while True:
            with server.accept()[0] as conn:
                if written := conn.makefile("rb").read():
                    received.append(json.loads(written)["message"]["content"])

    threading.Thread(target=serve, daemon=True).start()
    return path, received


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        codex_thread="",
        channel="claude:abcd1234",
        status=False,
        interval=0.01,
        quiet=0,
        push=True,
        foreground=True,
    )


def _until(condition, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


def test_the_scout_pushes_each_batch_and_stops_with_its_session(capsys):
    mailbox = _briefed()
    sock, received = _listener()
    listing = _session(sock)
    scout = hosted.start(_LEMON, _CHANNEL)
    _until(lambda: push_scout.running(_LEMON))
    _until(lambda: len(received) == 1)

    messages.send(mailbox, "first message", "other.IndexElf")
    _until(lambda: len(received) == 2)
    messages.send(mailbox, "second message", "other.IndexElf")
    _until(lambda: len(received) == 3)

    assert "push scout started" in received[0] and sock in received[0]
    assert "first message" in received[1] and "second message" in received[2]
    assert "lemonaid is watching for you" in received[1]
    assert "don't" not in (received[0] + received[1]).lower()
    _until(lambda: messages.pending_count(mailbox) == 0)  # marked done after the push
    registration = scout_roster.read(_LEMON)
    assert registration and hosted_scout.run(registration, lambda: False) == "retry"
    listing.unlink()
    assert scout.join() == "ended"
    assert not wait_state.is_armed(_LEMON)


def test_a_claude_scout_started_from_a_codex_lemon_serves_the_claude_session(monkeypatch):
    monkeypatch.setenv("CODEX_THREAD_ID", "calling-codex")
    _briefed()
    sock, received = _listener()
    listing = _session(sock)
    scout = hosted.start(_LEMON, _CHANNEL)

    _until(lambda: push_scout.running(_LEMON, _SESSION))
    _until(lambda: len(received) == 1)
    listing.unlink()
    scout.join()


def test_a_replacement_scout_does_not_announce_again():
    sock, received = _listener()
    entry = session_socket.Session(os.getpid(), _SESSION, os.getcwd(), sock)
    push_scout.announce(entry)
    push_scout.announce(entry)
    _until(lambda: received)
    time.sleep(0.2)

    assert len(received) == 1


def test_a_refused_push_leaves_the_message_for_the_next_waiter(capsys):
    mailbox = _briefed()
    _session(os.path.join(tempfile.mkdtemp(dir="/tmp"), "gone.sock"))
    messages.send(mailbox, "kept", "other.IndexElf")

    assert hosted.run(_LEMON, _CHANNEL) == "retry"
    assert messages.pending_count(mailbox) == 1


def test_no_scout_for_a_session_that_would_hold_the_message(monkeypatch, capsys):
    _briefed()
    _session("/tmp/unused.sock")
    monkeypatch.setattr(inbound, "session_accepts", lambda entry: False)

    assert wait_cli.run(_args()) == 2
    assert "crossSessionInbound" in capsys.readouterr().out
    assert hosted.run(_LEMON, _CHANNEL) == "ended"


def test_no_scout_for_a_parked_session_and_its_messages_stay_pending(caplog, capsys):
    mailbox = _briefed()
    sock, received = _listener()
    _session(sock, parked_job="1eb3e867")
    messages.send(mailbox, "kept", "other.IndexElf")

    with caplog.at_level(logging.INFO):
        assert hosted.run(_LEMON, _CHANNEL) == "ended"
        assert not push_scout.ensure("abcd1234", _LEMON, grace=0)

    assert messages.pending_count(mailbox) == 1
    assert received == []
    assert any("background job 1eb3e867" in r.getMessage() for r in caplog.records)
    assert wait_cli.run(_args()) == 2
    assert "background job 1eb3e867" in capsys.readouterr().out


def test_ensure_starts_a_scout_only_for_a_session_that_accepts(monkeypatch):
    _briefed()
    _session("/tmp/unused.sock")
    registered = _registered(monkeypatch)

    push_scout.ensure("abcd1234", _LEMON, grace=0)
    monkeypatch.setattr(inbound, "session_accepts", lambda entry: False)
    push_scout.ensure("abcd1234", _LEMON, grace=0)

    assert registered == [_CHANNEL]


def test_the_stop_check_starts_a_scout_instead_of_asking_for_a_background_task(monkeypatch, capsys):
    _briefed()
    monkeypatch.setattr(push_scout, "ensure", lambda session_id, lemon_id, grace: True)

    stop_check.handle(json.dumps({"session_id": _SESSION}), grace=0.0)

    assert capsys.readouterr().out == ""


def test_ensure_replaces_a_scout_still_bound_to_the_previous_session(monkeypatch):
    """After /clear the old scout holds the lock until it notices its session is gone."""
    _briefed()
    _session("/tmp/unused.sock")
    registered = _registered(monkeypatch)
    lock = wait_state.lock_path(_LEMON)
    lock.parent.mkdir(parents=True, exist_ok=True)
    old = waiter_lock.acquire(lock)
    with registry.registered("wait", (_LEMON,), "claude:00000000", "lemonaid watch --self --push"):
        threading.Timer(0.3, old.close).start()

        push_scout.ensure("abcd1234", _LEMON, grace=0)

    assert registered == [_CHANNEL]


def _silence(lemon_id: str) -> None:
    then = time.time() - wait_state.STALE - 1
    for path in wait_state.lock_path(lemon_id).parent.glob("wait.*"):
        os.utime(path, (then, then))


def test_a_polling_scout_keeps_its_heartbeat_fresh():
    _briefed()
    sock, _ = _listener()
    listing = _session(sock)
    scout = hosted.start(_LEMON, _CHANNEL)
    _until(lambda: push_scout.running(_LEMON))
    _silence(_LEMON)

    _until(lambda: not wait_state.deaf(_LEMON))
    listing.unlink()
    scout.join()


def test_ensure_replaces_a_scout_that_stopped_polling(monkeypatch):
    _briefed()
    _session("/tmp/unused.sock")
    registered = _registered(monkeypatch)
    stuck = subprocess.Popen(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                f"""
                import time
                from lemonaid.watch import registry, wait_state, waiter_lock
                lock = wait_state.lock_path({_LEMON!r})
                lock.parent.mkdir(parents=True, exist_ok=True)
                held = waiter_lock.acquire(lock)
                with registry.registered("wait", ({_LEMON!r},), "claude:abcd1234", "lemonaid watch --self --push"):
                    print("held", flush=True)
                    time.sleep(60)
                """
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert stuck.stdout and stuck.stdout.readline() == "held\n"
        _silence(_LEMON)

        push_scout.ensure(_SESSION, _LEMON, grace=0)

        assert stuck.wait(timeout=10) != 0
        assert registered == [_CHANNEL]
    finally:
        stuck.kill()
        stuck.wait()


def test_status_calls_a_silent_scout_deaf(capsys):
    _briefed()
    _session("/tmp/unused.sock")
    lock = wait_state.lock_path(_LEMON)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with waiter_lock.acquire(lock):
        _silence(_LEMON)

        assert wait_cli.run(argparse.Namespace(**{**vars(_args()), "status": True})) == 1

    assert "watcher deaf" in capsys.readouterr().out


def _exits(caplog) -> list[tuple[str, str]]:
    return [
        (r.levelname, r.getMessage())
        for r in caplog.records
        if r.getMessage().startswith("push scout exited")
    ]


def test_a_scout_whose_session_ends_logs_a_normal_exit(caplog):
    entry = session_socket.Session(os.getpid(), _SESSION, "", "")
    with caplog.at_level(logging.INFO), push_scout.logged(_LEMON, entry):
        pass

    [(level, message)] = _exits(caplog)
    assert level == "INFO"
    assert "exited normally" in message and "session ended" in message and _LEMON in message


def test_a_scout_restarting_on_request_logs_a_normal_exit(caplog):
    entry = session_socket.Session(os.getpid(), _SESSION, "", "")
    with caplog.at_level(logging.INFO), push_scout.logged(_LEMON, entry, lambda: True):
        pass

    [(level, message)] = _exits(caplog)
    assert level == "INFO"
    assert "exited normally" in message and "restarting on request" in message


def test_watch_stop_is_a_normal_exit_and_a_stray_sigterm_is_not(caplog):
    entry = session_socket.Session(os.getpid(), _SESSION, "", "")
    with caplog.at_level(logging.INFO):
        with (
            pytest.raises(SystemExit),
            registry.registered(
                "wait", (_LEMON,), "claude:abcd1234", "lemonaid watch --self --push"
            ),
            push_scout.logged(_LEMON, entry),
        ):
            stop_sender.record(registry.entry(os.getpid()), "claude:other")
            raise SystemExit(143)
        with pytest.raises(SystemExit), push_scout.logged(_LEMON, entry):
            raise SystemExit(143)

    assert [(level, "exited normally" in message) for level, message in _exits(caplog)] == [
        ("INFO", True),
        ("WARNING", False),
    ]


def test_a_refused_push_logs_an_abnormal_exit(caplog):
    mailbox = _briefed()
    _session(os.path.join(tempfile.mkdtemp(dir="/tmp"), "gone.sock"))
    messages.send(mailbox, "kept", "other.IndexElf")

    with caplog.at_level(logging.INFO):
        assert hosted.run(_LEMON, _CHANNEL) == "retry"

    [(level, message)] = _exits(caplog)
    assert level == "WARNING" and "Failed" in message


def test_a_scout_stops_when_claude_code_parks_its_session(caplog):
    mailbox = _briefed()
    sock, received = _listener()
    listing = _session(sock)
    with caplog.at_level(logging.INFO):
        scout = hosted.start(_LEMON, _CHANNEL)
        _until(lambda: len(received) == 1)  # the announcement

        _session(sock, parked_job="1eb3e867")
        assert scout.join() == "ended"
    messages.send(mailbox, "kept", "other.IndexElf")
    time.sleep(0.2)

    assert len(received) == 1
    assert messages.pending_count(mailbox) == 1
    assert not wait_state.is_armed(_LEMON)
    [(level, message)] = _exits(caplog)
    assert level == "INFO" and "session parked" in message and "1eb3e867" in message
    listing.unlink()


def test_a_batch_for_a_session_parked_while_the_scout_connects_stays_pending(monkeypatch):
    mailbox = _briefed()
    sock, received = _listener()
    _session(sock)
    scout = hosted.start(_LEMON, _CHANNEL)
    _until(lambda: len(received) == 1)  # the announcement

    class Parking(socket.socket):
        def connect(self, address) -> None:
            super().connect(address)
            _session(sock, parked_job="1eb3e867")

    monkeypatch.setattr(session_socket.socket, "socket", Parking)
    messages.send(mailbox, "kept", "other.IndexElf")

    assert scout.join() == "retry"
    assert messages.pending_count(mailbox) == 1
    assert not any("kept" in content for content in received)


def test_push_registers_the_scout_with_the_host_and_returns(capsys):
    _briefed()
    _session("/tmp/unused.sock")

    assert wait_cli.run(argparse.Namespace(**{**vars(_args()), "foreground": False})) == 2

    registration = scout_roster.read(_LEMON)
    assert registration and registration.channel == _CHANNEL and not registration.thread
    assert "did not take its lock" in capsys.readouterr().out


def test_push_without_foreground_reports_a_running_scout(capsys):
    mailbox = _briefed()
    sock, _ = _listener()
    listing = _session(sock)
    scout = hosted.start(_LEMON, _CHANNEL)
    _until(lambda: push_scout.running(_LEMON))

    assert wait_cli.run(argparse.Namespace(**{**vars(_args()), "foreground": False})) == 0
    assert "push scout running" in capsys.readouterr().out
    listing.unlink()
    scout.join()
    assert messages.pending_count(mailbox) == 0


def test_a_lemon_with_no_socket_is_told_it_is_not_on_push():
    _briefed()

    notice = push_scout.not_pushing("abcd1234", _LEMON)

    assert (
        "NOT pushing" in notice
        and "no running Claude session" in notice
        and "background waiter" in notice
    )


def test_a_lemon_whose_session_would_hold_pushes_is_told_so(monkeypatch):
    _briefed()
    _session("/tmp/unused.sock")
    monkeypatch.setattr(inbound, "session_accepts", lambda entry: False)

    assert "crossSessionInbound" in push_scout.not_pushing("abcd1234", _LEMON)


def test_a_lemon_with_a_background_waiter_is_not_told_it_is_off_push():
    _briefed()
    wait_state.lock_path(_LEMON).parent.mkdir(parents=True, exist_ok=True)
    with waiter_lock.acquire(wait_state.lock_path(_LEMON), grace=1):
        assert push_scout.not_pushing("abcd1234", _LEMON) == ""


def _hosting_after(monkeypatch, delay: float) -> None:
    """A registration only gets its scout `delay` seconds after the call, as when the host restarts."""
    started = time.monotonic()
    monkeypatch.setattr(scout_start, "host", lambda *a: None)
    monkeypatch.setattr(
        push_scout,
        "_scout_channels",
        lambda lemon_id: {_CHANNEL} if time.monotonic() - started >= delay else set(),
    )
    monkeypatch.setattr(
        wait_state, "is_armed", lambda lemon_id, grace=0: time.monotonic() - started >= delay
    )


def test_ensure_waits_out_a_host_restart_longer_than_the_grace(monkeypatch):
    _briefed()
    _session("/tmp/unused.sock")
    _hosting_after(monkeypatch, 0.5)
    scout_roster.mark_restarting()

    assert push_scout.ensure("abcd1234", _LEMON, grace=0.1, restart_wait=5)


def test_ensure_does_not_wait_for_a_host_that_is_not_restarting(monkeypatch):
    _briefed()
    _session("/tmp/unused.sock")
    _hosting_after(monkeypatch, 0.5)

    assert not push_scout.ensure("abcd1234", _LEMON, grace=0.1, restart_wait=5)


def test_ensure_gives_up_when_a_restarting_host_never_returns(monkeypatch):
    _briefed()
    _session("/tmp/unused.sock")
    _hosting_after(monkeypatch, 60)
    scout_roster.mark_restarting()

    assert not push_scout.ensure("abcd1234", _LEMON, grace=0.1, restart_wait=0.5)
