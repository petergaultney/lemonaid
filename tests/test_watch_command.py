"""`lemonaid run` and `lemonaid watch command`: a process's exit, reported once, wherever it ran."""

import dataclasses
import datetime
import os
import signal
import subprocess
import sys
import time

import pytest

from lemonaid.brief import attached, identity, store, waiters
from lemonaid.inbox import db
from lemonaid.watch import command_cli, command_events, command_record, run_cli, subscriptions


@pytest.fixture
def state_dir(tmp_path):
    return tmp_path / "cursors"


def _poll(w) -> list[str]:
    sent: list[str] = []
    command_events.poll(w, sent.append)
    return sent


def test_an_unwrapped_process_is_reported_once_when_it_exits(state_dir):
    sleeper = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE
    )
    w = command_events.open_watch(state_dir, sleeper.pid, "")
    assert _poll(w) == []

    sleeper.communicate(b"")

    assert _poll(w) == [
        f"process {sleeper.pid} exited; its exit status is unknown (it was not started with `lemonaid run`)"
    ]
    assert _poll(w) == []
    assert _poll(command_events.open_watch(state_dir, sleeper.pid, "")) == []  # a rearm


def test_a_pid_with_no_process_is_reported_at_once(state_dir):
    done = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True
    )
    pid = int(done.stdout)

    assert (
        "was not running when this watch started"
        in _poll(command_events.open_watch(state_dir, pid, ""))[0]
    )


def test_a_recorded_exit_gives_the_command_and_status(state_dir):
    record = command_record.Record(
        424242, "Thu Nov  5 17:00:00 2026", "./deploy.sh", "/srv", "x.DustyMix", 1000.0
    )
    command_record.write(dataclasses.replace(record, exit=3, ended=1000.0 + 600))

    assert _poll(command_events.open_watch(state_dir, 424242, "")) == [
        "`./deploy.sh` (pid 424242, in /srv) exited with status 3 after 10m"
    ]


def test_a_killed_wrapper_is_reported_without_a_status(state_dir):
    command_record.write(
        command_record.Record(424243, "Thu Nov  5 17:00:00 2026", "make", "/srv", "x.Dusty", 1.0)
    )

    [message] = _poll(command_events.open_watch(state_dir, 424243, ""))
    assert "ended without recording its exit status" in message


@pytest.fixture
def lemon_brief():
    path = store.create("running", datetime.date(2026, 11, 5))
    with db.connect() as conn:
        attached.attach(conn, "claude:runner", path)
        lemon_id = identity.ensure(conn, path)
    return path, lemon_id


def _run(tmp_path, *words: str) -> subprocess.CompletedProcess:
    """`lemonaid run` in a process of its own, since the pid it records is its own."""
    return subprocess.run(
        [sys.executable, "-m", "lemonaid", "run", *words],
        env={**os.environ, "LEMONAID_DB": str(tmp_path / "lemonaid.db")},
        capture_output=True,
        text=True,
    )


def test_run_records_the_watch_then_the_exit_and_the_watch_removes_itself(
    lemon_brief, state_dir, tmp_path
):
    path, lemon_id = lemon_brief
    done = _run(tmp_path, "--lemon", lemon_id, "--", "sh", "-c", "echo out; exit 3")
    assert (done.returncode, done.stdout) == (3, "out\n")

    [spec] = [s for s in subscriptions.read(path.read_text(), path.parent) if s.kind == "command"]
    pid = int(spec.target[0])
    assert waiters.commands(path.read_text()) == [f"lemonaid watch command --wait {pid}"]

    [message] = _poll(command_events.open_watch(state_dir, pid, ""))
    assert message.startswith("`sh -c 'echo out; exit 3'` (pid ")
    assert "exited with status 3 after" in message

    command_cli.forget(lemon_id, pid)
    assert waiters.commands(path.read_text()) == []


def test_run_reports_a_signal(lemon_brief, state_dir, tmp_path):
    path, lemon_id = lemon_brief
    assert _run(tmp_path, "--lemon", lemon_id, "--", "sh", "-c", "kill -TERM $$").returncode == 143

    pid = int(waiters.commands(path.read_text())[0].split()[-1])
    [message] = _poll(command_events.open_watch(state_dir, pid, ""))
    assert "was ended by SIGTERM (exit 143)" in message


def test_run_refuses_a_lemon_without_a_brief(tmp_path):
    done = _run(tmp_path, "--lemon", "nobody.NoSuch", "--", "true")
    assert done.returncode == 2
    assert "not started" in done.stderr


def _sleeper() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE
    )


def test_a_stale_record_does_not_stand_for_a_new_live_process(state_dir):
    sleeper = _sleeper()
    try:
        command_record.write(
            command_record.Record(sleeper.pid, "Mon Jan  1 00:00:00 2024", "old", "/", "x", 1.0, 0)
        )
        assert _poll(command_events.open_watch(state_dir, sleeper.pid, "")) == []
    finally:
        sleeper.communicate(b"")


def test_a_reported_exit_does_not_silence_a_later_run_under_the_same_pid(state_dir):
    old = command_record.Record(
        424244, "Mon Jan  1 00:00:00 2024", "old", "/", "x", 1.0, 0, "", 2.0
    )
    command_record.write(old)
    assert len(_poll(command_events.open_watch(state_dir, 424244, ""))) == 1
    assert _poll(command_events.open_watch(state_dir, 424244, "")) == []  # a rearm

    command_record.write(
        dataclasses.replace(old, started="Tue Jan  2 00:00:00 2024", command="new")
    )

    [message] = _poll(command_events.open_watch(state_dir, 424244, ""))
    assert message.startswith("`new`")


def test_an_exited_process_its_parent_has_not_reaped_is_reported(state_dir):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.1)"])
    w = command_events.open_watch(state_dir, child.pid, "")
    time.sleep(1.0)  # exited, and not yet reaped: a zombie

    assert "exited; its exit status is unknown" in _poll(w)[0]
    child.wait()


@pytest.mark.parametrize("when", ["before", "after"])
def test_a_sigterm_while_the_command_starts_reaches_it(monkeypatch, when):
    real = subprocess.Popen

    def popen(argv):
        if when == "before":
            os.kill(os.getpid(), signal.SIGTERM)
        started = real(argv)
        if when == "after":
            os.kill(os.getpid(), signal.SIGTERM)
        return started

    monkeypatch.setattr(run_cli.subprocess, "Popen", popen)

    assert run_cli._run([sys.executable, "-c", "import time; time.sleep(5)"]) == (143, "SIGTERM")
