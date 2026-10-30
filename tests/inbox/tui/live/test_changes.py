"""A refresh loads only when the database, a watched directory or its request changed."""

import sqlite3
import threading
import time

import pytest

from lemonaid.inbox.tui.live import changes
from lemonaid.watch import kqueue_waits

_kqueue = pytest.mark.skipif(not kqueue_waits.available(), reason="needs kqueue")


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "lemonaid.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE t (x)")
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    (briefs / "a.md").write_text("one")
    found = changes.Changes(path, [briefs], changes.hub())
    yield found, path, briefs
    found.close()


@_kqueue
def test_an_unchanged_inbox_loads_again_only_after_the_full_interval(setup):
    found, _, _ = setup

    assert found.due("request", 100.0)
    assert not found.due("request", 101.0)
    assert found.due("request", 100.0 + changes.FULL_SECONDS)


@_kqueue
def test_a_new_request_loads_at_once(setup):
    found, _, _ = setup
    found.due("request", 100.0)

    assert found.due("another request", 100.1)


@_kqueue
def test_a_commit_by_another_connection_loads(setup):
    found, path, _ = setup
    found.due("request", 100.0)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO t VALUES (1)")

    assert found.due("request", 100.1)
    assert not found.due("request", 100.2)


@_kqueue
def test_an_edited_brief_loads(setup):
    found, _, briefs = setup
    found.due("request", 100.0)

    (briefs / "a.md").write_text("two")

    deadline = time.monotonic() + 5
    while not found.due("request", 100.1):  # once the hub's thread has seen the write
        assert time.monotonic() < deadline
        time.sleep(0.02)


@_kqueue
def test_a_mark_loads(setup):
    found, _, _ = setup
    found.due("request", 100.0)

    found.mark()

    assert found.due("request", 100.1)


class _Hub:
    def watch(self, *args, **kwargs):
        return lambda: None


def test_closing_waits_for_a_read_in_progress(tmp_path, monkeypatch):
    reading, release, closed = threading.Event(), threading.Event(), threading.Event()

    class Connection(sqlite3.Connection):
        def close(self):
            closed.set()
            super().close()

    connect = sqlite3.connect

    def trace(statement):
        if statement == "PRAGMA data_version":
            reading.set()
            assert release.wait(5)

    def held_open(*args, **kwargs):
        conn = connect(*args, **kwargs, factory=Connection)
        conn.set_trace_callback(trace)
        return conn

    monkeypatch.setattr(changes.sqlite3, "connect", held_open)
    found = changes.Changes(tmp_path / "db", [], _Hub())
    results: list[bool] = []
    reader = threading.Thread(target=lambda: results.append(found.due("request", 100.0)))
    closer = threading.Thread(target=found.close)
    reader.start()
    try:
        assert reading.wait(5)
        closer.start()

        assert not closed.wait(0.1)  # the read still holds the connection
    finally:
        release.set()
        reader.join(5)
        closer.join(5)

    assert results == [True] and closed.is_set()
    assert found.due("request", 101.0)  # a tick after closing loads rather than raising


def test_without_kqueue_no_database_is_opened(tmp_path, monkeypatch):
    monkeypatch.setattr(changes.sqlite3, "connect", lambda *a, **k: pytest.fail("connected"))
    found = changes.Changes(tmp_path / "db", [], None)

    assert found.due("request", 100.0) and found.due("request", 100.1)

    found.close()
