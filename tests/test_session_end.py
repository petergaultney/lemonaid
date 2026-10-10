"""The SessionEnd hook records when a session ended, until the session speaks again."""

import json

from lemonaid.claude import install_hooks, session_end
from lemonaid.inbox import db


def _row(channel: str) -> db.Notification:
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    assert row is not None
    return row


def test_an_exit_is_recorded_with_claudes_reason():
    with db.connect() as conn:
        db.add(conn, "claude:abcd1234", "", metadata={"tty": "/dev/ttys900"})

    session_end.handle_session_end(json.dumps({"session_id": "abcd1234", "reason": "logout"}))

    metadata = _row("claude:abcd1234").metadata
    assert metadata["exit_reason"] == "logout"
    assert metadata["exited_at"] > 0
    assert metadata["tty"] == "/dev/ttys900"


def test_the_next_hook_clears_the_exit():
    with db.connect() as conn:
        db.add(conn, "claude:abcd1234", "")
    session_end.handle_session_end(json.dumps({"session_id": "abcd1234", "reason": "other"}))

    with db.connect() as conn:
        db.register_working(conn, "claude:abcd1234", "Started", metadata={"cwd": "/tmp"})

    assert "exited_at" not in _row("claude:abcd1234").metadata


def test_a_later_notification_clears_the_exit_too():
    with db.connect() as conn:
        db.add(conn, "claude:abcd1234", "")
    session_end.handle_session_end(json.dumps({"session_id": "abcd1234", "reason": "other"}))

    with db.connect() as conn:
        db.add(conn, "claude:abcd1234", "Waiting for input", metadata={"cwd": "/tmp"})

    assert "exit_reason" not in _row("claude:abcd1234").metadata


def test_a_hook_without_a_session_changes_nothing():
    session_end.handle_session_end("{}")
    session_end.handle_session_end("not json")


def test_the_hook_installs_beside_the_users_own(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {"SessionEnd": [{"hooks": [{"command": "mine"}]}]}}))

    install_hooks.install("SessionEnd", install_hooks.SESSION_END_COMMAND, settings)

    entries = json.loads(settings.read_text())["hooks"]["SessionEnd"]
    assert [hook["command"] for entry in entries for hook in entry["hooks"]] == [
        "mine",
        install_hooks.SESSION_END_COMMAND,
    ]
