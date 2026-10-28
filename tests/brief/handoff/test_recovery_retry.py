"""CLI retries retire definite failures without duplicating an uncertain launch."""

import argparse
import json
import time
from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from lemonaid.brief import attached
from lemonaid.brief.handoff import cli, coordinator, pane, recovery, request, state

from .shared import recovery_runtime


def _args(*arguments):
    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers())
    return parser.parse_args(["handoff", *arguments])


def _setup(conn, path, monkeypatch):
    recovery_runtime(monkeypatch, path)
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(path.parent))
    monkeypatch.setattr(cli.db, "connect", lambda: nullcontext(conn))
    monkeypatch.setattr(coordinator, "source", lambda *_: (path, "work", "2", "@2", "%2", "claude"))
    monkeypatch.setattr(pane, "has_pane", lambda *_: True)
    monkeypatch.setattr(recovery.handoff_launch, "configured_line", lambda *_: "codex --no-daemon")
    monkeypatch.setattr(request, "watch", Mock())
    return _args("--source", "claude:old", "--to", "codex", "--recover", "--yes")


def test_failed_cli_recovery_can_retry(setup, monkeypatch, capsys):
    conn, path = setup
    args = _setup(conn, path, monkeypatch)
    launch = Mock(side_effect=[ValueError("preserve failed"), None])
    monkeypatch.setattr(recovery.pane, "preserve", launch)
    with pytest.raises(SystemExit):
        args.func(args)
    assert "preserve failed" in json.loads(capsys.readouterr().err)["error"]
    failed = conn.execute("SELECT * FROM brief_handoffs").fetchone()
    assert failed["phase"] == "failed" and failed["error"]
    request.watch.assert_not_called()
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path
    args.func(args)
    assert json.loads(capsys.readouterr().out)["phase"] == "launched"
    assert launch.call_count == 2
    assert conn.execute("SELECT COUNT(*) FROM brief_handoffs").fetchone()[0] == 2


def test_expired_unlaunched_recovery_is_retired(setup, monkeypatch, capsys):
    conn, path = setup
    args = _setup(conn, path, monkeypatch)
    token, _, _ = request.prepare(conn, "codex", source="claude:old", recover=True)
    conn.execute("UPDATE brief_handoffs SET deadline = ? WHERE token = ?", (time.time() - 1, token))
    conn.commit()
    launch = recovery.pane.replace
    args.func(args)
    assert json.loads(capsys.readouterr().out)["phase"] == "launched"
    assert state.get(conn, token)["phase"] == "failed"
    launch.assert_called_once()


@pytest.mark.parametrize("interrupted", [False, True])
def test_uncertain_launch_stays_pending_after_failure_and_expiry(
    setup, monkeypatch, capsys, interrupted
):
    conn, path = setup
    args = _setup(conn, path, monkeypatch)
    launch = Mock(side_effect=ValueError("inspect the original pane"))
    monkeypatch.setattr(recovery.pane, "replace", launch)
    if interrupted:
        token, _, _ = request.prepare(conn, "codex", source="claude:old", recover=True)
        conn.execute("UPDATE brief_handoffs SET phase = 'prepared' WHERE token = ?", (token,))
        conn.commit()
    else:
        with pytest.raises(SystemExit):
            args.func(args)
        capsys.readouterr()
    pending = conn.execute("SELECT * FROM brief_handoffs").fetchone()
    assert pending["phase"] == "prepared"
    assert bool(pending["error"]) is not interrupted
    conn.execute("UPDATE brief_handoffs SET deadline = ?", (time.time() - 1,))
    conn.commit()
    with pytest.raises(SystemExit):
        args.func(args)
    assert "may have replaced" in json.loads(capsys.readouterr().err)["error"]
    assert state.get(conn, pending["token"])["phase"] == "prepared"
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path
    assert launch.call_count == (0 if interrupted else 1)
    request.watch.assert_not_called()


@pytest.mark.parametrize(
    "reason",
    [
        "No process binding",
        "Multiple harnesses share the terminal",
        "Unrelated jobs share the terminal",
    ],
)
def test_unknown_native_process_is_refused_before_stop(setup, monkeypatch, reason):
    conn, path = setup
    _setup(conn, path, monkeypatch)
    recovery.planning.build.side_effect = ValueError(reason)
    with pytest.raises(ValueError, match=reason):
        request.prepare(conn, "codex", source="claude:old", recover=True)
    recovery.process.terminate.assert_not_called()
    assert conn.execute("SELECT COUNT(*) FROM brief_handoffs").fetchone()[0] == 0


def test_recovery_from_inside_source_is_refused(setup, monkeypatch):
    conn, path = setup
    _setup(conn, path, monkeypatch)
    source = recovery.process.Identity(**recovery.planning.build.return_value["source"])
    monkeypatch.setattr(recovery.process, "ancestry", lambda *_: [source])
    with pytest.raises(ValueError, match="outside the outgoing harness"):
        request.prepare(conn, "codex", source="claude:old", recover=True)
    recovery.process.terminate.assert_not_called()


def test_changed_pane_is_refused_before_stop(setup, monkeypatch):
    conn, path = setup
    _setup(conn, path, monkeypatch)
    recovery.planning.build.return_value["pane"]["window"] = "@different"
    with pytest.raises(ValueError, match="pane disagree"):
        request.prepare(conn, "codex", source="claude:old", recover=True)
    recovery.process.terminate.assert_not_called()


def test_changed_source_generation_does_not_start_replacement(setup, monkeypatch):
    conn, path = setup
    _setup(conn, path, monkeypatch)
    token, _, _ = request.prepare(conn, "codex", source="claude:old", recover=True)
    recovery.process.terminate.side_effect = ValueError("Harness process generation changed")
    with pytest.raises(ValueError, match="generation changed"):
        recovery.launch(conn, state.get(conn, token))
    recovery.pane.replace.assert_not_called()
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path
