"""A handoff to the lemon's own harness gives it a fresh session in the same pane."""

import argparse
import json
from contextlib import nullcontext
from unittest.mock import Mock

from lemonaid.brief import attached
from lemonaid.brief.handoff import cli as handoff_cli
from lemonaid.brief.handoff import launch as handoff_launch
from lemonaid.brief.handoff import pane as handoff_tmux
from lemonaid.brief.handoff import state as handoff_state
from lemonaid.config import Config, TmuxSessionConfig
from lemonaid.inbox import db, pins

_FRESH = "f0e1d2c3-0000-4000-8000-000000000000"


def _args(*argv):
    parser = argparse.ArgumentParser()
    handoff_cli.add_parser(parser.add_subparsers())
    return parser.parse_args(["handoff", *argv])


def _report(args, capsys) -> dict:
    args.func(args)
    return json.loads(capsys.readouterr().out)


def test_claude_hands_off_to_a_fresh_claude_in_its_own_pane(setup, monkeypatch, capsys):
    conn, path = setup
    old = db.get_by_channel(conn, "claude:old", unread_only=False)
    conn.execute(
        "UPDATE notifications SET metadata = ? WHERE id = ?",
        (
            json.dumps(
                {**old.metadata, "tty": "/dev/ttys2", "tmux_session": "work", "tmux_window": "2"}
            ),
            old.id,
        ),
    )
    conn.commit()
    config = Config(tmux_session=TmuxSessionConfig(resume_window=1))
    for module in (handoff_cli, handoff_launch):
        monkeypatch.setattr(module, "load_config", lambda: config)
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(path.parent))
    monkeypatch.setattr(handoff_cli.db, "connect", lambda: nullcontext(conn))
    monkeypatch.setattr(handoff_cli.subprocess, "Popen", Mock())
    monkeypatch.setattr(handoff_cli.to_brief, "send", Mock())
    monkeypatch.setattr(handoff_tmux, "pane_for_tty", lambda *_: ("%2", "@2"))
    monkeypatch.setattr(handoff_tmux, "has_pane", lambda *_: True)
    monkeypatch.setattr(handoff_tmux, "current_command", lambda _pane: "claude")
    monkeypatch.setattr(handoff_tmux, "remain_on_exit", lambda _pane: "off")
    monkeypatch.setattr(handoff_tmux, "set_remain_on_exit", lambda *_: True)
    respawn = Mock(return_value="")
    monkeypatch.setattr(handoff_tmux, "respawn", respawn)
    monkeypatch.setattr(
        handoff_tmux,
        "pane_process",
        lambda *_: ("400", False) if respawn.called else ("300", False),
    )

    token = _report(_args("--to", "claude", "--brief", str(path)), capsys)["token"]
    assert handoff_state.get(conn, token)["harness"] == "claude"

    path.write_text(path.read_text().replace("Old notes.", f"New notes.\nHandoff-Ready: {token}"))
    assert _report(_args("status", token), capsys)["phase"] == "launched"
    assert respawn.call_args.args[0] == "%2"
    typed, environment = respawn.call_args.args[2:]
    assert typed.split()[-2] == "claude"
    assert token in environment["LEMONAID_PROMPT"]
    assert environment["LEMONAID_HANDOFF_TOKEN"] == token
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path

    # What the new session's SessionStart hook records, with the token in its environment.
    db.register_working(
        conn, "claude:f0e1d2c3", "Started", metadata={"session_id": _FRESH, "cwd": str(path.parent)}
    )
    assert handoff_state.bind_target(conn, token, "claude:f0e1d2c3")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", _FRESH)
    monkeypatch.setenv("TMUX_PANE", "%2")
    monkeypatch.setenv("LEMONAID_HANDOFF_TOKEN", token)
    assert _report(_args("accept", token), capsys)["phase"] == "complete"

    respawn.assert_called_once()
    assert attached.by_channel(conn, ["claude:f0e1d2c3"])["claude:f0e1d2c3"] == path
    assert db.get_by_channel(conn, "claude:f0e1d2c3", unread_only=False).name == "Manual name"
    assert pins.pinned_positions(conn) == {"claude:f0e1d2c3": 10.0}
    assert db.get_by_channel(conn, "claude:old", unread_only=False).status == "archived"
