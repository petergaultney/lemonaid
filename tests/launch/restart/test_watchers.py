import dataclasses
import json
import os
from types import SimpleNamespace

import pytest

from lemonaid.claude import session_socket
from lemonaid.inbox import db
from lemonaid.launch.restart import process, state, watchers

from . import shared


def test_watcher_uses_target_environment_not_callers(tmp_path, monkeypatch):
    plan = shared.plan(tmp_path)
    plan["settings"] = {
        **plan["settings"],
        "environment": {
            **plan["settings"]["environment"],
            "PATH": "/target/bin",
            "CODEX_HOME": "/target/codex",
        },
    }
    monkeypatch.setenv("CODEX_HOME", "/caller/codex")
    monkeypatch.setattr(watchers.registry, "mine", lambda *args: [])
    calls = []
    monkeypatch.setattr(watchers.subprocess, "Popen", lambda *args, **kwargs: calls.append(kwargs))
    watchers.start(plan, "token")
    assert calls[0]["env"]["CODEX_HOME"] == "/target/codex"
    assert calls[0]["env"]["PATH"] == "/target/bin"


@pytest.mark.parametrize("command", ["", "lemonaid watch --self"])
def test_claude_background_or_missing_waiter_refuses_before_quiescing(command):
    waiters = [SimpleNamespace(kind="wait", command=command)] if command else []
    with pytest.raises(ValueError, match="running push scout"):
        watchers.check_source("claude", waiters)


def test_failed_source_restoration_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(watchers, "start", lambda *args: None)
    monkeypatch.setattr(watchers.registry, "mine", lambda *args: [])
    with pytest.raises(TimeoutError, match="rearm delivery manually"):
        watchers.restore(shared.plan(tmp_path), timeout=0)


def test_readiness_finds_socket_in_target_claude_home(tmp_path, monkeypatch):
    target_home = tmp_path / "target"
    (target_home / "sessions").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "caller"))
    harness = dataclasses.replace(shared.SOURCE, pid=os.getpid())
    entry = session_socket.Session(harness.pid, shared.SESSION, str(tmp_path), "/target/socket")
    (target_home / "sessions" / f"{harness.pid}.json").write_text(
        json.dumps(
            {"pid": harness.pid, "sessionId": entry.session_id, "messagingSocketPath": entry.socket}
        )
    )
    plan = shared.plan(tmp_path)
    plan["channel"] = "claude:01234567"
    plan["settings"] = {
        **plan["settings"],
        "environment": {"CLAUDE_CONFIG_DIR": str(target_home)},
        "native_homes": {"claude": str(target_home)},
    }
    with db.connect() as conn:
        token = state.reserve(conn, plan)
        state.update(
            conn,
            token,
            "verifying",
            watcher=dataclasses.asdict(harness),
            scout_pid=harness.pid,
            scout_socket=entry.socket,
        )
    monkeypatch.setattr(process, "same", lambda identity: True)
    monkeypatch.setattr(watchers.registry, "mine", lambda *args: [SimpleNamespace(pid=harness.pid)])
    assert watchers.ready(plan["channel"], token, harness)
