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
from lemonaid.watch import push_scout, registry, stop_sender, wait_cli, wait_state, waiter_lock

_SESSION = "abcd1234-1111-2222-3333-444455556666"
_LEMON = "task.IndexElf"


def _briefed() -> Path:
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"# task\n\nBrief-ID: {_LEMON}\n\n## Watching\n")
    with db.connect() as conn:
        db.add(conn, "claude:abcd1234", "", metadata={"session_id": _SESSION})
        attached.attach(conn, "claude:abcd1234", path)
    return messages.inbox_for_id(_LEMON)


def _session(sock: str) -> Path:
    listing = session_socket.claude_dir() / "sessions" / f"{os.getpid()}.json"
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "sessionId": _SESSION,
                "cwd": os.getcwd(),
                "messagingSocketPath": sock,
            }
        )
    )
    return listing


def _listener() -> tuple[str, list[str]]:
    """A Unix socket that keeps every message content written to it."""
    path = os.path.join(tempfile.mkdtemp(dir="/tmp"), "s.sock")  # AF_UNIX paths are short
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(4)
    received: list[str] = []

    def serve() -> None:
        while True:
            with server.accept()[0] as conn:
                received.append(json.loads(conn.makefile("rb").read())["message"]["content"])

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
    inbox = _briefed()
    sock, received = _listener()
    listing = _session(sock)
    results: list[int] = []
    scout = threading.Thread(target=lambda: results.append(wait_cli.run(_args())))
    scout.start()
    _until(lambda: push_scout.running(_LEMON))
    _until(lambda: len(received) == 1)

    messages.send(inbox, "first message", "other.IndexElf")
    _until(lambda: len(received) == 2)
    messages.send(inbox, "second message", "other.IndexElf")
    _until(lambda: len(received) == 3)

    assert "push scout started" in received[0] and sock in received[0]
    assert "first message" in received[1] and "second message" in received[2]
    assert "lemonaid is watching for you" in received[1]
    assert "don't" not in (received[0] + received[1]).lower()
    assert messages.pending_count(inbox) == 0
    assert wait_cli.run(_args()) == 3  # a second scout for the same lemon refuses
    listing.unlink()
    scout.join(timeout=10)
    assert results == [0]
    assert not wait_state.is_armed(_LEMON)


def test_a_replacement_scout_does_not_announce_again():
    sock, received = _listener()
    entry = session_socket.Session(os.getpid(), _SESSION, os.getcwd(), sock)
    push_scout.announce(entry)
    push_scout.announce(entry)
    _until(lambda: received)
    time.sleep(0.2)

    assert len(received) == 1


def test_a_refused_push_leaves_the_message_for_the_next_waiter(capsys):
    inbox = _briefed()
    _session(os.path.join(tempfile.mkdtemp(dir="/tmp"), "gone.sock"))
    messages.send(inbox, "kept", "other.IndexElf")

    assert wait_cli.run(_args()) == 1
    assert messages.pending_count(inbox) == 1


def test_no_scout_for_a_session_that_would_hold_the_message(monkeypatch, capsys):
    _briefed()
    _session("/tmp/unused.sock")
    monkeypatch.setattr(inbound, "session_accepts", lambda entry: False)

    assert wait_cli.run(_args()) == 2
    assert "crossSessionInbound" in capsys.readouterr().out


def test_ensure_starts_a_scout_only_for_a_session_that_accepts(monkeypatch):
    _briefed()
    _session("/tmp/unused.sock")
    spawned: list[session_socket.Session] = []
    monkeypatch.setattr(push_scout, "_spawn", spawned.append)

    push_scout.ensure("abcd1234", _LEMON, grace=0)
    monkeypatch.setattr(inbound, "session_accepts", lambda entry: False)
    push_scout.ensure("abcd1234", _LEMON, grace=0)

    assert [e.session_id for e in spawned] == [_SESSION]


def test_the_stop_check_starts_a_scout_instead_of_asking_for_a_background_task(monkeypatch, capsys):
    _briefed()
    monkeypatch.setattr(push_scout, "ensure", lambda session_id, lemon_id, grace: True)

    stop_check.handle(json.dumps({"session_id": _SESSION}), grace=0.0)

    assert capsys.readouterr().out == ""


def test_ensure_replaces_a_scout_still_bound_to_the_previous_session(monkeypatch):
    """After /clear the old scout holds the lock until it notices its session is gone."""
    _briefed()
    _session("/tmp/unused.sock")
    spawned: list[session_socket.Session] = []
    monkeypatch.setattr(push_scout, "_spawn", spawned.append)
    lock = wait_state.lock_path(_LEMON)
    lock.parent.mkdir(parents=True, exist_ok=True)
    old = waiter_lock.acquire(lock)
    with registry.registered("wait", (_LEMON,), "claude:00000000", "lemonaid watch --self --push"):
        threading.Timer(0.3, old.close).start()

        push_scout.ensure("abcd1234", _LEMON, grace=0)

    assert [e.session_id for e in spawned] == [_SESSION]


def _silence(lemon_id: str) -> None:
    then = time.time() - wait_state.STALE - 1
    for path in wait_state.lock_path(lemon_id).parent.glob("wait.*"):
        os.utime(path, (then, then))


def test_a_polling_scout_keeps_its_heartbeat_fresh():
    _briefed()
    sock, received = _listener()
    listing = _session(sock)
    scout = threading.Thread(target=lambda: wait_cli.run(_args()))
    scout.start()
    _until(lambda: push_scout.running(_LEMON))
    _silence(_LEMON)

    _until(lambda: not wait_state.deaf(_LEMON))
    listing.unlink()
    scout.join(timeout=10)


def test_ensure_replaces_a_scout_that_stopped_polling(monkeypatch):
    _briefed()
    _session("/tmp/unused.sock")
    spawned: list[session_socket.Session] = []
    monkeypatch.setattr(push_scout, "_spawn", spawned.append)
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
        assert [e.session_id for e in spawned] == [_SESSION]
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
    inbox = _briefed()
    _session(os.path.join(tempfile.mkdtemp(dir="/tmp"), "gone.sock"))
    messages.send(inbox, "kept", "other.IndexElf")

    with caplog.at_level(logging.INFO):
        assert wait_cli.run(_args()) == 1

    [(level, message)] = _exits(caplog)
    assert level == "WARNING" and "Failed" in message


def test_push_without_foreground_starts_a_detached_scout_and_returns(monkeypatch, capsys):
    _briefed()
    _session("/tmp/unused.sock")
    spawned: list[session_socket.Session] = []
    monkeypatch.setattr(push_scout, "_spawn", spawned.append)

    assert wait_cli.run(argparse.Namespace(**{**vars(_args()), "foreground": False})) == 2

    assert [e.session_id for e in spawned] == [_SESSION]
    assert "did not take its lock" in capsys.readouterr().out


def test_push_without_foreground_reports_a_running_scout(capsys):
    inbox = _briefed()
    sock, _ = _listener()
    listing = _session(sock)
    scout = threading.Thread(target=lambda: wait_cli.run(_args()))
    scout.start()
    _until(lambda: push_scout.running(_LEMON))

    assert wait_cli.run(argparse.Namespace(**{**vars(_args()), "foreground": False})) == 0
    assert "push scout running" in capsys.readouterr().out
    listing.unlink()
    scout.join(timeout=10)
    assert messages.pending_count(inbox) == 0


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
