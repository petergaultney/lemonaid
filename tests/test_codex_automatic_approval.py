"""Automatic approval review must not ask the inbox user for permission."""

import json

import pytest

from lemonaid.codex import notify, permissions
from lemonaid.inbox import db

_THREAD = "01999a7c-2f10-7a3e-9c41-5b2d8e0f1a11"
_TURN = "approval-turn"


@pytest.mark.parametrize(
    ("reviewer", "context_turn", "hook_turn", "suppressed"),
    [
        ("auto_review", _TURN, _TURN, True),
        ("user", _TURN, _TURN, False),
        (None, _TURN, _TURN, False),
        ("auto_review", "previous-turn", _TURN, False),
        ("auto_review", _TURN, "", False),
    ],
)
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    "tool_name", ["Bash", "apply_patch", "mcp__codex_apps__example_write", "unknown", ""]
)
def test_permission_hook_uses_its_own_turn_reviewer(
    monkeypatch, tmp_path, reviewer, context_turn, hook_turn, suppressed, existing, tool_name
):
    rollout = tmp_path / f"rollout-{_THREAD}.jsonl"
    entries = [
        {"type": "session_meta", "payload": {"id": _THREAD, "cwd": "/tmp/project"}},
        {
            "type": "turn_context",
            "payload": {"turn_id": context_turn, "approvals_reviewer": reviewer},
        },
        {"type": "event_msg", "payload": {"message": "x" * 100_000}},
    ]
    rollout.write_text("\n".join(map(json.dumps, entries)) + "\n")
    monkeypatch.setattr(notify, "find_session_path", lambda session_id: rollout)
    channel = f"codex:{_THREAD}"
    with db.connect() as conn:
        if existing:
            db.add(conn, channel=channel, message="Running a tool", status="read")
        before = db.get_by_channel(conn, channel, unread_only=False)

    notify.handle_notification(
        json.dumps(
            {
                "session_id": _THREAD,
                "turn_id": hook_turn,
                "cwd": "/tmp/project",
                "hook_event_name": "PermissionRequest",
                "tool_name": tool_name,
            }
        )
    )

    with db.connect() as conn:
        after = db.get_by_channel(conn, channel, unread_only=False)
    if suppressed and tool_name in ("Bash", "apply_patch"):
        assert after == before
    else:
        assert after.asks
        assert after.message == "Permission needed in tmp/project"


def test_latest_matching_context_wins(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text(
        "\n".join(
            json.dumps({"type": "turn_context", "payload": context})
            for context in [
                {"turn_id": _TURN, "approvals_reviewer": "auto_review"},
                {"turn_id": _TURN, "approvals_reviewer": "user"},
                {"turn_id": "other-turn", "approvals_reviewer": "auto_review"},
            ]
        )
    )
    assert not permissions.automatically_reviewed(rollout, _TURN, "Bash")


@pytest.mark.parametrize(
    "content", ["", "{broken", '"turn_context"', '{"type":"turn_context","payload":null}']
)
def test_unknown_reviewer_keeps_permission_visible(tmp_path, content):
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text(content)
    assert not permissions.automatically_reviewed(rollout, _TURN, "Bash")
    assert not permissions.automatically_reviewed(tmp_path / "missing", _TURN, "Bash")
    assert not permissions.automatically_reviewed(None, _TURN, "Bash")
