import argparse
import sqlite3

import pytest

from lemonaid.openclaw import cli, observe, sessions


class _Stop(Exception):
    pass


class _Inline:
    def __init__(self, target, args, daemon):
        self._run = lambda: target(*args)

    def start(self):
        self._run()


def _observed(monkeypatch, refresh, rounds: int, listen=None) -> list[float]:
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        if len(slept) == rounds:
            raise _Stop

    monkeypatch.setattr(observe.sync, "refresh", refresh)
    monkeypatch.setattr(observe.gateway, "hold", lambda on_turn: True)
    monkeypatch.setattr(observe.gateway, "listen", listen or (lambda: None))
    monkeypatch.setattr(observe.time, "sleep", sleep)
    with pytest.raises(_Stop):
        observe.run("openclaw", 30.0, 5.0)
    return slept


def test_observing_syncs_each_round_with_what_it_was_given(monkeypatch):
    calls = []
    slept = _observed(monkeypatch, lambda *args: calls.append(args), rounds=2)

    assert [call[:2] for call in calls] == [("openclaw", 30.0), ("openclaw", 30.0)]
    assert slept == [5.0, 5.0]


@pytest.mark.parametrize(
    "error", [sqlite3.OperationalError("database is locked"), sessions.Unavailable("gateway down")]
)
def test_observing_outlives_a_failed_sync(monkeypatch, error):
    calls = []

    def refresh(*args):
        calls.append(args)
        raise error

    _observed(monkeypatch, refresh, rounds=2)

    assert len(calls) == 2


def test_observe_refuses_without_openclaw(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.sessions, "cli", lambda: str(tmp_path / "openclaw"))
    with pytest.raises(SystemExit, match="no openclaw executable"):
        cli.cmd_observe(argparse.Namespace(days=1.0, every=1.0))


def test_observing_reopens_the_gateway_connection_each_round(monkeypatch):
    listened = []

    def listen():
        listened.append(1)
        raise OSError("gateway down")

    _observed(monkeypatch, lambda *args: None, rounds=2, listen=listen)

    assert len(listened) == 2


def test_a_turn_that_cant_be_recorded_is_logged_not_raised(monkeypatch, caplog):
    def locked(conn, channel, at, started, ended):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(observe.db, "record_turn_times", locked)

    observe._recorder("openclaw")("agent:main:x", 1.0, 1.0, 0)

    assert "agent:main:x" in caplog.text


def test_only_a_turn_that_ended_is_settled(monkeypatch):
    settled = []
    monkeypatch.setattr(observe.db, "record_turn_times", lambda *args: 1)
    monkeypatch.setattr(observe.turn_end, "settle", lambda key, *rest: settled.append((key, *rest)))
    monkeypatch.setattr(observe.threading, "Thread", _Inline)
    record = observe._recorder("openclaw")

    record("agent:main:running", 5.0, 1.0, 0)
    record("agent:main:ended", None, 1.0, 9.0)

    assert [each[:2] for each in settled] == [("agent:main:ended", "openclaw")]
    assert settled[0][3:] == (1.0, False)


def test_a_turn_that_failed_is_settled_as_failed(monkeypatch):
    settled = []
    monkeypatch.setattr(observe.db, "record_turn_times", lambda *args: 1)
    monkeypatch.setattr(observe.turn_end, "settle", lambda *args: settled.append(args[-1]))
    monkeypatch.setattr(observe.threading, "Thread", _Inline)
    monkeypatch.setattr(observe.turns, "_failed", {})
    observe.turns.note(
        {
            "sessionKey": "agent:main:x",
            "runId": "r1",
            "ts": 2000,
            "stream": "lifecycle",
            "data": {"phase": "error", "error": "model down"},
        }
    )

    observe._recorder("openclaw")("agent:main:x", None, 1.0, 2.0)
    observe._recorder("openclaw")("agent:main:x", None, 3.0, 4.0)

    assert settled == [True, False]
