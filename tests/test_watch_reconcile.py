import argparse
import fcntl
import os
import subprocess
from pathlib import Path

from lemonaid.brief import attached, store
from lemonaid.inbox import db
from lemonaid.messages import recipient
from lemonaid.watch import (
    codex_waiter,
    push_scout,
    reconcile,
    registry,
    restart,
    wait_state,
    waiter_lock,
)


def _lemon(name: str, *, status: str = "", archived: bool = False, mid_turn: bool = False) -> str:
    path = store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {name}\n\nBrief-ID: {name}.IndexElf\n" + (f"Status: {status}\n" if status else "")
    )
    channel = f"claude:{name}"
    with db.connect() as conn:
        db.add(conn, channel, "", metadata={})
        attached.attach(conn, channel, path)
        if archived:
            conn.execute(
                "UPDATE notifications SET status = 'archived' WHERE channel = ?", (channel,)
            )
        if mid_turn:
            conn.execute("UPDATE notifications SET turn_at = 1 WHERE channel = ?", (channel,))
        conn.commit()
    return f"{name}.IndexElf"


def _quiet(monkeypatch) -> list[tuple[str, str]]:
    started: list[tuple[str, str]] = []
    monkeypatch.setattr(recipient, "harness_alive", lambda row: True)
    monkeypatch.setattr(codex_waiter, "restore", lambda conn: codex_waiter.Restored([], False))
    monkeypatch.setattr(push_scout, "session", lambda session: object())
    monkeypatch.setattr(push_scout, "problem", lambda entry: "")
    monkeypatch.setattr(registry, "running", lambda: iter(()))
    monkeypatch.setattr(push_scout, "ensure", lambda s, lemon: started.append((s, lemon)) or True)
    return started


def test_a_pass_starts_a_scout_only_for_a_live_idle_lemon_that_needs_one(monkeypatch):
    started = _quiet(monkeypatch)
    wanted = _lemon("idle")
    _lemon("finished", status="done")
    _lemon("gone", archived=True)
    _lemon("busy", mid_turn=True)
    watched = _lemon("watched")
    lock = wait_state.lock_path(watched)
    lock.parent.mkdir(parents=True)

    with waiter_lock.acquire(lock):
        done = reconcile.run()

    assert started == [("idle", wanted)]
    assert done == [f"started a scout for {wanted}"]


def test_a_pass_asks_waiters_on_outdated_code_to_restart(monkeypatch):
    _quiet(monkeypatch)
    old = registry.Waiter(4242, "codex:a", "wait", ("a.Bee",), "", "/", "", "1.0", True)
    monkeypatch.setattr(registry, "running", lambda: iter([old]))
    monkeypatch.setattr(registry, "current", lambda waiter: True)
    monkeypatch.setattr(restart, "outdated", lambda waiter, current: True)
    killed = []
    monkeypatch.setattr(restart.os, "kill", lambda pid, sig: killed.append(pid))

    assert reconcile.run() == ["asked a.Bee's watcher (pid 4242) to restart"]
    assert killed == [4242]


def test_a_pass_does_nothing_while_another_runs(monkeypatch):
    started = _quiet(monkeypatch)
    _lemon("idle")
    registry.root().mkdir(parents=True, exist_ok=True)
    with open(registry.root() / "reconcile.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)

        assert reconcile.run() == []

    assert started == []


def _spawns(monkeypatch, fail: bool = False) -> tuple[list[dict[str, str]], list[float]]:
    envs: list[dict[str, str]] = []
    clock = [1000.0]

    def popen(*args, **kwargs):
        envs.append(kwargs["env"])
        if fail:
            raise PermissionError("sandboxed")

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(reconcile, "_editable", lambda: False)
    monkeypatch.setattr(reconcile.time, "time", lambda: clock[0])
    monkeypatch.setattr(restart, "version", lambda: "2.0")
    return envs, clock


def _later(clock: list[float]) -> None:
    clock[0] += reconcile._RETRY_SECONDS


def test_turning_reconcile_off_stops_both_the_command_and_the_install_trigger(monkeypatch, capsys):
    started = _quiet(monkeypatch)
    _lemon("idle")
    envs, _ = _spawns(monkeypatch)
    Path(os.environ["LEMONAID_CONFIG"]).write_text("[watch]\nreconcile = false\n")

    reconcile._cmd(argparse.Namespace())
    reconcile.after_install()

    assert "reconcile is off" in capsys.readouterr().out
    assert started == [] and envs == []


def test_commands_after_an_install_start_passes_a_minute_apart_until_one_settles(monkeypatch):
    _quiet(monkeypatch)
    envs, clock = _spawns(monkeypatch)
    monkeypatch.setenv("CODEX_THREAD_ID", "calling-codex")

    reconcile.after_install()
    reconcile.after_install()
    _later(clock)
    reconcile.after_install()
    reconcile.run()
    _later(clock)
    reconcile.after_install()

    assert len(envs) == 2
    assert all("CODEX_THREAD_ID" not in env for env in envs)


def test_a_pass_that_fails_to_start_is_tried_again_later(monkeypatch):
    envs, clock = _spawns(monkeypatch, fail=True)

    reconcile.after_install()
    _later(clock)
    reconcile.after_install()

    assert len(envs) == 2


def test_an_unsettled_pass_is_retried_a_bounded_number_of_times(monkeypatch):
    _quiet(monkeypatch)
    _lemon("idle")
    monkeypatch.setattr(push_scout, "ensure", lambda s, lemon: False)
    envs, clock = _spawns(monkeypatch)

    for _ in range(reconcile._ATTEMPTS + 3):
        reconcile.after_install()
        assert "a later pass will try again" in reconcile.run()[-1]
        _later(clock)

    assert len(envs) == reconcile._ATTEMPTS


def test_a_lemon_whose_liveness_is_unknown_leaves_the_pass_unsettled(monkeypatch):
    started = _quiet(monkeypatch)
    _lemon("idle")
    monkeypatch.setattr(recipient, "harness_alive", lambda row: None)
    envs, clock = _spawns(monkeypatch)

    reconcile.run()
    _later(clock)
    reconcile.after_install()

    assert started == [] and len(envs) == 1


def test_a_session_that_can_never_take_a_scout_does_not_hold_the_pass_open(monkeypatch):
    started = _quiet(monkeypatch)
    _lemon("idle")
    monkeypatch.setattr(
        push_scout, "problem", lambda entry: "the session would hold pushed messages"
    )
    envs, clock = _spawns(monkeypatch)

    assert reconcile.run() == ["no scout for idle.IndexElf: the session would hold pushed messages"]
    _later(clock)
    reconcile.after_install()

    assert started == [] and envs == []


def test_a_dev_checkout_starts_no_pass(monkeypatch):
    envs, _ = _spawns(monkeypatch)
    monkeypatch.setattr(reconcile, "_editable", lambda: True)

    reconcile.after_install()

    assert envs == []
