"""Tests for lemon_watchers shared utilities."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from lemonaid.lemon_watchers import (
    get_latest_activity,
    has_activity_since,
    parse_timestamp,
)


def test_parse_timestamp_zulu():
    ts = parse_timestamp("2026-01-24T12:34:56Z")
    assert ts == datetime(2026, 1, 24, 12, 34, 56, tzinfo=timezone.utc).timestamp()


def test_get_latest_activity_reads_tail(tmp_path):
    session = tmp_path / "session.jsonl"
    entries = [
        {"type": "noise"},
        {"type": "message", "text": "first"},
        {"type": "message", "text": "second"},
    ]
    session.write_text("\n".join(json.dumps(e) for e in entries))

    def describe(entry: dict) -> str | None:
        if entry.get("type") == "message":
            return entry.get("text")
        return None

    assert get_latest_activity(session, describe) == "second"


def test_has_activity_since(tmp_path):
    session = tmp_path / "session.jsonl"
    entries = [
        {"timestamp": "2026-01-24T12:00:00Z", "type": "skip"},
        {"timestamp": "2026-01-24T12:01:00Z", "type": "dismiss"},
    ]
    session.write_text("\n".join(json.dumps(e) for e in entries))

    since = datetime(2026, 1, 24, 12, 0, 30, tzinfo=timezone.utc).timestamp()
    assert has_activity_since(session, since, lambda e: e.get("type") == "dismiss")

    since = datetime(2026, 1, 24, 12, 2, 0, tzinfo=timezone.utc).timestamp()
    assert not has_activity_since(session, since, lambda e: e.get("type") == "dismiss")
