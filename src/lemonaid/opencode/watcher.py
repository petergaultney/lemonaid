"""OpenCode session watcher backend."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .utils import get_db_path

CHANNEL_PREFIX = "opencode:"


def _to_iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def get_session_path(session_id: str, cwd: str) -> Path | None:
    """Return a synthetic path encoding db-path and session id."""
    if not session_id:
        return None

    db_path = get_db_path()
    if not db_path.exists():
        return None

    return Path(f"{db_path}#{session_id}")


def read_lines(session_path: Path) -> list[str]:
    """Read recent session parts from OpenCode SQLite DB as JSONL-style lines."""
    raw_path = str(session_path)
    if "#" not in raw_path:
        return []

    db_path_str, session_id = raw_path.rsplit("#", 1)
    if not session_id:
        return []

    query = """
        SELECT recent.part_data, recent.time_created, recent.message_data
        FROM (
            SELECT p.data AS part_data, p.time_created AS time_created, m.data AS message_data
            FROM part p
            JOIN message m ON m.id = p.message_id
            WHERE p.session_id = ?
            ORDER BY p.time_created DESC
            LIMIT 120
        ) AS recent
        ORDER BY recent.time_created ASC
    """

    try:
        with sqlite3.connect(db_path_str) as conn:
            rows = conn.execute(query, (session_id,)).fetchall()
    except sqlite3.Error:
        return []

    lines: list[str] = []
    for part_data_raw, ts_ms, message_data_raw in rows:
        try:
            part_data = json.loads(part_data_raw)
            message_data = json.loads(message_data_raw)
        except (TypeError, json.JSONDecodeError):
            continue

        if not isinstance(ts_ms, int):
            continue

        lines.append(
            json.dumps(
                {
                    "timestamp": _to_iso(ts_ms),
                    "type": "part",
                    "role": message_data.get("role"),
                    "part": part_data,
                }
            )
        )

    return lines


def _describe_tool(part: dict[str, object]) -> str:
    tool_name_obj = part.get("tool", "unknown")
    tool_name = tool_name_obj if isinstance(tool_name_obj, str) else "unknown"
    state_obj = part.get("state")
    state: dict[str, object] = state_obj if isinstance(state_obj, dict) else {}
    input_obj = state.get("input")
    tool_input: dict[str, object] = input_obj if isinstance(input_obj, dict) else {}

    if tool_name == "read":
        path = tool_input.get("filePath", "")
        if isinstance(path, str) and path:
            return f"Reading {Path(path).name}"
        return "Reading file"

    if tool_name in ("edit", "write"):
        path = tool_input.get("filePath", "")
        if isinstance(path, str) and path:
            return f"Editing {Path(path).name}"
        return "Editing file"

    if tool_name == "bash":
        cmd = tool_input.get("command", "")
        if isinstance(cmd, str) and cmd:
            return f"Running: {cmd[:120]}" if len(cmd) <= 120 else f"Running: {cmd[:117]}..."
        return "Running command"

    if tool_name in ("grep", "glob"):
        pattern = tool_input.get("pattern", "")
        if isinstance(pattern, str) and pattern:
            return f"Searching: {pattern[:80]}"
        return "Searching"

    if tool_name == "webfetch":
        return "Fetching web content"

    return f"Using {tool_name}"


def describe_activity(entry: dict) -> str | None:
    """Extract a human-readable description of what OpenCode is doing."""
    part = entry.get("part")
    if not isinstance(part, dict):
        return None

    part_type = part.get("type")
    if part_type == "tool":
        return _describe_tool(part)

    if part_type == "reasoning":
        return "Thinking..."

    if part_type == "text":
        text = part.get("text", "")
        if isinstance(text, str) and text.strip():
            first_line = text.strip().split("\n")[0][:200]
            if len(first_line) < len(text.strip().split("\n")[0]):
                first_line += "..."
            return first_line

    if part_type == "step-start":
        return "Working..."

    return None


def should_dismiss(entry: dict) -> bool:
    """Check if a session entry indicates we should dismiss notification."""
    role = entry.get("role")
    part = entry.get("part")
    if not isinstance(part, dict):
        return False

    if role in ("assistant", "user"):
        return True

    return part.get("type") in ("tool", "reasoning", "text", "step-start", "step-finish")


def needs_attention(entry: dict) -> bool:
    """Return True when OpenCode indicates assistant turn completion.

    OpenCode emits assistant `step-finish` parts with `reason: "stop"`
    when a turn is complete and waiting for user input.
    """
    part_obj = entry.get("part")
    if not isinstance(part_obj, dict):
        return False
    part: dict[str, object] = part_obj

    return part.get("type") == "step-finish" and part.get("reason") == "stop"
