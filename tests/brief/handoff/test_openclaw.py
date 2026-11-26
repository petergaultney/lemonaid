"""A handoff to OpenClaw starts its receiver as a new root session once the source is ready."""

import argparse
import time
from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from lemonaid.brief import attached
from lemonaid.brief.handoff import cli as handoff_cli
from lemonaid.brief.handoff import coordinator as handoff_coordinator
from lemonaid.brief.handoff import launch as handoff_launch
from lemonaid.brief.handoff import pane as handoff_tmux
from lemonaid.brief.handoff import request as handoff_request
from lemonaid.brief.handoff import self_started
from lemonaid.brief.handoff import state as handoff_state
from lemonaid.inbox import db
from lemonaid.openclaw import gateway, lemons, sessions, sync

THREAD = "01a2132a-0c1d-7000-8000-000000000002"


def test_openclaw_names_its_own_destination():
    assert handoff_launch.destination("openclaw") == "openclaw"


@pytest.mark.parametrize(
    "pane", [("", "", "", ""), ("work", "2", "@2", "%2")], ids=["no pane", "tmux pane"]
)
def test_the_receiver_is_a_new_session_that_accepts_and_takes_the_brief(
    setup, monkeypatch, tmp_path, pane
):
    conn, path = setup
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        sync, "agents", lambda cli: {"main": sync.Agent("main", "Ada", str(tmp_path), True)}
    )
    monkeypatch.setattr(
        gateway,
        "call",
        lambda cli, method, params, timeout: calls.append((method, params)) or {"sessionId": "s"},
    )
    monkeypatch.setattr(handoff_tmux, "has_pane", lambda *_: True)
    monkeypatch.setattr(
        self_started,
        "_stop_sender",
        lambda conn, row: calls.append(("hold", {"pane": row["source_pane_id"]})) or "4242",
    )
    row = handoff_state.request(
        conn, path, "claude:old", "openclaw", *pane, str(tmp_path), time.time() + 600
    )
    path.write_text(
        path.read_text().replace("Old notes.", f"Notes.\nHandoff-Ready: {row['token']}")
    )

    report = handoff_coordinator.advance(conn, row["token"])

    held = [("hold", {"pane": pane[3]})] if pane[3] else []
    assert calls[: len(held)] == held  # a sender in a pane stops before the receiver starts
    [(create, made), (send, first)] = calls[len(held) :]
    assert (create, send) == ("sessions.create", "chat.send")
    assert "parentSessionKey" not in made and made["agentId"] == "main"
    target = sessions.channel(made["key"])
    assert (report["phase"], report["target"], report.get("start_command")) == (
        "launched",
        target,
        None,
    )
    assert f"brief handoff accept {row['token']}" in first["message"]
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path

    found = sessions.Session(made["key"], "s", "main", "direct", "", 0, 0, 0)
    lemons.register(conn, found, THREAD, None, str(tmp_path), "openclaw-chat", "Handoff")
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".openclaw/agents/main/agent/codex-home"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LEMONAID_CHANNEL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.setattr(handoff_cli.db, "connect", lambda: nullcontext(conn))
    monkeypatch.setattr(handoff_cli.request.subprocess, "Popen", Mock())
    handoff_cli._cmd(argparse.Namespace(watch=False, to=None, token=row["token"], action="accept"))

    assert attached.by_channel(conn, [target])[target] == path
    assert db.get_by_channel(conn, "claude:old", unread_only=False).status == "archived"


@pytest.mark.parametrize("archived", [False, True], ids=["live", "archived"])
def test_the_request_to_an_openclaw_lemon_starts_its_scout(setup, monkeypatch, tmp_path, archived):
    conn, path = setup
    source = sessions.channel("agent:main:dashboard:5a1d")
    found = sessions.Session(
        source.removeprefix(sessions.PREFIX), "s", "main", "direct", "", 0, 0, 0
    )
    lemons.register(conn, found, "", None, str(tmp_path), "openclaw-chat", "Source")
    attached.attach(conn, source, path)
    if archived:
        db.archive_channel(conn, source, "quiet", cause="archived", by="user")
    started = []
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(path.parent))
    sent = Mock()
    monkeypatch.setattr(handoff_request.to_brief, "send", sent)
    monkeypatch.setattr(
        handoff_request.openclaw_scout,
        "ensure",
        lambda channel, lemon_id, cwd: started.append((channel, cwd)) or True,
    )

    handoff_request.prepare(conn, "openclaw", brief=str(path))

    assert started == [(source, str(tmp_path))]
    assert not db.get_by_channel(conn, source, unread_only=False).is_archived
    [(_, message)] = [call.args for call in sent.call_args_list]
    assert f"lemonaid openclaw register --session-key {found.key}" in message
    assert str(path) in message
