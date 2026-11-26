"""`lemon start` from an OpenClaw session: a new root session of the same agent, as a lemon."""

import argparse
import contextlib
import json
from pathlib import Path

import pytest

import lemonaid.launch.cli
import lemonaid.launch.passthrough
import lemonaid.openclaw.cli
from lemonaid.brief import attached, identity, store
from lemonaid.front_end import chat
from lemonaid.inbox import db
from lemonaid.launch import openclaw_session
from lemonaid.lineage import links
from lemonaid.openclaw import gateway, lemons, sessions, sync

PARENT_KEY = "agent:garden:matrix:channel:!g4rd3n:grove.example"
PARENT_THREAD = "01a2131f-7a40-78e0-af29-d83548f8dbe3"
GARDEN = sync.Agent("garden", "Ada", "/srv/garden", True)


@pytest.fixture
def gateway_calls(monkeypatch, tmp_path):
    """Run as a command the garden agent's session runs, against a fake gateway."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".openclaw/agents/garden/agent/codex-home"))
    monkeypatch.setenv("CODEX_THREAD_ID", PARENT_THREAD)
    for variable in ("TMUX", "TMUX_PANE", "WEZTERM_PANE", "CMUX_SURFACE_ID", "LEMONAID_CHANNEL"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(sync, "agents", lambda cli: {"garden": GARDEN})
    calls: list[tuple[str, dict]] = []

    def call(cli: str, method: str, params: dict, timeout: float) -> dict:
        calls.append((method, params))
        return {"ok": True, "key": params.get("key"), "sessionId": "sid-new"}

    monkeypatch.setattr(gateway, "call", call)
    monkeypatch.setattr(
        openclaw_session.openclaw_scout,
        "ensure",
        lambda channel, lemon_id, cwd: calls.append(("scout", {"channel": channel})) or True,
    )
    return calls


def _brief(name: str) -> Path:
    path = store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Tend the {name}\n\nStatus: working\n")
    return path.resolve()


def _start(capsys, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    lemonaid.launch.cli.add_parser(parser.add_subparsers())
    args = parser.parse_args(["start", "--json", *argv])
    with contextlib.suppress(SystemExit):
        args.func(args)
    return json.loads(capsys.readouterr().out)


def test_a_new_root_session_of_the_callers_agent_gets_its_brief_and_parent(capsys, gateway_calls):
    with db.connect() as conn:
        parent = sessions.Session(PARENT_KEY, "sid-1", "garden", "group", "done", 0, 0, 0)
        lemons.register(conn, parent, PARENT_THREAD, None, "/srv/garden", chat.NAME)
        attached.attach(conn, sessions.channel(PARENT_KEY), _brief("lead"))
    path = _brief("beds")

    started = _start(capsys, "--brief", "beds", "--parent", "self")

    assert started["error"] is None
    [(create, made), (scout, scouted), (send, first)] = gateway_calls
    assert (create, scout, send) == ("sessions.create", "scout", "chat.send")
    assert scouted["channel"] == sessions.channel(made["key"])
    assert "parentSessionKey" not in made
    assert (made["agentId"], made["displayName"]) == ("garden", "Tend the beds")
    key = made["key"]
    assert key.startswith("agent:garden:dashboard:") and first["sessionKey"] == key
    assert f"lemonaid openclaw register --session-key {key}" in first["message"]
    assert str(path) in first["message"]
    with db.connect() as conn:
        row = db.get_by_channel(conn, sessions.channel(key), unread_only=False)
        assert (row.switch_source, row.name, row.metadata["cwd"]) == (
            chat.NAME,
            "Tend the beds",
            "/srv/garden",
        )
        assert attached.by_channel(conn, [row.channel]) == {row.channel: path}
        child = identity.ensure(conn, path)
        assert links.parent_of(conn, child) == started["parent"]


def test_terminal_only_options_are_refused_before_anything_starts(capsys, gateway_calls):
    refused = _start(capsys, "--preset", "codex", "--dry-run")

    assert "--preset, --dry-run" in refused["error"]
    assert gateway_calls == []


def test_harness_arguments_after_the_separator_are_refused(capsys, gateway_calls):
    parser = argparse.ArgumentParser()
    lemon = parser.add_subparsers().add_parser("lemon").add_subparsers()
    lemonaid.launch.cli.add_parser(lemon)
    args = lemonaid.launch.passthrough.parse_args(
        parser, ["lemon", "start", "--json", "--", "--model", "other"]
    )
    with contextlib.suppress(SystemExit):
        args.func(args)

    assert "-- <harness arguments>" in json.loads(capsys.readouterr().out)["error"]
    assert gateway_calls == []


def test_registering_from_inside_keeps_the_name_it_started_with(capsys, gateway_calls):
    _start(capsys, "--brief", str(_brief("beds")))
    key = gateway_calls[0][1]["key"]
    found = sessions.Session(key, "sid-new", "garden", "direct", "", 0, 0, 0)
    child_thread = "01a2132a-0c1d-7000-8000-000000000002"

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sessions, "listed", lambda cli: {key: found})
        patch.setenv("CODEX_THREAD_ID", child_thread)
        with contextlib.suppress(SystemExit):
            lemonaid.openclaw.cli.cmd_register(argparse.Namespace(session_key=key, claim=False))

    with db.connect() as conn:
        row = db.get_by_channel(conn, sessions.channel(key), unread_only=False)
    assert (row.name, row.metadata["codex_thread"]) == ("Tend the beds", child_thread)
