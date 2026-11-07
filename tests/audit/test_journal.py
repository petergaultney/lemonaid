import fcntl
import threading
import time
from pathlib import Path

from lemonaid.audit import journal


def test_append_rotates_past_the_size_limit_and_read_returns_both_files_oldest_first(
    monkeypatch,
):
    monkeypatch.setattr(journal, "_MAX_BYTES", 10)

    journal.append("x.log", {"n": 1, "pad": "x" * 20})
    journal.append("x.log", {"n": 2})

    assert [e["n"] for e in journal.read("x.log")] == [1, 2]
    assert journal.path("x.log").with_name("x.log.1").exists()
    assert len(journal.path("x.log").read_text().splitlines()) == 1


def test_malformed_lines_are_skipped():
    journal.path("x.log").parent.mkdir(parents=True)
    journal.path("x.log").write_text('not json\n{"key": "a"}\n')

    assert list(journal.read("x.log")) == [{"key": "a"}]


def test_a_failed_write_is_logged_not_raised(monkeypatch, tmp_path):
    (tmp_path / "blocked").write_text("a file where the state directory should be")
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path / "blocked"))

    journal.append("x.log", {"n": 1})

    assert not journal.path("x.log").exists()


def test_writers_racing_to_rotate_keep_the_retained_file(monkeypatch):
    """Both writers see the file oversized; only the first, holding the lock, rotates it."""
    monkeypatch.setattr(journal, "_MAX_BYTES", 30)
    journal.append("x.log", {"n": "old", "pad": "x" * 40})
    started = threading.Barrier(2)
    real_replace = Path.replace

    def slow_replace(self, target):
        time.sleep(0.05)
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", slow_replace)

    def write(n):
        started.wait()
        journal.append("x.log", {"n": n})

    threads = [threading.Thread(target=write, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(e["n"] for e in journal.read("x.log")) == ["a", "b", "old"]


def test_a_writer_that_cannot_get_the_lock_still_appends(monkeypatch):
    monkeypatch.setattr(journal, "_LOCK_SECONDS", 0.05)
    journal.append("x.log", {"n": 1})
    with open(journal.path("x.log").with_name("x.log.lock")) as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        journal.append("x.log", {"n": 2})

    assert [e["n"] for e in journal.read("x.log")] == [1, 2]
