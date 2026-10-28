"""Confirmed recovery reuses the transfer transaction without an outgoing turn."""

import argparse
import json
from unittest.mock import Mock

import pytest

from lemonaid import groups
from lemonaid.brief import attached, identity
from lemonaid.brief.handoff import cli, coordinator, pane, recovery, request, state
from lemonaid.inbox import db, pins

from .shared import recovery_runtime


def _prepare(conn, path, monkeypatch):
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(path.parent))
    monkeypatch.setattr(recovery.handoff_launch, "configured_line", lambda *_: "codex --no-daemon")
    monkeypatch.setattr(coordinator, "source", lambda *_: (path, "work", "2", "@2", "%2", "claude"))
    monkeypatch.setattr(
        request.to_brief, "send", Mock(side_effect=AssertionError("no outgoing turn"))
    )
    return request.prepare(conn, "codex", source="claude:old", recover=True)[0]


def test_recovery_launch_accept_and_manual_state(setup, monkeypatch):
    conn, path = setup
    original = path.read_text()
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(path.parent))
    stable_id = identity.from_path(path)
    groups.store.add(conn, groups.store.create(conn, "test-group"), [stable_id])
    runtime = recovery_runtime(monkeypatch, path)
    token = _prepare(conn, path, monkeypatch)
    assert state.ready(conn, state.get(conn, token)) == (True, "")
    monkeypatch.setattr(pane, "has_pane", lambda *_: True)
    report = coordinator.advance(conn, token)
    assert report["phase"] == "launched"
    assert report["old_pane"] == report["new_pane"] == "%2"
    assert runtime["events"] == ["stop", "replace"]
    assert not runtime["alive"]["source"]
    assert (
        "without a final outgoing turn"
        in recovery.pane.replace.call_args.args[4]["LEMONAID_PROMPT"]
    )
    assert path.read_text() == original
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path
    assert state.bind_target(conn, token, "codex:new")
    state.acknowledge(conn, token, "codex:new", "accept")
    assert coordinator.advance(conn, token)["phase"] == "complete"
    assert attached.by_channel(conn, ["codex:new"])["codex:new"] == path
    assert pins.pinned_positions(conn) == {"codex:new": 10.0}
    assert db.get_by_channel(conn, "codex:new", unread_only=False).name == "Manual name"
    assert conn.execute("SELECT parent_id FROM lemon_parents").fetchone()[0] == "parent.Other"
    assert path.read_text() == original
    assert identity.from_path(path) == stable_id
    assert groups.store.names_of(conn, stable_id) == ("test-group",)
    recovery.process.terminate.assert_called_once_with(runtime["source"])
    recovery.pane.replace.assert_called_once()


def test_recovery_refuses_changed_saved_context(setup, monkeypatch):
    conn, path = setup
    recovery_runtime(monkeypatch, path)
    token = _prepare(conn, path, monkeypatch)
    path.write_text(path.read_text() + "\nChanged.\n")
    assert not state.ready(conn, state.get(conn, token))[0]
    assert "recovery brief changed" in state.ready(conn, state.get(conn, token))[1]


def test_recovery_requires_explicit_source_and_confirmation(capsys):
    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers())
    args = parser.parse_args(["handoff", "--to", "codex", "--recover"])
    with pytest.raises(SystemExit):
        args.func(args)
    assert "--yes" in json.loads(capsys.readouterr().err)["error"]


def test_recovery_launch_failure_retains_source(setup, monkeypatch):
    conn, path = setup
    runtime = recovery_runtime(monkeypatch, path)
    token = _prepare(conn, path, monkeypatch)
    recovery.pane.preserve.side_effect = ValueError("Could not preserve pane")
    with pytest.raises(ValueError, match="Could not preserve"):
        recovery.launch(conn, state.get(conn, token))
    coordinator.recover_source(conn, state.get(conn, token), "failed")
    assert state.get(conn, token)["phase"] == "failed"
    assert runtime["events"] == []
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path


def test_registered_waiters_stop_before_replacement(setup, monkeypatch):
    conn, path = setup
    runtime = recovery_runtime(monkeypatch, path)
    token = _prepare(conn, path, monkeypatch)
    waiter = object()
    monkeypatch.setattr(recovery.registry, "mine", lambda *_: [waiter])
    stop = Mock(side_effect=lambda *_: runtime["events"].append("stop-waiter"))
    monkeypatch.setattr(recovery.stopping, "stop", stop)
    recovery.launch(conn, state.get(conn, token))
    assert runtime["events"] == ["stop", "stop-waiter", "replace"]
    stop.assert_called_once_with(waiter, f"handoff {token}")
