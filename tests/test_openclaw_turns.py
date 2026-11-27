"""Which OpenClaw turns are running, from the gateway's `agent` events."""

import pytest

from lemonaid.openclaw import turns

KEY = "agent:main:phone"
T = 1795671692000


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(turns, "_ended", {})
    monkeypatch.setattr(turns, "_recorded", {})
    monkeypatch.setattr(turns, "_started", {})


def _event(at: int, stream: str = "assistant", phase: str = "") -> dict:
    return {"sessionKey": KEY, "runId": "r1", "ts": at, "stream": stream, "data": {"phase": phase}}


def _tracked(*events: dict) -> list[tuple]:
    recorded: list[tuple] = []
    for each in events:
        turns.track(each, lambda *told: recorded.append(told))
    return recorded


def test_a_turn_runs_from_its_first_event_until_it_ends():
    assert _tracked(
        _event(T, "lifecycle", "start"),
        _event(T + 500),
        _event(T + 900, "lifecycle", "end"),
    ) == [(KEY, T / 1000, T / 1000, 0), (KEY, None, T / 1000, (T + 900) / 1000)]


def test_a_long_turn_is_recorded_again_each_minute_so_it_never_goes_stale():
    assert _tracked(_event(T), _event(T + 30_000), _event(T + 61_000)) == [
        (KEY, T / 1000, T / 1000, 0),
        (KEY, (T + 61_000) / 1000, T / 1000, 0),
    ]


def test_an_event_from_a_turn_already_over_doesnt_reopen_it():
    assert _tracked(_event(T + 1000, "lifecycle", "end"), _event(T + 1000), _event(T + 400)) == [
        (KEY, None, (T + 1000) / 1000, (T + 1000) / 1000)
    ]


def test_a_retry_after_an_error_runs_again():
    assert _tracked(
        _event(T, "lifecycle", "start"),
        _event(T + 100, "lifecycle", "error"),
        _event(T + 200, "lifecycle", "start"),
    ) == [
        (KEY, T / 1000, T / 1000, 0),
        (KEY, None, T / 1000, (T + 100) / 1000),
        (KEY, (T + 200) / 1000, (T + 200) / 1000, (T + 100) / 1000),
    ]


def test_an_event_without_a_session_is_no_turn():
    assert _tracked({**_event(T), "sessionKey": ""}) == []
