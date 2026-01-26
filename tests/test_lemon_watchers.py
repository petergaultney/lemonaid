"""Tests for lemon_watchers shared utilities."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from lemonaid.lemon_watchers import (
    get_latest_activity,
    has_activity_since,
    parse_timestamp,
)


def test_parse_timestamp_zulu():
    ts = parse_timestamp("2026-01-24T12:34:56Z")
    assert ts == datetime(2026, 1, 24, 12, 34, 56, tzinfo=UTC).timestamp()


def test_get_latest_activity_reads_tail(tmp_path):
    session = tmp_path / "session.jsonl"
    entries = [
        {"type": "noise"},
        {"type": "message", "text": "first", "timestamp": "2026-01-26T10:00:00"},
        {"type": "message", "text": "second", "timestamp": "2026-01-26T10:00:01"},
    ]
    session.write_text("\n".join(json.dumps(e) for e in entries))

    def describe(entry: dict) -> str | None:
        if entry.get("type") == "message":
            return entry.get("text")
        return None

    result = get_latest_activity(session, describe)
    assert result == ("second", "2026-01-26T10:00:01")


def test_has_activity_since(tmp_path):
    session = tmp_path / "session.jsonl"
    entries = [
        {"timestamp": "2026-01-24T12:00:00Z", "type": "skip"},
        {"timestamp": "2026-01-24T12:01:00Z", "type": "dismiss"},
    ]
    session.write_text("\n".join(json.dumps(e) for e in entries))

    since = datetime(2026, 1, 24, 12, 0, 30, tzinfo=UTC).timestamp()
    assert has_activity_since(session, since, lambda e: e.get("type") == "dismiss")

    since = datetime(2026, 1, 24, 12, 2, 0, tzinfo=UTC).timestamp()
    assert not has_activity_since(session, since, lambda e: e.get("type") == "dismiss")
