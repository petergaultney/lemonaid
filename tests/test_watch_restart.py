"""Running watch --self waiters restart into the installed lemonaid when asked by signal."""

import argparse
import os
import signal
import subprocess
import sys
import textwrap

import pytest

from lemonaid.brief import attached, store
from lemonaid.inbox import db
from lemonaid.watch import batch_wait, registry, restart, restart_cli, wait_cli, wait_state


def _waiter(
    pid: int,
    version: str = "1.0",
    restartable: bool = True,
    lemon: str = "a.Bee",
    channel: str = "codex:a",
    command: str = "",
):
    return registry.Waiter(pid, channel, "wait", (lemon,), command, "/", "", version, restartable)


def test_the_signal_is_noted_only_while_listening():
    with restart.listening():
        pass

    assert signal.getsignal(restart.SIGNAL) is signal.SIG_DFL
    try:
        with restart.listening():
            os.kill(os.getpid(), restart.SIGNAL)
            assert restart.requested()

        assert signal.getsignal(restart.SIGNAL) is signal.SIG_IGN
    finally:
        signal.signal(restart.SIGNAL, signal.SIG_DFL)


def test_a_second_request_cannot_kill_a_restarting_watcher():
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                """
                import os, sys
                from lemonaid.watch import restart
                with restart.listening():
                    print("listening", flush=True)
                    while not restart.requested():
                        pass
                print("restarting", flush=True)
                sys.stdin.readline()
                os.execv(sys.executable, [sys.executable, "-c", "import sys; print('new', flush=True); sys.stdin.readline()"])
                """
            ),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdin and child.stdout
    assert child.stdout.readline() == "listening\n"
    os.kill(child.pid, restart.SIGNAL)
    assert child.stdout.readline() == "restarting\n"
    os.kill(child.pid, restart.SIGNAL)
    child.stdin.write("\n")
    child.stdin.flush()
    assert child.stdout.readline() == "new\n"
    os.kill(child.pid, restart.SIGNAL)
    child.stdin.write("\n")
    child.stdin.close()

    assert child.wait(timeout=10) == 0


def test_a_waiter_whose_entry_is_gone_is_not_signaled(monkeypatch):
    monkeypatch.setattr(restart.os, "kill", lambda pid, sig: pytest.fail("signaled"))

    assert restart.send([_waiter(os.getpid())]) == []


def test_only_restartable_live_waiters_are_signaled(monkeypatch):
    monkeypatch.setattr(registry, "current", lambda waiter: True)
    killed = []

    def kill(pid, sig):
        if pid == 3:
            raise ProcessLookupError
        killed.append((pid, sig))

    monkeypatch.setattr(restart.os, "kill", kill)

    sent = restart.send([_waiter(1), _waiter(2, restartable=False), _waiter(3)])

    assert [w.pid for w in sent] == [1]
    assert killed == [(1, restart.SIGNAL)]


def test_a_new_version_asks_older_waiters_to_restart_once(monkeypatch):
    monkeypatch.setattr(restart, "version", lambda: "2.0")
    monkeypatch.setattr(registry, "running", lambda: iter([_waiter(1, "1.0"), _waiter(2, "2.0")]))
    monkeypatch.setattr(registry, "current", lambda waiter: True)
    monkeypatch.setattr(restart.os, "kill", lambda pid, sig: None)

    assert [w.pid for w in restart.after_upgrade()] == [1]
    assert restart.after_upgrade() == []


def test_the_watcher_restarts_after_releasing_its_lock(monkeypatch):
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text("# task\n\nBrief-ID: task.IndexElf\n\n## Watching\n")
    with db.connect() as conn:
        db.add(conn, "codex:test", "", metadata={})
        attached.attach(conn, "codex:test", path)
    args = argparse.Namespace(
        codex_thread="",
        channel="codex:test",
        status=False,
        interval=0.01,
        quiet=0,
        push=False,
        foreground=False,
    )
    restarted = []
    monkeypatch.setattr(restart, "requested", lambda: True)
    monkeypatch.setattr(
        restart, "restart", lambda: restarted.append(wait_state.is_armed("task.IndexElf"))
    )

    assert wait_cli.run(args) == 0
    assert restarted == [False]


def test_an_idle_wait_stops_for_a_restart(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    brief = tmp_path / "task.md"
    brief.write_text("# task\n\nBrief-ID: task.IndexElf\n\n## Watching\n")

    assert batch_wait.wait(
        brief,
        inbox,
        tmp_path / "cursors",
        "",
        print,
        lambda: True,
        quiet=0,
        restart_requested=lambda: True,
    )


def test_the_command_restarts_named_or_all_watchers(monkeypatch, capsys):
    waiters = [
        _waiter(1, lemon="a.Bee"),
        _waiter(
            2,
            lemon="b.Cow",
            restartable=False,
            channel="claude:old",
            command="lemonaid watch --self --push",
        ),
    ]
    monkeypatch.setattr(registry, "running", lambda: iter(waiters))
    monkeypatch.setattr(registry, "current", lambda waiter: True)
    monkeypatch.setattr(restart.os, "kill", lambda pid, sig: None)

    def run(*argv):
        parser = argparse.ArgumentParser()
        restart_cli.add_parser(parser.add_subparsers())
        return restart_cli.run(parser.parse_args(["restart", *argv]))

    assert run("a.Bee") == 0
    assert "pid 1" in capsys.readouterr().out
    assert run("--all") == 0
    out = capsys.readouterr().out
    assert "pid 1" in out and "1 older watchers" in out
    assert "b.Cow  wait  pid 2  channel claude:old  lemonaid watch --self --push" in out
    assert run() == 2
