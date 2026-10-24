"""Run the smaller coordinator and native hook against test-owned processes only."""

import json
import subprocess
import sys

import pytest

from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.launch.restart import coordinator, native, pane, planning, process, state
from lemonaid.messages import store, waiter
from lemonaid.watch import registry, wait_state

from . import runtime_fixture, shared

runtime = runtime_fixture.runtime
_until = runtime_fixture._until


def test_old_scout_releases_both_locks_before_pane_replacement(runtime, tmp_path, monkeypatch):
    _path, lemon_id, _original = runtime
    inbox = store.inbox_for_id(lemon_id)
    with (tmp_path / "scout.log").open("w") as log:
        scout = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "lemonaid",
                "watch",
                "--self",
                "--push",
                "--foreground",
                "--channel",
                shared.CHANNEL,
                "--codex-thread",
                shared.SESSION,
            ],
            stdout=log,
            stderr=log,
        )
        try:
            _until(lambda: registry.mine(shared.CHANNEL))
            assert wait_state.is_armed(lemon_id)
            assert waiter.is_armed(inbox)
            replace = pane.replace

            def checked_replace(*args, **kwargs):
                assert not registry.mine(shared.CHANNEL)
                assert not wait_state.is_armed(lemon_id)
                assert not waiter.is_armed(inbox)
                return replace(*args, **kwargs)

            monkeypatch.setattr(pane, "replace", checked_replace)
            with db.connect() as conn:
                plan = planning.build(conn, shared.CHANNEL, Config(), True)
            token = state.reserve(plan)
            coordinator.run(token)
            assert state.get(token)["phase"] == "started"
            assert scout.wait(timeout=5) == 143
        finally:
            if scout.poll() is None:
                scout.terminate()
                scout.wait(timeout=5)


def test_native_resume_gets_rearm_instruction_without_rebuilding_watchers(runtime, tmp_path):
    path, lemon_id, original = runtime
    before = path.read_bytes()
    with db.connect() as conn:
        plan = planning.build(conn, shared.CHANNEL, Config(), True)
    pending = store.send(store.inbox_for_id(lemon_id), "held during restart", "test")
    token = state.reserve(plan)
    assert pending.exists()
    coordinator.run(token)
    operation = state.get(token)
    assert operation["phase"] == "started", json.dumps(operation, indent=2)
    current = pane.by_id(original.socket, original.pane)
    assert current.pane == original.pane and current.window == original.window
    assert current.pid != original.pid
    assert path.read_bytes() == before
    assert pane.exit_option(current) == ""
    _until(lambda: (tmp_path / "prompt").exists())
    assert (tmp_path / "prompt").read_text() == planning.PROMPT
    assert native.binding(shared.CHANNEL)["session_id"] == shared.SESSION
    resumed = native.binding(shared.CHANNEL)["identity"]["pid"]
    assert resumed != plan["source"]["pid"]
    assert current.pid in {p.pid for p in process.ancestry(resumed)}
    assert pending.exists()
    assert not registry.mine(shared.CHANNEL)  # Coordinator does not reconstruct transient state.
    # Acting on the prompt, the resumed lemon can arm the normal watcher itself.
    with (tmp_path / "watch.log").open("w") as log:
        watcher = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "lemonaid",
                "watch",
                "--self",
                "--channel",
                shared.CHANNEL,
                "--codex-thread",
                shared.SESSION,
            ],
            stdout=log,
            stderr=log,
        )
        try:
            _until(lambda: not pending.exists())
            assert "held during restart" in (tmp_path / "queued").read_text()
        finally:
            watcher.terminate()
            watcher.wait(timeout=5)


def test_self_restart_detached_worker_survives_callers_exit(runtime, tmp_path):
    _path, _lemon_id, original = runtime
    (tmp_path / "self-restart").touch()

    def scheduled():
        try:
            return json.loads((tmp_path / "operation.json").read_text())["token"]
        except (OSError, ValueError, KeyError):
            return None

    token = _until(scheduled)

    def started():
        operation = state.get(token)
        assert operation["phase"] not in ("failed", "partial"), operation
        return operation["phase"] == "started"

    _until(started)
    assert pane.by_id(original.socket, original.pane).pid != original.pid


@pytest.mark.parametrize("boundary", ["stopping", "starting", "respawned"])
def test_interrupted_worker_does_not_replay_the_stop_or_launch(
    runtime, tmp_path, monkeypatch, boundary
):
    _path, _lemon_id, original = runtime
    with db.connect() as conn:
        plan = planning.build(conn, shared.CHANNEL, Config(), True)
    token = state.reserve(plan)
    script = "\n".join(
        [
            "import os,sys",
            "from lemonaid.launch.restart import coordinator,state,pane",
            "update=state.update",
            "def crash(token,phase,**fields):",
            "    update(token,phase,**fields)",
            "    if phase==sys.argv[2]: os._exit(9)",
            "state.update=crash",
            "replace=pane.replace",
            "def respawn(*a,**kw):",
            "    result=replace(*a,**kw)",
            '    if sys.argv[2]=="respawned": os._exit(9)',
            "    return result",
            "pane.replace=respawn",
            "coordinator.run(sys.argv[1])",
        ]
    )
    child = subprocess.run([sys.executable, "-c", script, token, boundary], timeout=15)
    assert child.returncode == 9, state.get(token)
    current = pane.by_id(original.socket, original.pane)
    monkeypatch.setattr(state.time, "time", lambda: 10**12)
    assert state.get(token)["phase"] == "partial"
    coordinator.run(token)
    assert pane.by_id(original.socket, original.pane) == current
    assert pane.exit_option(current) == "on"
