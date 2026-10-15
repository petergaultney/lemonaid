import json
import os
import shlex
import subprocess
import sys
from types import SimpleNamespace

import pytest

from lemonaid.inbox import db
from lemonaid.launch.restart import cli, environment, settings, state, watchers

from . import shared


def _default_target(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings.launch_args,
        "argv",
        lambda pid: ["claude", "--model", "claude-sonnet-5-5", "--permission-mode", "default"],
    )
    return settings.capture(
        "claude", 123, {}, {"HOME": str(tmp_path / "source"), "PATH": os.environ["PATH"]}
    )


def test_default_target_clears_callers_overrides_in_watcher_and_native_exec(tmp_path, monkeypatch):
    captured = _default_target(tmp_path, monkeypatch)
    for key in environment.KEYS:
        if key not in ("HOME", "PATH"):
            monkeypatch.setenv(
                key, "/caller/home" if key.endswith(("HOME", "DIR")) else "caller-override"
            )
            assert captured["environment"][key] is None
    plan = {**shared.plan(tmp_path), "harness": "claude", "settings": captured}
    monkeypatch.setattr(watchers.registry, "mine", lambda *args: [])
    calls = []
    with monkeypatch.context() as patch:
        patch.setattr(watchers.subprocess, "Popen", lambda *args, **kwargs: calls.append(kwargs))
        watchers.start(plan, "token")
    child = calls[0]["env"]
    assert child["HOME"] == str(tmp_path / "source")
    assert all(key not in child for key in environment.KEYS if captured["environment"][key] is None)
    # Exercise the actual post-shell exec prefix, not only a subprocess environment mock.
    command = settings.line(
        [sys.executable, "-c", "import json,os;print(json.dumps(dict(os.environ)))"],
        "",
        captured["environment"],
    )
    result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
    actual = json.loads(result.stdout)
    assert all(
        key not in actual for key in environment.KEYS if captured["environment"][key] is None
    )
    assert actual["HOME"] == child["HOME"]
    # Default Claude config means an unset override, not forcing ~/.claude: those
    # choices put Claude's account JSON and Keychain lookup in different locations.
    assert "CLAUDE_CONFIG_DIR" not in actual
    assert captured["native_homes"]["claude"] == str(tmp_path / "source/.claude")


def test_default_target_socket_lookup_ignores_callers_claude_home(tmp_path, monkeypatch):
    captured = _default_target(tmp_path, monkeypatch)
    root = tmp_path / "source/.claude"
    (root / "sessions").mkdir(parents=True)
    pid = os.getpid()
    (root / "sessions" / f"{pid}.json").write_text(
        json.dumps(
            {"pid": pid, "sessionId": shared.SESSION, "messagingSocketPath": "/source/socket"}
        )
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "caller"))
    plan = {
        **shared.plan(tmp_path),
        "channel": "claude:01234567",
        "harness": "claude",
        "settings": captured,
    }
    with db.connect() as conn:
        token = state.reserve(conn, plan)
        state.update(
            conn,
            token,
            "verifying",
            watcher=shared.plan(tmp_path)["source"],
            scout_pid=pid,
            scout_socket="/source/socket",
        )
    monkeypatch.setattr(watchers.process, "same", lambda identity: True)
    monkeypatch.setattr(
        watchers.registry, "mine", lambda *args: [SimpleNamespace(pid=shared.SOURCE.pid)]
    )
    assert watchers.ready(plan["channel"], token, SimpleNamespace(pid=pid))


def test_recovery_command_also_clears_unset_native_overrides(tmp_path, monkeypatch):
    captured = _default_target(tmp_path, monkeypatch)
    plan = {**shared.plan(tmp_path), "settings": captured}
    with db.connect() as conn:
        token = state.reserve(conn, plan)
        report = cli._report(state.get(conn, token))
    argv = shlex.split(report["resume_command"])
    assert argv[:1] == ["/usr/bin/env"]
    assert any(argv[i : i + 2] == ["-u", "CLAUDE_CONFIG_DIR"] for i in range(len(argv)))
    assert any(argv[i : i + 2] == ["-u", "LEMONAID_RESTART_TOKEN"] for i in range(len(argv)))


def test_incomplete_older_binding_cannot_claim_absent_overrides_are_known():
    with pytest.raises(ValueError, match="fresh native hook"):
        environment.validate({"environment": {"PATH": "/source/bin"}})


def test_old_operation_reports_status_without_an_unsafe_recovery_command(tmp_path):
    plan = {**shared.plan(tmp_path), "settings": {"environment": {"PATH": "/old"}}}
    with db.connect() as conn:
        token = state.reserve(conn, plan)
        report = cli._report(state.get(conn, token))
    assert report["phase"] == "planned"
    assert report["resume_command"] == ""
    assert "fresh native hook" in report["recovery_error"]
