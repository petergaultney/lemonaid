import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import threading
from pathlib import Path

import pytest

from lemonaid.inbox import db
from lemonaid.openclaw import cli, observe, sessions
from lemonaid.rules import hits, patterns, snapshot
from tests.rules import shared


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
    monkeypatch.setattr(observe, "_settle", lambda *args: settled.append(args))
    monkeypatch.setattr(observe.threading, "Thread", _Inline)
    record = observe._recorder("openclaw")

    record("agent:main:running", 5.0, 1.0, 0)
    record("agent:main:ended", None, 1.0, 9.0)

    assert settled == [("agent:main:ended", "openclaw", 1.0)]


def _handed(monkeypatch, said) -> list[dict]:
    """What each `_settle` hands `openclaw hook turn-end`, with the lemon having *said* that."""
    handed = []

    def run(command, input, **kwargs):
        assert command[-3:] == ["openclaw", "hook", "turn-end"]
        handed.append(json.loads(input))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(observe.subprocess, "run", run)
    monkeypatch.setattr(observe.conversation, "final_message", said)
    shared.configure(Path(os.environ["LEMONAID_CONFIG"]), Path("/promoted/patterns.toml"))
    return handed


def test_a_turn_that_failed_is_handed_on_as_failed_without_its_message(monkeypatch):
    handed = _handed(monkeypatch, lambda *args: "Ready to merge?")
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

    observe._settle("agent:main:x", "openclaw", 1.0)
    observe._settle("agent:main:x", "openclaw", 3.0)

    assert handed == [
        {"session_key": "agent:main:x", "said": "", "failed": True},
        {"session_key": "agent:main:x", "said": "Ready to merge?", "failed": False},
    ]


def test_a_final_message_the_gateway_cant_give_is_handed_on_as_none(monkeypatch):
    def down(*args):
        raise OSError("gateway down")

    handed = _handed(monkeypatch, down)

    observe._settle("agent:main:x", "openclaw", 1.0)

    assert handed == [{"session_key": "agent:main:x", "said": "", "failed": False}]


def test_a_turn_settled_from_a_worker_thread_runs_the_rule_check(monkeypatch, tmp_path):
    """The rule check's regex time limit needs a main thread, which the observer's worker isn't."""
    monkeypatch.setenv("LEMONAID_DB", str(tmp_path / "lemonaid.db"))
    source = shared.write(tmp_path / "patterns", shared.MERGE_ASK)
    snapshot.promote(source, patterns.load(source).patterns, dt.datetime.now().astimezone())
    shared.configure(Path(os.environ["LEMONAID_CONFIG"]), source)
    with db.connect() as conn:
        db.add(conn, channel=sessions.channel("agent:main:x"), message="hi", status="read")
    monkeypatch.setattr(observe.conversation, "final_message", lambda *a: "Ready to merge?")

    worker = threading.Thread(target=observe._settle, args=("agent:main:x", "openclaw", 1.0))
    worker.start()
    worker.join(timeout=60)

    assert [json.loads(line)["pattern"] for line in hits.path().read_text().splitlines()] == [
        "merge-ask"
    ]
    with db.connect() as conn:
        assert db.get_by_channel(
            conn, sessions.channel("agent:main:x"), unread_only=False
        ).is_unread
