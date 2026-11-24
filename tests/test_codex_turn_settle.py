"""A Codex turn that ends in an error sends no turn-complete notification; its transcript's
`task_complete` closes it instead."""

import json
import time
from pathlib import Path

from lemonaid.codex import notify, turns
from lemonaid.inbox import db

_THREAD = "01a20eb1-4deb-7e01-a186-41f492b40d0b"
_CHANNEL = f"codex:{_THREAD}"
_REFUSED = {"message": "This content was flagged for possible cybersecurity risk."}


def _event(kind: str, turn: str, **fields) -> str:
    return json.dumps({"type": "event_msg", "payload": {"type": kind, "turn_id": turn, **fields}})


def _transcript(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / f"rollout-{_THREAD}.jsonl"
    path.write_text('{"cut": "a partial first li' + "\n" + "\n".join(lines) + "\n")
    return path


def _started(transcript: Path, turn: str) -> db.Notification:
    with db.connect() as conn:
        db.add(
            conn,
            _CHANNEL,
            "Waiting",
            metadata={"session_id": _THREAD, "session_path": str(transcript)},
        )
    notify.handle_turn_hook(
        json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": _THREAD, "turn_id": turn})
    )
    return _row()


def _row() -> db.Notification:
    with db.connect() as conn:
        found = db.get_by_channel(conn, _CHANNEL, unread_only=False)
    assert found is not None
    return found


def test_a_refused_turn_is_closed_with_why(tmp_path):
    transcript = _transcript(
        tmp_path,
        _event("task_started", "t1"),
        _event("task_complete", "t1", completed_at=100, last_agent_message="ok"),
        _event("task_started", "t2"),
        _event("task_complete", "t2", completed_at=200, error=_REFUSED),
    )
    row = _started(transcript, "t2")
    assert row.turn_at is not None

    with db.connect() as conn:
        turns._settle(conn, row)

    after = _row()
    assert after.turn_at is None
    assert (after.metadata["turn_ended_id"], after.metadata["turn_ended_at"]) == ("t2", 200)
    assert after.message == f"Turn failed: {_REFUSED['message']}"


def test_a_turn_still_running_is_left_open(tmp_path):
    transcript = _transcript(
        tmp_path,
        _event("task_started", "t1"),
        _event("task_complete", "t1", completed_at=100, last_agent_message="ok"),
        _event("task_started", "t2"),
    )
    row = _started(transcript, "t2")

    with db.connect() as conn:
        turns._settle(conn, row)
    assert _row().turn_at == row.turn_at


def test_only_turns_older_than_a_failed_one_takes_are_read(tmp_path):
    transcript = _transcript(
        tmp_path, _event("task_started", "t1"), _event("task_complete", "t1", error=_REFUSED)
    )
    row = _started(transcript, "t1")

    with db.connect() as conn:
        turns.settle_stale(conn, row.turn_at + 1)
        assert _row().turn_at is not None
        turns.settle_stale(conn, time.time() + 60)
    assert _row().turn_at is None
