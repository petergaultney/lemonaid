import argparse
import os
import select
import subprocess
from pathlib import Path

import pytest

from lemonaid.brief import attached, store
from lemonaid.inbox import db
from lemonaid.watch import (
    batch_wait,
    codex_scout,
    delivery,
    push_scout,
    registry,
    scout_failures,
    wait_cli,
    wait_state,
    wait_status,
)
from tests.scout_host import shared as hosted


def _briefed() -> None:
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text("# task\n\nBrief-ID: task.IndexElf\n\n## Watching\n")
    with db.connect() as conn:
        db.add(conn, "codex:test", "", metadata={})
        attached.attach(conn, "codex:test", path)


def _codex(directory: Path, body: str) -> Path:
    directory.mkdir()
    codex = directory / "codex"
    codex.write_text(f"#!/bin/sh\n{body}\n")
    codex.chmod(0o755)
    return codex


def _broken_codex_on_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    shim = _codex(
        tmp_path / "shims", 'echo "mise ERROR No version is set for shim: codex" >&2; exit 1'
    )
    monkeypatch.setenv("PATH", f"{shim.parent}{os.pathsep}{os.environ['PATH']}")


def _one_batch_then(monkeypatch, alive: list[bool], still_alive: bool) -> None:
    monkeypatch.setattr(codex_scout, "_ALIVE_EVERY", 0)
    monkeypatch.setattr(codex_scout, "thread_alive", lambda thread, max_age=0.0: alive[0])

    def wait(*args, **kwargs):
        args[4]("batch")
        alive[0] = still_alive

    monkeypatch.setattr(batch_wait, "wait", wait)


def _args(push: bool) -> argparse.Namespace:
    return argparse.Namespace(
        codex_thread="test",
        channel="",
        status=False,
        interval=0.01,
        quiet=0,
        push=push,
        foreground=push,
    )


def test_the_scout_keeps_queueing_batches_until_its_thread_dies(monkeypatch):
    _briefed()
    queued, commands, alive = [], [], [True]
    monkeypatch.setattr(delivery, "codex_setup_problem", lambda *_: "")
    monkeypatch.setattr(codex_scout, "_ALIVE_EVERY", 0)
    monkeypatch.setattr(codex_scout, "thread_alive", lambda thread, max_age=0.0: alive[0])
    monkeypatch.setattr(
        delivery,
        "queue_text",
        lambda thread, kind, text_of: lambda m: queued.append(text_of(m)),
    )

    def wait(*args, **kwargs):
        commands.extend(w.command for w in registry.running_for("wait", "task.IndexElf"))
        args[4](f"batch {len(queued)}")
        alive[0] = len(queued) < 2

    monkeypatch.setattr(batch_wait, "wait", wait)

    with hosted.hosting():
        assert hosted.run("task.IndexElf", "codex:test", "test") == "ended"
    assert len(queued) == 2
    assert all(text.endswith("\n\n---\nlemonaid keeps watching.") for text in queued)
    assert all(push_scout.FLAG in command.split() for command in commands)
    assert not wait_state.is_armed("task.IndexElf")


def test_a_batch_for_a_dead_thread_is_not_queued(monkeypatch):
    queued = []
    monkeypatch.setattr(codex_scout, "thread_alive", lambda thread, max_age=0.0: False)
    monkeypatch.setattr(delivery, "queue_text", lambda *args: queued.append)

    with pytest.raises(delivery.Failed):
        codex_scout.to_thread("test")("batch")
    assert queued == []


def test_liveness_leaves_a_starting_session_time_to_open_its_rollout(monkeypatch):
    checks = []
    monkeypatch.setattr(
        codex_scout, "thread_alive", lambda thread, max_age=0.0: checks.append(thread)
    )
    still, pids = codex_scout.liveness("test")

    assert still()
    assert checks == []
    assert pids == ()


_STARTED = "Mon Nov 16 18:27:18 2026"
_watch, _inspect = codex_scout.process_exit.watch, codex_scout.process.inspect


def _started(monkeypatch, started: str) -> None:
    """`ps -p` finds a process started at *started* on any pid."""
    monkeypatch.setattr(
        codex_scout.process,
        "inspect",
        lambda pid: codex_scout.process.Identity(pid, 1, "ttys001", started, "/opt/codex"),
    )


def _owned_by(monkeypatch, *pids: int | None) -> tuple[list[str], list[bool]]:
    """Each lookup of the scout's thread finds it in the next of *pids* (None: in none of
    them); the threads looked up, and a flag that says the process found has exited."""
    found = iter(pids)
    asked: list[str] = []
    exited = [False]

    def owner(thread: str, max_age: float = 0.0) -> codex_scout.processes.Running | None:
        asked.append(thread)
        pid = next(found)
        return pid and codex_scout.processes.Running(thread, "ttys001", "/opt/codex", pid, _STARTED)

    monkeypatch.setattr(codex_scout.processes, "owner", owner)
    monkeypatch.setattr(codex_scout.process_exit, "watch", lambda pid: lambda: exited[0])
    _started(monkeypatch, _STARTED)
    monkeypatch.setattr(codex_scout.processes, "switched", lambda found: False)
    monkeypatch.setattr(codex_scout, "thread_alive", lambda thread: False)
    return asked, exited


def test_a_scout_watches_its_threads_process_without_listing_again(monkeypatch):
    asked, _ = _owned_by(monkeypatch, 4321)
    monkeypatch.setattr(codex_scout, "_ALIVE_EVERY", 0)
    still, pids = codex_scout.liveness("test")

    assert all(still() for _ in range(3))
    assert asked == ["test"]
    assert pids == (4321,)


def test_a_scout_ends_as_soon_as_its_threads_process_exits(monkeypatch):
    _, exited = _owned_by(monkeypatch, 4321, None)
    still, _ = codex_scout.liveness("test")
    assert still()

    exited[0] = True
    assert not still()


def test_a_scout_ends_once_clear_moves_its_process_to_another_thread(monkeypatch):
    _owned_by(monkeypatch, 4321, None)
    monkeypatch.setattr(codex_scout, "_ALIVE_EVERY", 0)
    monkeypatch.setattr(codex_scout.processes, "switched", lambda found: True)
    still, _ = codex_scout.liveness("test")

    assert not still()


def test_a_process_that_took_the_pid_before_it_was_watched_is_not_the_owner(monkeypatch):
    _owned_by(monkeypatch, 4321, None)
    _started(monkeypatch, "Mon Nov 23 16:00:00 2026")
    still, _ = codex_scout.liveness("test")

    assert not still()


@pytest.mark.skipif(not hasattr(select, "kqueue"), reason="kqueue only")
def test_a_stale_listing_cannot_hand_the_scout_another_live_process(monkeypatch):
    other = subprocess.Popen(["sleep", "5"])
    try:
        _owned_by(monkeypatch, other.pid, None)
        monkeypatch.setattr(codex_scout.process_exit, "watch", _watch)
        monkeypatch.setattr(codex_scout.process, "inspect", _inspect)
        still, _ = codex_scout.liveness("test")

        assert not still()
    finally:
        other.kill()
        other.wait()


def test_a_scout_that_cannot_confirm_its_process_lists_at_each_check(monkeypatch):
    asked, _ = _owned_by(monkeypatch, 4321, 4321)

    def inspect(pid: int) -> None:
        raise subprocess.TimeoutExpired("ps", 3)

    monkeypatch.setattr(codex_scout.process, "inspect", inspect)
    monkeypatch.setattr(codex_scout, "_ALIVE_EVERY", 0)
    still, _ = codex_scout.liveness("test")

    assert still()
    assert asked == ["test"] * 2


def test_without_kqueue_a_scout_lists_at_each_check(monkeypatch):
    asked, _ = _owned_by(monkeypatch, 4321, 4321, 4321)
    monkeypatch.setattr(codex_scout.process_exit, "watch", lambda pid: None)
    monkeypatch.setattr(codex_scout, "_ALIVE_EVERY", 0)
    still, _ = codex_scout.liveness("test")

    assert still() and still()
    assert asked == ["test"] * 3


def test_a_scout_is_woken_by_its_threads_process_exiting(monkeypatch):
    _briefed()
    _, exited = _owned_by(monkeypatch, 4321, None)
    monkeypatch.setattr(delivery, "codex_setup_problem", lambda *_: "")
    watched = []

    def wait(*args, **kwargs):
        watched.extend(kwargs["harness"][1])
        exited[0] = True

    monkeypatch.setattr(batch_wait, "wait", wait)

    with hosted.hosting():
        assert hosted.run("task.IndexElf", "codex:test", "test") == "ended"
    assert watched == [4321]


def test_a_one_shot_rearm_beside_a_scout_is_a_no_op(monkeypatch, capsys):
    _briefed()
    monkeypatch.setattr(push_scout, "running", lambda lemon_id, session_id="": True)
    monkeypatch.setattr(
        batch_wait, "wait", lambda *args, **kwargs: pytest.fail("started a second watcher")
    )

    assert wait_cli.run(_args(push=False)) == 0
    assert "nothing to rearm" in capsys.readouterr().out


def test_a_thread_open_only_in_the_shared_daemon_is_alive(monkeypatch):
    monkeypatch.setattr(
        codex_scout.processes, "open_threads", lambda max_age=0.0: {"daemon-thread"}
    )

    assert codex_scout.thread_alive("daemon-thread")
    assert not codex_scout.thread_alive("exited-thread")


def test_the_scout_queues_with_the_codex_that_has_its_thread_open(tmp_path, monkeypatch):
    _briefed()
    _broken_codex_on_path(tmp_path, monkeypatch)
    real = _codex(tmp_path / "real", 'echo "$@" > "$(dirname "$0")/args"')
    monkeypatch.setattr(delivery.processes, "executable", lambda thread, max_age=0.0: str(real))
    _one_batch_then(monkeypatch, [True], still_alive=False)
    scout_failures.record("task.IndexElf", "an earlier failure")

    with hosted.hosting():
        assert hosted.run("task.IndexElf", "codex:test", "test") == "ended"
    assert (real.parent / "args").read_text().startswith("queue --thread test --message ")
    assert scout_failures.read("task.IndexElf") is None


def test_a_scout_that_keeps_failing_reports_why(tmp_path, monkeypatch, capsys):
    _briefed()
    _broken_codex_on_path(tmp_path, monkeypatch)
    monkeypatch.setattr(delivery.processes, "executable", lambda thread, max_age=0.0: "")
    _one_batch_then(monkeypatch, [True], still_alive=True)

    with hosted.hosting():
        assert hosted.run("task.IndexElf", "codex:test", "test") == "retry"
        assert hosted.run("task.IndexElf", "codex:test", "test") == "retry"
    assert (
        wait_status.report("task.IndexElf", "codex:test", "test", store.briefs_dir() / "task.md")
        == 1
    )
    assert capsys.readouterr().out.startswith(
        "push scout failing: codex queue exited 1: mise ERROR No version is set for shim: codex"
        " (2 attempts in a row since "
    )
    assert scout_failures.delay("task.IndexElf", 30) == 60
