"""Notify finds UUIDv7 rollouts without walking unrelated session history."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from lemonaid.codex import notify, utils

_THREAD = "01a15bb9-250e-7b00-85b9-1dd66e595f01"


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_uuid_timestamp_finds_rollout_on_adjacent_local_days(tmp_path, monkeypatch, offset):
    day = datetime.fromtimestamp((UUID(_THREAD).int >> 80) / 1000, UTC).date()
    directory = tmp_path / (day + timedelta(days=offset)).strftime("%Y/%m/%d")
    directory.mkdir(parents=True)
    path = directory / f"rollout-2026-10-20T19-50-22-{_THREAD}.jsonl"
    path.write_text(json.dumps({"type": "session_meta", "payload": {"id": _THREAD}}) + "\n")
    monkeypatch.setattr(utils, "get_sessions_root", lambda: tmp_path)
    assert utils.find_session_path(_THREAD) == path


def test_missing_uuid_uses_only_three_date_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "get_sessions_root", lambda: tmp_path)
    visited = []
    original = type(tmp_path).glob

    def glob(path, pattern):
        visited.append((path.relative_to(tmp_path).as_posix(), pattern))
        return original(path, pattern)

    monkeypatch.setattr(type(tmp_path), "glob", glob)
    monkeypatch.setattr(
        type(tmp_path), "rglob", lambda *args: pytest.fail("no recursive history scan")
    )
    assert utils.find_session_path(_THREAD) is None
    assert visited == [
        (day, f"rollout-*-{_THREAD}.jsonl") for day in ("2026/10/20", "2026/10/19", "2026/10/21")
    ]


def test_reported_thread_cannot_borrow_an_explicit_sibling_rollout(tmp_path, monkeypatch):
    sibling = tmp_path / "sibling.jsonl"
    sibling.write_text("{}\n")
    monkeypatch.setattr(notify, "find_session_path", lambda thread: None)
    monkeypatch.setattr(
        notify, "find_latest_session_for_cwd", lambda cwd: pytest.fail("no cwd fallback")
    )
    assert notify._resolve_session_path(_THREAD, "/shared", str(sibling)) is None
