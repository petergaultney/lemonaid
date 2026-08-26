"""A notification that cannot name its session is dropped, not filed."""

import json

import pytest

from lemonaid.claude import notify as claude_notify
from lemonaid.codex import notify as codex_notify
from lemonaid.inbox import db
from lemonaid.inbox.channel import UnidentifiedSession, channel_id
from lemonaid.openclaw import notify as openclaw_notify
from lemonaid.opencode import notify as opencode_notify


def test_a_session_id_becomes_a_channel():
    assert channel_id("claude", "a1b2c3d4e5f6") == "claude:a1b2c3d4"


@pytest.mark.parametrize("missing", ["", None])
def test_no_session_id_is_refused_rather_than_named_unknown(missing):
    with pytest.raises(UnidentifiedSession):
        channel_id("claude", missing)


def _rows():
    with db.connect() as conn:
        return conn.execute("SELECT channel FROM notifications").fetchall()


def test_codex_drops_a_payload_with_no_session(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", str(tmp_path / "inbox.db"))

    codex_notify.handle_notification(
        json.dumps({"type": "agent-turn-complete", "cwd": "/tmp", "last-assistant-message": "hi"})
    )

    assert _rows() == []


def test_codex_keeps_a_payload_that_names_its_thread(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", str(tmp_path / "inbox.db"))

    codex_notify.handle_notification(
        json.dumps(
            {
                "type": "agent-turn-complete",
                "cwd": "/tmp",
                "thread-id": "01a03bff-a7bb-77a2-9b4d-d63cfe32fd00",
                "last-assistant-message": "hi",
            }
        )
    )

    assert [r["channel"] for r in _rows()] == ["codex:01a03bff"]


def test_claude_drops_a_payload_with_no_session(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", str(tmp_path / "inbox.db"))

    claude_notify.handle_notification(json.dumps({"cwd": "/tmp", "hook_event_name": "Stop"}))

    assert _rows() == []


def test_openclaw_refuses_an_unidentified_session():
    with pytest.raises(UnidentifiedSession):
        channel_id("openclaw", "")


def test_opencode_refuses_an_unidentified_session():
    with pytest.raises(UnidentifiedSession):
        opencode_notify._channel_for_session("")


def test_opencode_keeps_the_whole_session_id():
    assert opencode_notify._channel_for_session("abcdefghijkl") == "opencode:abcdefghijkl"


def test_openclaw_module_imports_the_guard():
    assert openclaw_notify.UnidentifiedSession is UnidentifiedSession
