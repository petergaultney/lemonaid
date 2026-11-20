"""Codex's PermissionRequest hook marks its lemon stuck on a prompt."""

import json

import pytest

from lemonaid.codex import notify
from lemonaid.inbox import db
from tests import codex_fakes

_THREAD = "01999a7c-2f10-7a3e-9c41-5b2d8e0f1a11"


@pytest.fixture(autouse=True)
def _notification_rollouts(monkeypatch, tmp_path, codex_records):
    codex_records.everything = lambda thread: codex_fakes.thread(
        thread, path=str(tmp_path / f"rollout-{thread}.jsonl")
    )
    monkeypatch.delenv("TMUX_PANE", raising=False)


def test_a_permission_request_hook_is_a_prompt_not_a_finished_turn():
    notify.handle_notification(
        json.dumps(
            {
                "session_id": _THREAD,
                "cwd": "/tmp/project",
                "hook_event_name": "PermissionRequest",
                "tool_name": "Bash",
            }
        )
    )

    with db.connect() as conn:
        row = db.get_by_channel(conn, f"codex:{_THREAD}", unread_only=False)
    assert row.message == "Permission needed in tmp/project"
    assert row.asks
