"""Tests for lemonaid.opencode.watcher module."""

import json
import sqlite3
from pathlib import Path

from lemonaid.opencode import watcher


def test_describe_activity_tool_bash():
    entry = {
        "part": {
            "type": "tool",
            "tool": "bash",
            "state": {
                "input": {
                    "command": "pytest tests/test_opencode_watcher.py",
                }
            },
        }
    }
    assert watcher.describe_activity(entry) == "Running: pytest tests/test_opencode_watcher.py"


def test_should_dismiss_user_activity():
    entry = {"role": "user", "part": {"type": "text", "text": "continue"}}
    assert watcher.should_dismiss(entry) is True


def test_needs_attention_on_step_finish_stop():
    entry = {"role": "assistant", "part": {"type": "step-finish", "reason": "stop"}}
    assert watcher.needs_attention(entry) is True


def test_needs_attention_false_on_tool_calls_finish():
    entry = {"role": "assistant", "part": {"type": "step-finish", "reason": "tool-calls"}}
    assert watcher.needs_attention(entry) is False


def test_read_lines_from_sqlite(tmp_path: Path):
    db_path = tmp_path / "opencode.db"
    session_id = "ses_test123"
    message_id = "msg_1"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT, time_created INTEGER)"
        )
        conn.execute(
            "CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, data TEXT, time_created INTEGER)"
        )
        conn.execute(
            "INSERT INTO message (id, session_id, data, time_created) VALUES (?, ?, ?, ?)",
            (message_id, session_id, json.dumps({"role": "assistant"}), 1_700_000_000_000),
        )
        conn.execute(
            "INSERT INTO part (id, message_id, session_id, data, time_created) VALUES (?, ?, ?, ?, ?)",
            (
                "prt_1",
                message_id,
                session_id,
                json.dumps({"type": "text", "text": "hello"}),
                1_700_000_000_123,
            ),
        )
        conn.commit()

    lines = watcher.read_lines(Path(f"{db_path}#{session_id}"))
    assert len(lines) == 1

    parsed = json.loads(lines[0])
    assert parsed["role"] == "assistant"
    assert parsed["part"]["type"] == "text"
    assert parsed["timestamp"].endswith("Z")
