"""Tests for lemon_watchers shared utilities."""

import json
import threading
from datetime import UTC, datetime

import pytest

from lemonaid.lemon_watchers import (
    ModelInfo,
    fish_path,
    get_latest_activity,
    has_activity_since,
    parse_timestamp,
    watcher,
)
from lemonaid.lemon_watchers.watcher import _latest_model


def test_started_watcher_can_be_stopped_and_joined():
    polled = threading.Event()

    def get_active():
        polled.set()
        return []

    watcher.start_unified_watcher([], get_active, lambda _channel: 0, lambda _channel, _message: 0)
    assert polled.wait(1)

    watcher.stop_unified_watcher()

    assert watcher._watcher_thread is None
    assert watcher._watcher_stop is None


def test_latest_model_uses_the_newest_entry_that_names_one():
    entries = [
        {"model": "gpt-5.6-sol"},
        {"type": "tool"},
        {"model": "gpt-5.6-terra"},
    ]

    def extract(entry: dict) -> ModelInfo | None:
        return ModelInfo("openai", entry["model"]) if "model" in entry else None

    assert _latest_model(entries, extract) == ("openai", "gpt-5.6-sol")


def test_watch_loop_restores_model_metadata_erased_by_an_older_hook(tmp_path, monkeypatch):
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-09-22T18:00:00Z",
                "model": "claude-opus-5-5",
            }
        )
    )

    class Backend:
        CHANNEL_PREFIX = "claude:"

        @staticmethod
        def get_session_path(_session_id, _cwd):
            return session

        @staticmethod
        def get_model(entry):
            model = entry.get("model")
            return ModelInfo("anthropic", model) if model else None

        @staticmethod
        def describe_activity(_entry):
            return None

        @staticmethod
        def should_dismiss(_entry):
            return False

    saved: dict[str, ModelInfo] = {}
    recorded: list[ModelInfo] = []
    polls = 0

    def record_model(channel: str, provider: str, model: str) -> None:
        observed = ModelInfo(provider, model)
        recorded.append(observed)
        saved[channel] = observed

    def finish_poll(_seconds: float) -> None:
        nonlocal polls
        polls += 1
        if polls == 1:
            session.write_text(json.dumps({"type": "noise"}))
            saved.clear()
            return
        raise StopIteration

    monkeypatch.setattr(watcher.time, "sleep", finish_poll)

    with pytest.raises(StopIteration):
        watcher.unified_watch_loop(
            [Backend],
            lambda: [("claude:abc", "abc", "/tmp", 0.0, False, None, "", None)],
            lambda _channel: 0,
            lambda _channel, _message: 0,
            record_model=record_model,
            models=lambda: dict(saved),
            poll_interval=0,
        )

    assert recorded == [
        ModelInfo("anthropic", "claude-opus-5-5"),
        ModelInfo("anthropic", "claude-opus-5-5"),
    ]


def test_watch_loop_retries_transcript_that_appears_after_session_hook(tmp_path, monkeypatch):
    session = tmp_path / "session.jsonl"
    path_lookups = 0

    class Backend:
        CHANNEL_PREFIX = "claude:"

        @staticmethod
        def get_session_path(_session_id, _cwd):
            nonlocal path_lookups
            path_lookups += 1
            if path_lookups == 1:
                return None
            return session

        @staticmethod
        def get_model(entry):
            model = entry.get("model")
            return ModelInfo("anthropic", model) if model else None

        @staticmethod
        def describe_activity(_entry):
            return None

        @staticmethod
        def should_dismiss(_entry):
            return False

    recorded: list[ModelInfo] = []
    polls = 0

    def finish_poll(_seconds: float) -> None:
        nonlocal polls
        polls += 1
        if polls == 1:
            session.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": "2026-09-23T18:00:00Z",
                        "model": "claude-opus-5-5",
                    }
                )
            )
            return
        raise StopIteration

    monkeypatch.setattr(watcher, "_MISSING_SESSION_RETRY_SECONDS", 0.0)
    monkeypatch.setattr(watcher.time, "sleep", finish_poll)

    with pytest.raises(StopIteration):
        watcher.unified_watch_loop(
            [Backend],
            lambda: [("claude:abc", "abc", "/tmp", 0.0, False, None, "", None)],
            lambda _channel: 0,
            lambda _channel, _message: 0,
            record_model=lambda _channel, provider, model: recorded.append(
                ModelInfo(provider, model)
            ),
            models=dict,
            poll_interval=0,
        )

    assert path_lookups == 2
    assert recorded == [ModelInfo("anthropic", "claude-opus-5-5")]


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


def test_fish_path_under_home(monkeypatch):
    monkeypatch.setattr(
        "lemonaid.lemon_watchers.common.Path.home",
        staticmethod(lambda: __import__("pathlib").Path("/Users/peter")),
    )
    assert fish_path("/Users/peter/play/lemonaid") == "~/p/lemonaid"
    assert fish_path("/Users/peter/work/ds-monorepo/libs/gent") == "~/w/d/l/gent"


def test_fish_path_shallow(monkeypatch):
    monkeypatch.setattr(
        "lemonaid.lemon_watchers.common.Path.home",
        staticmethod(lambda: __import__("pathlib").Path("/Users/peter")),
    )
    assert fish_path("/Users/peter/play") == "~/play"
    assert fish_path("/Users/peter") == "~"


def test_fish_path_absolute():
    assert fish_path("/etc/nginx/conf.d") == "/e/n/conf.d"


def test_fish_path_empty():
    assert fish_path("") == ""
