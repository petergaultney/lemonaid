import argparse

from lemonaid.audit import events
from lemonaid.launch.move import cli, coordinator


def _args(**given) -> argparse.Namespace:
    return argparse.Namespace(
        **{
            "lemon": "move.Test",
            "destination": "/dest",
            "root": "",
            "force": True,
            "dry_run": False,
            "status": "",
            "json": True,
            **given,
        }
    )


def _plan(args):
    return {
        "kind": "move",
        "channel": "codex:abc",
        "lemon_id": "move.Test",
        "from": {"cwd": "/source"},
        "destination": {"directory": "/dest"},
        "claude_trust": True,
    }


def test_a_started_move_is_audited(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_plan", _plan)
    monkeypatch.setattr(coordinator, "spawn", lambda token: None)
    cli._cmd(_args())
    [entry] = events.entries(0)
    assert (entry["action"], entry["thing"], entry["why"]) == ("lemon-move", "move.Test", "forced")
    assert (entry["from"], entry["to"]) == ("/source", "/dest")
    assert entry["claude_trust"] is True
    assert entry["token"]


def test_a_dry_run_is_not_audited(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_plan", _plan)
    cli._cmd(_args(dry_run=True))
    assert events.entries(0) == []
