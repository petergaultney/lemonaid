"""Tests for the read_lines dispatch in watcher infrastructure.

Verifies that:
- Consumer functions accept a custom read_lines callable
- Backends with read_lines get it resolved via getattr
- Backends without read_lines fall back to read_jsonl_tail
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from lemonaid.lemon_watchers.watcher import (
    check_needs_attention,
    get_latest_activity,
    has_activity_since,
    read_jsonl_tail,
)


def _fake_reader(lines: list[str]):
    """Create a reader that returns canned lines regardless of path."""

    def read_lines(path: Path) -> list[str]:
        return lines

    return read_lines


def test_get_latest_activity_custom_reader():
    """get_latest_activity uses the provided read_lines callable."""
    entries = [
        json.dumps({"type": "msg", "text": "hello", "timestamp": "2026-01-26T10:00:00"}),
    ]
    reader = _fake_reader(entries)

    def describe(entry: dict) -> str | None:
        return entry.get("text")

    result = get_latest_activity(Path("/fake"), describe, read_lines=reader)
    assert result == ("hello", "2026-01-26T10:00:00")


def test_get_latest_activity_default_reader(tmp_path):
    """Without custom reader, falls back to read_jsonl_tail (local file)."""
    session = tmp_path / "session.jsonl"
    entries = [
        json.dumps({"type": "msg", "text": "from file", "timestamp": "2026-01-26T10:00:00"}),
    ]
    session.write_text("\n".join(entries))

    def describe(entry: dict) -> str | None:
        return entry.get("text")

    # No read_lines argument — should use default read_jsonl_tail
    result = get_latest_activity(session, describe)
    assert result == ("from file", "2026-01-26T10:00:00")


def test_has_activity_since_custom_reader():
    """has_activity_since uses the provided read_lines callable."""
    entries = [
        json.dumps({"type": "dismiss", "timestamp": "2026-01-26T12:01:00Z"}),
    ]
    reader = _fake_reader(entries)
    since = datetime(2026, 1, 26, 12, 0, 0, tzinfo=UTC).timestamp()
    result = has_activity_since(Path("/fake"), since, lambda e: e.get("type") == "dismiss", reader)
    assert result is not None
    assert result["type"] == "dismiss"


def test_has_activity_since_custom_reader_no_match():
    """Custom reader returns lines, but none match dismiss criteria."""
    entries = [
        json.dumps({"type": "other", "timestamp": "2026-01-26T12:01:00Z"}),
    ]
    reader = _fake_reader(entries)
    since = datetime(2026, 1, 26, 12, 0, 0, tzinfo=UTC).timestamp()
    result = has_activity_since(Path("/fake"), since, lambda e: e.get("type") == "dismiss", reader)
    assert result is None


def test_check_needs_attention_custom_reader():
    """check_needs_attention uses the provided read_lines callable."""
    entries = [
        json.dumps({"type": "stop", "timestamp": "2026-01-26T12:01:00Z"}),
    ]
    reader = _fake_reader(entries)
    since = datetime(2026, 1, 26, 12, 0, 0, tzinfo=UTC).timestamp()
    result = check_needs_attention(Path("/fake"), since, lambda e: e.get("type") == "stop", reader)
    assert result is not None
    assert result["type"] == "stop"


def test_getattr_resolves_backend_read_lines():
    """getattr on a backend with read_lines returns it; without, returns default."""

    class WithReadLines:
        CHANNEL_PREFIX = "test:"

        @staticmethod
        def read_lines(path: Path) -> list[str]:
            return ["custom"]

    class WithoutReadLines:
        CHANNEL_PREFIX = "other:"

    assert getattr(WithReadLines, "read_lines", read_jsonl_tail) is WithReadLines.read_lines
    assert getattr(WithoutReadLines, "read_lines", read_jsonl_tail) is read_jsonl_tail
