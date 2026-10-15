"""Run the real coordinator, hooks, watcher and journal on a private tmux server."""

import json
import os
import subprocess
import sys

import pytest

from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.launch.restart import coordinator, native, pane, planning, state, supervisor
from lemonaid.messages import store

from . import runtime_fixture, shared

runtime = runtime_fixture.runtime
_until = runtime_fixture._until


@pytest.mark.parametrize("runtime", [False, True], indirect=True)
def test_cutover_keeps_identity_and_delivers_queued_message_after_verification(
    runtime, tmp_path, monkeypatch
):
    path, lemon_id, original = runtime
    before = path.read_bytes()
    with db.connect() as conn:
        plan = planning.build(conn, shared.CHANNEL, Config(), force=True)
        token = state.reserve(conn, plan)
    target_home = plan["settings"]["environment"]["CODEX_HOME"] or "<unset>"
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "caller-codex"))
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join(
            p for p in os.environ["PATH"].split(os.pathsep) if p != str(tmp_path / "bin")
        ),
    )
    inbox = store.inbox_for_id(lemon_id)
    pending = store.send(inbox, "held during restart", "test")
    coordinator.run(token)
    with db.connect() as conn:
        operation = state.get(conn, token)
        generation = native.registered(conn, shared.CHANNEL)
        assert operation["phase"] == "complete", json.dumps(
            {"operation": operation, "generation": generation}, indent=2
        )
    current = pane.by_id(original.socket, original.pane)
    assert current.pane == original.pane
    assert current.window == original.window
    assert current.pid != original.pid
    assert generation["session_id"] == shared.SESSION
    assert generation["token"] == token
    with db.connect() as conn:
        assert (
            db.get_by_channel(conn, shared.CHANNEL, unread_only=False).metadata["tty"]
            == current.tty
        )
    assert path.read_bytes() == before
    assert pane.exit_option(current) == ""
    _until(lambda: (tmp_path / "queued").exists(), timeout=10)
    assert "held during restart" in (tmp_path / "queued").read_text()
    assert f"home={target_home}" in (tmp_path / "queued").read_text()
    assert "bedrock=<unset>" in (tmp_path / "queued").read_text()
    _until(lambda: not pending.exists())


def test_self_restart_coordinator_survives_callers_exit(runtime, tmp_path):
    _path, _lemon_id, original = runtime
    (tmp_path / "self-restart").touch()

    def scheduled():
        operation_file = tmp_path / "operation.json"
        if not operation_file.exists():
            return None
        try:
            return json.loads(operation_file.read_text())["operation_id"]
        except (ValueError, KeyError):
            return None

    token = _until(scheduled)

    def complete():
        with db.connect() as conn:
            operation = state.get(conn, token)
        assert operation["phase"] not in ("failed", "partial"), operation
        return operation["phase"] == "complete"

    _until(complete)
    assert pane.by_id(original.socket, original.pane).pid != original.pid


@pytest.mark.parametrize(
    "phase", ["quiescing", "stopping", "source-exited", "starting", "respawned", "verifying"]
)
def test_supervisor_reconciles_real_coordinator_death_at_boundaries(runtime, tmp_path, phase):
    _path, lemon_id, original = runtime
    with db.connect() as conn:
        plan = planning.build(conn, shared.CHANNEL, Config(), force=True)
        token = state.reserve(conn, plan)
    pending = store.send(store.inbox_for_id(lemon_id), "preserve on crash", "test")
    child_script = "\n".join(
        [
            "import os,sys",
            "from lemonaid.launch.restart import coordinator,state,pane",
            "replace = pane.replace",
            "def interrupted(*args, **kwargs):",
            "    result = replace(*args, **kwargs)",
            "    if sys.argv[2] == 'respawned': os._exit(9)",
            "    return result",
            "pane.replace = interrupted",
            "update = state.update",
            "def crash(conn,token,phase,**evidence):",
            "    update(conn,token,phase,**evidence)",
            "    if phase == sys.argv[2]: os._exit(9)",
            "state.update = crash",
            "coordinator.run(sys.argv[1])",
        ]
    )
    with (tmp_path / "crash.log").open("w") as log:
        child = subprocess.Popen(
            [sys.executable, "-c", child_script, token, phase],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        supervisor.monitor(token, child)
    assert child.returncode == 9
    with db.connect() as conn:
        operation = state.get(conn, token)
        assert operation["phase"] in ("failed", "partial"), operation
    assert not state.blocked(shared.CHANNEL)
    # Early aborts can restore a watcher and deliver the pending message; later ones retain it.
    assert pending.exists() or (tmp_path / "queued").exists()
    if phase in ("quiescing", "stopping"):
        assert pane.check(original).pid == original.pid
        assert pane.exit_option(original) == ""

    if phase == "respawned":
        current = pane.by_id(original.socket, original.pane)
        assert current.pane == original.pane and current.window == original.window
        assert current.pid != original.pid
        assert pane.exit_option(current) == "on"
        assert pending.exists()
        with db.connect() as conn:
            generation = native.registered(conn, shared.CHANNEL)
        assert generation["token"] in ("", token)
        assert operation["evidence"].get("replacement") is None
