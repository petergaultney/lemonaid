import argparse

import pytest

from lemonaid.brief import attached, store
from lemonaid.inbox import db
from lemonaid.watch import (
    batch_wait,
    codex_scout,
    delivery,
    push_scout,
    registry,
    wait_cli,
    wait_state,
)


def _briefed() -> None:
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text("# task\n\nBrief-ID: task.IndexElf\n\n## Watching\n")
    with db.connect() as conn:
        db.add(conn, "codex:test", "", metadata={})
        attached.attach(conn, "codex:test", path)


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
    monkeypatch.setattr(delivery, "codex_setup_problem", lambda: "")
    monkeypatch.setattr(codex_scout, "_ALIVE_EVERY", 0)
    monkeypatch.setattr(codex_scout, "thread_alive", lambda thread: alive[0])
    monkeypatch.setattr(
        delivery, "to_codex", lambda thread, kind, instruction: lambda m: queued.append(instruction)
    )

    def wait(*args, **kwargs):
        commands.extend(w.command for w in registry.running_for("wait", "task.IndexElf"))
        args[4](f"batch {len(queued)}")
        alive[0] = len(queued) < 2

    monkeypatch.setattr(batch_wait, "wait", wait)

    assert wait_cli.run(_args(push=True)) == 0
    assert len(queued) == 2
    assert all("queues the next batch" in text and "rearm" not in text for text in queued)
    assert all(push_scout.FLAG in command.split() for command in commands)
    assert not wait_state.is_armed("task.IndexElf")


def test_a_batch_for_a_dead_thread_is_not_queued(monkeypatch):
    queued = []
    monkeypatch.setattr(codex_scout, "thread_alive", lambda thread: False)
    monkeypatch.setattr(delivery, "to_codex", lambda *args: queued.append)

    with pytest.raises(delivery.Failed):
        codex_scout.to_thread("test")("batch")
    assert queued == []


def test_liveness_leaves_a_starting_session_time_to_open_its_rollout(monkeypatch):
    checks = []
    monkeypatch.setattr(codex_scout, "thread_alive", lambda thread: checks.append(thread))

    assert codex_scout.liveness("test")()
    assert checks == []


def test_a_one_shot_rearm_beside_a_scout_is_a_no_op(monkeypatch, capsys):
    _briefed()
    monkeypatch.setattr(push_scout, "running", lambda lemon_id, session_id="": True)
    monkeypatch.setattr(
        batch_wait, "wait", lambda *args, **kwargs: pytest.fail("started a second watcher")
    )

    assert wait_cli.run(_args(push=False)) == 0
    assert "nothing to rearm" in capsys.readouterr().out


def test_a_thread_open_only_in_the_shared_daemon_is_alive(monkeypatch):
    monkeypatch.setattr(codex_scout.processes, "open_threads", lambda: {"daemon-thread"})

    assert codex_scout.thread_alive("daemon-thread")
    assert not codex_scout.thread_alive("exited-thread")
