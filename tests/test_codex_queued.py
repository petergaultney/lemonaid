"""lemonaid reads the messages Codex holds in its queue, and says when Codex starts no turn from them."""

import contextlib
import datetime as dt
import json
import shutil
import sqlite3
import time
from pathlib import Path

import pytest

from lemonaid.codex import processes, queued
from lemonaid.codex import utils as codex_utils
from lemonaid.inbox import db
from lemonaid.messages import recipient

_HELD = queued.held  # conftest stubs it for every other test
_THREAD = "019a5a00-1111-7222-8333-444455556666"
_SCHEMA = """
CREATE TABLE queued_items (
    id TEXT PRIMARY KEY NOT NULL,
    thread_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    queue_order INTEGER NOT NULL,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);
"""


def _queue(home: Path, *rows: tuple[str, float], wal: bool = False) -> Path:
    """Codex's queue database in *home*, holding a message for each (thread, time queued)."""
    home.mkdir(parents=True, exist_ok=True)
    path = home / "queue_1.sqlite"
    with contextlib.closing(sqlite3.connect(path)) as conn:
        if wal:
            conn.execute("PRAGMA journal_mode=wal")
        conn.executescript(_SCHEMA)
        conn.executemany(
            "INSERT INTO queued_items VALUES (?, ?, '{}', ?, ?, ?)",
            [
                (f"item-{n}", thread, n, int(at * 1000), int(at * 1000))
                for n, (thread, at) in enumerate(rows)
            ],
        )
        conn.commit()
    return path


def _event(kind: str, at: float, **fields: str) -> str:
    stamp = dt.datetime.fromtimestamp(at, dt.UTC).isoformat().replace("+00:00", "Z")
    return json.dumps(
        {"timestamp": stamp, "type": "event_msg", "payload": {"type": kind, **fields}}
    )


def _rollout(path: Path, *events: str) -> Path:
    path.write_text(
        "\n".join([json.dumps({"type": "session_meta", "payload": {}}), *events]) + "\n"
    )
    return path


def test_held_counts_each_thread_s_messages_from_its_oldest(tmp_path):
    _queue(tmp_path, ("a", 1000.0), ("a", 1005.5), ("b", 2000.0))

    assert _HELD(tmp_path) == {"a": queued.Held(2, 1000.0), "b": queued.Held(1, 2000.0)}


def _add(conn: sqlite3.Connection, item: str, thread: str, at: float) -> None:
    conn.execute(
        "INSERT INTO queued_items VALUES (?, ?, '{}', 99, ?, ?)",
        (item, thread, int(at * 1000), int(at * 1000)),
    )
    conn.commit()


def _files(home: Path) -> dict[str, tuple[bytes, int, int]]:
    """Each file in *home*, with its bytes, size and modification time."""
    return {
        path.name: (path.read_bytes(), path.stat().st_size, path.stat().st_mtime_ns)
        for path in home.iterdir()
    }


def test_held_reads_a_copy_and_opens_nothing_in_the_codex_home(tmp_path, monkeypatch):
    home = tmp_path / "codex"
    _queue(home, ("a", 1000.0))
    opened = []
    connect = sqlite3.connect
    monkeypatch.setattr(
        queued.sqlite3,
        "connect",
        lambda target, **kw: opened.append(Path(target)) or connect(target, **kw),
    )
    before = _files(home)

    assert _HELD(home) == {"a": queued.Held(1, 1000.0)}
    assert len(opened) == 1 and not opened[0].is_relative_to(home)
    assert _files(home) == before


def test_held_reads_the_wal_of_a_database_codex_has_open_and_changes_none_of_its_files(tmp_path):
    home = tmp_path / "codex"
    path = _queue(home, ("a", 1000.0), wal=True)

    with contextlib.closing(sqlite3.connect(path)) as codex:
        _add(codex, "late", "b", 2000.0)  # only in the WAL until a checkpoint
        assert (home / "queue_1.sqlite-wal").stat().st_size > 0
        before = _files(home)

        assert _HELD(home) == {"a": queued.Held(1, 1000.0), "b": queued.Held(1, 2000.0)}
        assert _files(home) == before


def test_held_reads_a_wal_database_no_process_has_open_and_creates_no_files(tmp_path):
    home = tmp_path / "codex"
    _queue(home, ("a", 1000.0), wal=True)
    before = _files(home)

    assert _HELD(home) == {"a": queued.Held(1, 1000.0)}
    assert _files(home) == before
    assert list(before) == ["queue_1.sqlite"]


def _writing_during_copies(monkeypatch, path: Path, writes: int) -> list[Path]:
    """Codex adds a row to the queue at *path* during each of the first *writes* copies."""
    copied: list[Path] = []
    copy = shutil.copyfile

    def copy_while_codex_writes(source, target):
        copy(source, target)
        copied.append(Path(source))
        if len(copied) <= writes:
            with contextlib.closing(sqlite3.connect(path)) as codex:
                _add(codex, f"late-{len(copied)}", "a", 3000.0)

    monkeypatch.setattr(queued.shutil, "copyfile", copy_while_codex_writes)
    return copied


def test_held_copies_again_when_codex_writes_during_the_copy(tmp_path, monkeypatch):
    home = tmp_path / "codex"
    path = _queue(home, ("a", 1000.0), wal=True)
    copied = _writing_during_copies(monkeypatch, path, writes=1)

    assert _HELD(home) == {"a": queued.Held(2, 1000.0)}
    assert len(copied) > 1


def test_held_is_empty_when_codex_writes_during_every_copy(tmp_path, monkeypatch):
    home = tmp_path / "codex"
    path = _queue(home, ("a", 1000.0), wal=True)
    _writing_during_copies(monkeypatch, path, writes=1000)

    assert _HELD(home) == {}


def test_held_is_empty_without_a_database_or_with_an_unknown_one(tmp_path):
    assert _HELD(tmp_path) == {}

    (tmp_path / "queue_1.sqlite").write_text("not a database, but long enough for a header")
    assert _HELD(tmp_path) == {}


def test_a_completed_turn_ends_it_and_an_interrupt_is_named(tmp_path):
    done = _rollout(
        tmp_path / "done.jsonl", _event("task_started", 10.0), _event("task_complete", 20.0)
    )
    stopped = _rollout(
        tmp_path / "stopped.jsonl",
        _event("task_started", 10.0),
        _event("turn_aborted", 30.0, reason="interrupted"),
    )

    assert queued.last_turn_end(done) == queued.TurnEnd(20.0, False)
    assert queued.last_turn_end(stopped) == queued.TurnEnd(30.0, True)


def test_an_open_turn_or_a_tail_without_a_boundary_has_no_end(tmp_path):
    running = _rollout(
        tmp_path / "running.jsonl", _event("task_complete", 5.0), _event("task_started", 10.0)
    )
    fresh = _rollout(tmp_path / "fresh.jsonl")

    assert queued.last_turn_end(running) is None
    assert queued.last_turn_end(fresh) is None


@pytest.mark.parametrize(
    ("since", "ended", "now"),
    [
        (1000.0, 900.0, 1059.0),  # queued 59 seconds ago, on an idle thread
        (900.0, 1000.0, 1059.0),  # queued during a turn that ended 59 seconds ago
    ],
)
def test_a_message_codex_may_still_start_is_not_unrun(since, ended, now):
    found = queued.Held(1, since)

    assert queued.unrun(found, queued.TurnEnd(ended, False), now) == ""
    assert queued.unrun(found, queued.TurnEnd(ended, True), now) == ""
    assert queued.unrun(found, None, now + 3600) == ""  # a turn is open


def test_a_message_held_a_minute_on_an_idle_thread_is_unrun():
    found = queued.Held(2, 1000.0)

    assert queued.unrun(found, queued.TurnEnd(900.0, False), 1300.0) == (
        "Codex has held 2 queued messages for 5 minutes on an idle thread and started no turn"
    )
    assert queued.unrun(queued.Held(1, 1000.0), queued.TurnEnd(900.0, True), 1060.0) == (
        "an interrupt (Esc) ended its last turn, so Codex starts no turn from "
        "a queued message until its user's next prompt"
    )


def _codex(monkeypatch, tmp_path, events: list[str], queued_at: float, open_threads=None) -> None:
    """A Codex thread whose rollout has *events*, with a message Codex took at *queued_at*."""
    rollout = _rollout(tmp_path / f"rollout-{_THREAD}.jsonl", *events)
    monkeypatch.setattr(queued, "held", lambda home: {_THREAD: queued.Held(1, queued_at)})
    monkeypatch.setattr(codex_utils, "find_session_path", lambda thread: rollout)
    monkeypatch.setattr(
        processes,
        "open_threads",
        lambda max_age=0.0: {_THREAD} if open_threads is None else open_threads,
    )
    with db.connect() as conn:
        db.add(conn, f"codex:{_THREAD}", "", metadata={"session_id": _THREAD})


def test_an_interrupted_thread_s_held_message_is_unrun_by_channel(monkeypatch, tmp_path):
    now = time.time()
    _codex(
        monkeypatch, tmp_path, [_event("turn_aborted", now - 300, reason="interrupted")], now - 120
    )

    found = recipient.unrun_codex()

    assert list(found) == [f"codex:{_THREAD}"]
    assert "an interrupt (Esc)" in found[f"codex:{_THREAD}"]


def test_a_thread_no_codex_process_has_open_is_left_to_the_dead_check(monkeypatch, tmp_path):
    now = time.time()
    _codex(monkeypatch, tmp_path, [_event("task_complete", now - 300)], now - 120, set())

    assert recipient.unrun_codex() == {}


def test_a_message_held_while_a_turn_runs_is_not_unrun(monkeypatch, tmp_path):
    now = time.time()
    _codex(monkeypatch, tmp_path, [_event("task_started", now - 600)], now - 300)

    assert recipient.unrun_codex() == {}
