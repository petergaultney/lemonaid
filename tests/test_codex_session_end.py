"""Codex's SessionEnd hook records a quit: Codex reports nothing when it is killed."""

import json

from lemonaid.codex import session_end
from lemonaid.inbox import db

_THREAD = "01a1c858-ae4b-7422-8aa1-225b2a14e84a"


def test_any_report_is_recorded_as_a_quit():
    with db.connect() as conn:
        db.add(conn, f"codex:{_THREAD}", "", metadata={"tty": "/dev/ttys900"})

    session_end.handle_session_end(json.dumps({"session_id": _THREAD, "reason": "other"}))

    with db.connect() as conn:
        row = db.get_by_channel(conn, f"codex:{_THREAD}", unread_only=False)
    assert row is not None
    assert (row.metadata["exit_reason"], row.metadata["exit_deliberate"]) == ("other", True)
    assert row.metadata["tty"] == "/dev/ttys900"


def test_a_hook_without_a_session_changes_nothing():
    session_end.handle_session_end("{}")
    session_end.handle_session_end("not json")
