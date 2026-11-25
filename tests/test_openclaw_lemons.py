"""An OpenClaw session registers as a lemon and later finds itself from its Codex thread."""

import argparse

import pytest

from lemonaid.brief import lemon
from lemonaid.front_end import chat
from lemonaid.inbox import db
from lemonaid.openclaw import cli, lemons, sessions

KEY = "agent:garden:matrix:channel:!g4rd3n:grove.example"
THREAD = "01a2131f-7a40-78e0-af29-d83548f8dbe3"
FOUND = sessions.Session(KEY, "sid-1", "garden", "group", "done", 0, 100_000, 258_400)
CHILD_KEY = "agent:garden:dashboard:5a1d"
CHILD = sessions.Session(CHILD_KEY, "sid-2", "garden", "direct", "running", 0, 100_000, 258_400)
CHILD_THREAD = "01a2132a-0c1d-7000-8000-000000000002"


@pytest.fixture
def inside_openclaw(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    home = tmp_path / ".openclaw/agents/garden/agent/codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD)
    monkeypatch.delenv("LEMONAID_CHANNEL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    return home


def test_register_records_the_session_and_its_thread(inside_openclaw):
    with db.connect() as conn:
        lemons.register(conn, FOUND, THREAD, inside_openclaw, "/srv", chat.NAME)
        row = db.get_by_channel(conn, f"openclaw:{KEY}", unread_only=False)

    assert row is not None
    assert row.switch_source == chat.NAME
    assert row.metadata["session_key"] == KEY
    assert row.metadata["codex_thread"] == THREAD
    assert row.metadata["agent_id"] == "garden"


def test_self_channel_inside_openclaw_is_the_registered_session(inside_openclaw):
    with db.connect() as conn:
        lemons.register(conn, FOUND, THREAD, inside_openclaw, "/srv", chat.NAME)

        assert lemon.self_channel(conn) == f"openclaw:{KEY}"


def test_self_channel_follows_a_new_thread_after_reregistering(inside_openclaw, monkeypatch):
    with db.connect() as conn:
        lemons.register(conn, FOUND, THREAD, inside_openclaw, "/srv", chat.NAME)
        lemons.register(conn, FOUND, "01a2-new-thread", inside_openclaw, "/srv", chat.NAME)
        monkeypatch.setenv("CODEX_THREAD_ID", "01a2-new-thread")

        assert lemon.self_channel(conn) == f"openclaw:{KEY}"


def test_a_thread_belongs_to_the_session_that_last_registered_with_it(inside_openclaw):
    with db.connect() as conn:
        lemons.register(conn, FOUND, THREAD, inside_openclaw, "/srv", chat.NAME)
        lemons.register(conn, CHILD, THREAD, inside_openclaw, "/srv", chat.NAME)
        lemons.register(conn, FOUND, THREAD, inside_openclaw, "/srv", chat.NAME)

        assert lemon.self_channel(conn) == f"openclaw:{KEY}"


def test_self_channel_inside_openclaw_never_falls_back_to_codex(inside_openclaw):
    with db.connect() as conn:
        with pytest.raises(LookupError, match="openclaw register --session-key"):
            lemon.self_channel(conn)

        assert lemon.self_channel(conn, fallback="fallback") == "fallback"


def test_a_codex_lemon_outside_openclaw_keeps_its_codex_channel(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD)
    monkeypatch.delenv("LEMONAID_CHANNEL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)

    with db.connect() as conn:
        assert lemon.self_channel(conn) == f"codex:{THREAD}"


def test_register_cli_binds_the_session_to_the_callers_thread(inside_openclaw, monkeypatch, capsys):
    monkeypatch.setattr(sessions, "listed", lambda executable: {KEY: FOUND})

    with pytest.raises(SystemExit) as exit:
        cli.cmd_register(
            argparse.Namespace(session_key=KEY, session_id=None, cwd=None, claim=False)
        )

    assert exit.value.code == 0
    assert capsys.readouterr().out.strip() == f"registered openclaw:{KEY}"
    with db.connect() as conn:
        assert lemon.self_channel(conn) == f"openclaw:{KEY}"


def _register(monkeypatch, key: str, thread: str, claim: bool = False) -> None:
    monkeypatch.setattr(sessions, "listed", lambda executable: {KEY: FOUND, CHILD_KEY: CHILD})
    monkeypatch.setenv("CODEX_THREAD_ID", thread)
    with pytest.raises(SystemExit):
        cli.cmd_register(
            argparse.Namespace(session_key=key, session_id=None, cwd=None, claim=claim)
        )


def _self_channel(monkeypatch, thread: str) -> str:
    monkeypatch.setenv("CODEX_THREAD_ID", thread)
    with db.connect() as conn:
        return lemon.self_channel(conn)


def test_a_lemon_registering_another_session_leaves_both_threads_alone(
    inside_openclaw, monkeypatch, capsys
):
    _register(monkeypatch, KEY, THREAD)
    _register(monkeypatch, CHILD_KEY, CHILD_THREAD)
    _register(monkeypatch, CHILD_KEY, THREAD)

    assert "--claim" in capsys.readouterr().out.splitlines()[-1]
    assert _self_channel(monkeypatch, THREAD) == f"openclaw:{KEY}"
    assert _self_channel(monkeypatch, CHILD_THREAD) == f"openclaw:{CHILD_KEY}"


def test_claim_takes_back_a_thread_another_session_was_given(inside_openclaw, monkeypatch):
    _register(monkeypatch, KEY, THREAD)
    with db.connect() as conn:
        lemons.register(conn, CHILD, THREAD, inside_openclaw, "/srv", chat.NAME)

    _register(monkeypatch, KEY, THREAD)
    assert _self_channel(monkeypatch, THREAD) == f"openclaw:{CHILD_KEY}"

    _register(monkeypatch, KEY, THREAD, claim=True)
    assert _self_channel(monkeypatch, THREAD) == f"openclaw:{KEY}"


def test_register_cli_refuses_a_session_openclaw_doesnt_store(inside_openclaw, monkeypatch, capsys):
    monkeypatch.setattr(sessions, "listed", lambda executable: {})

    with pytest.raises(SystemExit) as exit:
        cli.cmd_register(
            argparse.Namespace(session_key=KEY, session_id=None, cwd=None, claim=False)
        )

    assert exit.value.code == 1
    assert "stores no session" in capsys.readouterr().out
